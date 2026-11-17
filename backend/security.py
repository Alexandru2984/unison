"""Bounded ASGI guards. Submitted text and client addresses are never logged."""
import asyncio
import time
from collections import OrderedDict
from starlette.responses import JSONResponse


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


class ApiSecurityMiddleware:
    def __init__(self, app, public_origin, write_limiter, max_body=16_384):
        self.app = app
        self.public_origin = public_origin
        self.write_limiter = write_limiter
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
            client = (scope.get('client') or ('unknown', 0))[0]
            if not self.write_limiter.allow(client):
                await reject(429, 'Too many writes. Please try again shortly.', {'Retry-After': '30'})
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
