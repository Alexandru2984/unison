"""Bounded ASGI guards. Submitted text and client addresses are never logged."""
import asyncio
import ipaddress
import time
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from starlette.responses import JSONResponse


def client_key(host):
    """Rate-limit identity. One IPv6 subscriber normally controls a whole /64."""
    try:
        address = ipaddress.ip_address(host)
    except (TypeError, ValueError):
        return str(host or 'unknown')
    if address.version == 6:
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        return str(ipaddress.ip_network(f'{address}/64', strict=False).network_address) + '/64'
    return str(address)


def scope_client(scope):
    return client_key((scope.get('client') or ('unknown', 0))[0])


class RateLimiter:
    def __init__(self, capacity=12, per_minute=10, max_clients=4096):
        self.capacity = capacity
        self.refill = per_minute / 60
        self.max_clients = max_clients
        self.entries = OrderedDict()

    def allow(self, key):
        now = time.monotonic()
        while self.entries and now - next(iter(self.entries.values()))[1] > 120:
            self.entries.popitem(last=False)
        previous = self.entries.pop(key, None)
        if previous is None and len(self.entries) >= self.max_clients:
            return False
        tokens, updated = previous or (self.capacity, now)
        tokens = min(self.capacity, tokens + (now - updated) * self.refill)
        allowed = tokens >= 1
        self.entries[key] = (tokens - 1 if allowed else tokens, now)
        return allowed


class WriteBudget:
    """Daily per-client and hourly global ceilings on newly stored ideas.

    The token bucket smooths bursts; this budget bounds how quickly anyone can
    consume the shared board's finite capacity. Memory is bounded.
    """

    def __init__(self, per_client_day=150, global_hour=600, max_clients=65_536, clock=time.time):
        self.per_client_day = per_client_day
        self.global_hour = global_hour
        self.max_clients = max_clients
        self.clock = clock
        self.clients = OrderedDict()
        self.recent = deque()

    def _day(self, now):
        return datetime.fromtimestamp(now, timezone.utc).date()

    def check(self, key):
        """Return (seconds to wait, 'global' | 'client'), or (0, None) when allowed."""
        now = self.clock()
        while self.recent and now - self.recent[0] >= 3600:
            self.recent.popleft()
        if len(self.recent) >= self.global_hour:
            return max(1, int(3600 - (now - self.recent[0])) + 1), 'global'
        day, count = self.clients.get(key, (None, 0))
        if day == self._day(now) and count >= self.per_client_day:
            midnight = datetime.combine(self._day(now) + timedelta(days=1), datetime.min.time(), timezone.utc)
            return max(1, int(midnight.timestamp() - now) + 1), 'client'
        return 0, None

    def consume(self, key):
        now = self.clock()
        today = self._day(now)
        self.recent.append(now)
        day, count = self.clients.pop(key, (today, 0))
        self.clients[key] = (today, count + 1 if day == today else 1)
        while len(self.clients) > self.max_clients:
            self.clients.popitem(last=False)


def classify_write(path):
    if path == '/api/idea':
        return 'idea'
    if path.endswith('/report'):
        return 'report'
    if path.endswith('/water'):
        return 'water'
    if path == '/api/preview':
        return 'preview'
    return 'idea'


class ApiSecurityMiddleware:
    def __init__(self, app, public_origin, limiters, max_body=16_384):
        self.app = app
        self.public_origin = public_origin
        self.limiters = limiters
        self.max_body = max_body

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            await self.app(scope, receive, send)
            return

        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers.extend([(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                                (b'x-frame-options', b'DENY'), (b'referrer-policy', b'strict-origin-when-cross-origin')])
                message = {**message, 'headers': headers}
            await send(message)

        async def reject(status, detail, headers=None):
            await JSONResponse({'detail': detail}, status_code=status, headers=headers)(scope, receive, secure_send)

        headers = {k.lower(): v for k, v in scope.get('headers', [])}
        if scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origin = headers.get(b'origin')
            if (origin is not None and origin.decode('latin1') != self.public_origin) or headers.get(b'sec-fetch-site') == b'cross-site':
                await reject(403, 'Cross-origin writes are not allowed')
                return
            if headers.get(b'content-type', b'').split(b';')[0].strip().lower() != b'application/json':
                await reject(415, 'Use application/json')
                return
            if not self.limiters[classify_write(scope['path'])].allow(scope_client(scope)):
                await reject(429, 'Too many requests. Please try again shortly.', {'Retry-After': '30'})
                return
        try:
            declared_size = int(headers.get(b'content-length', b'0'))
        except ValueError:
            await reject(400, 'Invalid content length')
            return
        if declared_size < 0:
            await reject(400, 'Invalid content length')
            return
        if declared_size > self.max_body:
            await reject(413, 'Request body is too large')
            return
        body = bytearray()

        async def read_body():
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return False
                chunk = message.get('body', b'')
                if len(body) + len(chunk) > self.max_body:
                    return None
                body.extend(chunk)
                if not message.get('more_body', False):
                    return True
        try:
            complete = await asyncio.wait_for(read_body(), 5)
        except TimeoutError:
            await reject(408, 'Request body timed out')
            return
        if complete is None:
            await reject(413, 'Request body is too large')
            return
        if complete is False:
            return
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
            return await receive()
        await self.app(scope, replay, secure_send)
