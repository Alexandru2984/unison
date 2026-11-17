import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import sqlite3
import unicodedata
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.websockets import WebSocketDisconnect
from security import ApiSecurityMiddleware, RateLimiter
from moderation import ReportReason, board_revision, init_moderation, now

PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_DIR / '.env', override=False)


def bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f'{name} must be an integer') from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f'{name} must be between {minimum} and {maximum}')
    return value


DB_PATH = Path(os.getenv('DB_PATH', Path(__file__).resolve().parent / 'evolution.db')).resolve()
UNISON_BIN = Path(os.getenv('UNISON_BIN', PROJECT_DIR / 'ucm-bin' / 'ucm-bin')).resolve()
UNISON_PROGRAM = Path(os.getenv('UNISON_PROGRAM', PROJECT_DIR / 'unison' / 'evolution.uc')).resolve()
PUBLIC_ORIGIN = os.getenv('PUBLIC_ORIGIN', 'https://unison.micutu.com').rstrip('/')
MAX_IDEAS = bounded_int('MAX_IDEAS', 10_000, 100, 100_000)
MAX_RESULTS = bounded_int('MAX_RESULTS', 500, 10, 2_000)
MAX_DEPTH = 32
MAX_RESULT_CHARACTERS = 4096
MAX_PROCESS_BYTES = 65_536
MAX_CLIENTS = 48
MAX_REPORTS = 10_000
MODERATION_POLL_SECONDS = 1
MUTATION_TIMEOUT_SECONDS = bounded_int('MUTATION_TIMEOUT_SECONDS', 5, 1, 30)
IDEA_FIELDS = 'id, parent_id, content, mutation, created_at, root_id, depth'
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
async def watch_moderation():
    with closing(connect_db()) as conn:
        revision = board_revision(conn)
    while True:
        await asyncio.sleep(MODERATION_POLL_SECONDS)
        try:
            with closing(connect_db()) as conn:
                current = board_revision(conn)
            if current != revision:
                revision = current
                await broadcast_idea({'event': 'board_changed', 'revision': current})
        except sqlite3.Error:
            logger.warning('Moderation state check failed')


@asynccontextmanager
async def lifespan(_app):
    task = asyncio.create_task(watch_moderation())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


docs_enabled = os.getenv('ENABLE_API_DOCS', '').lower() == 'true'
app = FastAPI(lifespan=lifespan, title='Idea Evolution API', docs_url='/docs' if docs_enabled else None,
              redoc_url='/redoc' if docs_enabled else None, openapi_url='/openapi.json' if docs_enabled else None)
write_limiter = RateLimiter()
socket_limiter = RateLimiter(capacity=12, per_minute=12)
app.add_middleware(ApiSecurityMiddleware, public_origin=PUBLIC_ORIGIN, write_limiter=write_limiter)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv(
    'ALLOWED_HOSTS', f'{urlsplit(PUBLIC_ORIGIN).hostname},127.0.0.1,localhost').split(','))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{'location': error.get('loc', ()), 'message': error.get('msg', 'Invalid value'),
               'type': error.get('type', 'value_error')} for error in exc.errors()]
    logger.warning('Request validation failed path=%s errors=%d', request.url.path, len(errors))
    return JSONResponse(status_code=422, content={'detail': errors})


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, exc: Exception):
    logger.error('Unhandled API failure type=%s', type(exc).__name__)
    return JSONResponse(status_code=500, content={'detail': 'An unexpected error occurred. Please try again.'},
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout = 5000')
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_db()) as conn:
        conn.execute('PRAGMA journal_mode = WAL')
        conn.execute('''CREATE TABLE IF NOT EXISTS ideas (id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER, content TEXT NOT NULL, mutation TEXT NOT NULL)''')
        columns = {row['name'] for row in conn.execute('PRAGMA table_info(ideas)')}
        additions = {'created_at': 'TEXT', 'root_id': 'INTEGER', 'depth': 'INTEGER NOT NULL DEFAULT 0',
                     'request_key': 'TEXT', 'request_hash': 'TEXT'}
        for name, definition in additions.items():
            if name not in columns:
                conn.execute(f'ALTER TABLE ideas ADD COLUMN {name} {definition}')
        if conn.execute('SELECT 1 FROM ideas WHERE root_id IS NULL LIMIT 1').fetchone():
            # Old timestamps stay NULL; legacy orphaned nodes receive a usable local root.
            conn.execute('''WITH RECURSIVE tree(id, root, depth) AS (
                SELECT id, id, 0 FROM ideas WHERE parent_id IS NULL UNION ALL
                SELECT i.id, t.root, t.depth + 1 FROM ideas i JOIN tree t ON i.parent_id = t.id WHERE t.depth < 1000)
                UPDATE ideas SET root_id = COALESCE((SELECT root FROM tree WHERE tree.id=ideas.id), id),
                depth = COALESCE((SELECT depth FROM tree WHERE tree.id=ideas.id), 0) WHERE root_id IS NULL''')
        conn.execute('CREATE INDEX IF NOT EXISTS ideas_parent ON ideas(parent_id, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS ideas_root ON ideas(root_id, id)')
        conn.execute('CREATE INDEX IF NOT EXISTS ideas_mutation ON ideas(mutation, id)')
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS ideas_request_key ON ideas(request_key) WHERE request_key IS NOT NULL')
        init_moderation(conn)
        conn.commit()


init_db()


class Mutation(StrEnum):
    BASE = 'base'
    EXPAND = 'expand'
    REPHRASE = 'rephrase'
    MUTATE_KEYWORDS = 'mutate_keywords'
    SYNTHESIZE = 'synthesize'


class IdeaRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(default='', max_length=2000, strict=True)
    parent_id: int | None = Field(default=None, gt=0, strict=True)
    mutation: Mutation = Mutation.BASE

    @model_validator(mode='after')
    def validate_operation(self):
        self.content = self.content.strip()
        if any(unicodedata.category(c) in ('Cc', 'Cs') and c not in '\n\r\t' for c in self.content):
            raise ValueError('Unsupported control character in content')
        if self.mutation == Mutation.BASE and not self.content:
            raise ValueError('Base ideas require content')
        if self.mutation != Mutation.BASE:
            if self.parent_id is None:
                raise ValueError('Mutations require a parent idea')
            if self.content:
                raise ValueError('Mutations use the selected parent content')
        return self


clients: dict[WebSocket, str] = {}
idea_lock = asyncio.Lock()
mutation_slots = asyncio.Semaphore(2)


async def broadcast_idea(idea: dict) -> None:
    async def deliver(client):
        try:
            await asyncio.wait_for(client.send_json(idea), timeout=0.5)
        except Exception:
            clients.pop(client, None)
            try:
                await asyncio.wait_for(client.close(code=1013, reason='Please reconnect'), timeout=0.1)
            except Exception:
                pass
    await asyncio.gather(*(deliver(client) for client in tuple(clients)))


async def run_mutation(mutation: Mutation, content: str) -> str:
    if not UNISON_BIN.is_file() or not UNISON_PROGRAM.is_file():
        raise HTTPException(status_code=503, detail='Mutation engine unavailable')
    try:
        await asyncio.wait_for(mutation_slots.acquire(), timeout=0.1)
    except TimeoutError:
        raise HTTPException(status_code=503, detail='Mutation engine is busy. Please try again.', headers={'Retry-After': '2'}) from None
    process = None
    collection_tasks = []
    try:
        process = await asyncio.create_subprocess_exec(
            str(UNISON_BIN), 'run.compiled', str(UNISON_PROGRAM), mutation.value, content,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, start_new_session=True)

        async def read_bounded(stream):
            data = bytearray()
            while len(data) <= MAX_PROCESS_BYTES:
                chunk = await stream.read(MAX_PROCESS_BYTES + 1 - len(data))
                if not chunk:
                    return bytes(data)
                data.extend(chunk)
            raise HTTPException(status_code=502, detail='Mutation engine output exceeded its limit')

        collection_tasks = [asyncio.create_task(read_bounded(process.stdout)),
                            asyncio.create_task(read_bounded(process.stderr)),
                            asyncio.create_task(process.wait())]
        try:
            stdout, _stderr, _ = await asyncio.wait_for(asyncio.gather(*collection_tasks), timeout=MUTATION_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning('Mutation timed out mutation=%s', mutation.value)
            raise HTTPException(status_code=504, detail='Mutation engine timed out') from None
        if process.returncode != 0:
            logger.error('Mutation failed mutation=%s code=%d', mutation.value, process.returncode)
            raise HTTPException(status_code=502, detail='Mutation engine failed')
        try:
            payload = json.loads(stdout.decode('utf-8', errors='strict'))
            result = payload['result']
            valid = payload.get('mutation') == mutation.value
        except (ValueError, KeyError, TypeError, AttributeError):
            result, valid = None, False
        if not valid or not isinstance(result, str) or not result.strip() or len(result) > MAX_RESULT_CHARACTERS:
            raise HTTPException(status_code=502, detail='Mutation returned invalid or oversized text. Try a shorter idea or Synthesize first.')
        if any(unicodedata.category(c) in ('Cc', 'Cs') and c not in '\n\r\t' for c in result):
            raise HTTPException(status_code=502, detail='Mutation engine returned unsupported characters')
        return result
    except OSError:
        logger.error('Mutation engine could not be started')
        raise HTTPException(status_code=503, detail='Mutation engine unavailable') from None
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            for task in collection_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*collection_tasks, return_exceptions=True)
            # Drain the finite pipe buffers after killing the process group. wait()
            # alone can hang when an oversized output has paused its read transport.
            await process.communicate()
        mutation_slots.release()


def get_parent(conn, parent_id):
    if parent_id is None:
        return None
    row = conn.execute(f'SELECT {IDEA_FIELDS} FROM ideas WHERE id = ? AND hidden=0', (parent_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Parent idea not found')
    if row['depth'] >= MAX_DEPTH:
        raise HTTPException(status_code=422, detail='Maximum branch depth reached. Start a new seed.')
    return row


@app.get('/api/health')
async def health():
    with closing(connect_db()) as conn:
        conn.execute('SELECT 1').fetchone()
    return {'status': 'ok', 'engine_available': UNISON_BIN.is_file() and UNISON_PROGRAM.is_file(),
            'revision': os.getenv('APP_REVISION', 'development')[:12]}


@app.post('/api/idea', status_code=201)
async def create_idea(req: IdeaRequest, response: Response, idempotency_key: str | None = Header(default=None)):
    if idempotency_key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', idempotency_key):
        raise HTTPException(status_code=422, detail='Invalid idempotency key')
    request_hash = hashlib.sha256(req.model_dump_json().encode()).hexdigest()

    def replay(conn):
        if idempotency_key is None:
            return None
        row = conn.execute(f'SELECT {IDEA_FIELDS}, request_hash, hidden FROM ideas WHERE request_key = ?', (idempotency_key,)).fetchone()
        if row is None:
            return None
        if row['hidden']:
            raise HTTPException(status_code=404, detail='Idea not found')
        if row['request_hash'] != request_hash:
            raise HTTPException(status_code=409, detail='Idempotency key was already used for a different idea')
        response.status_code = 200
        return {key: row[key] for key in IDEA_FIELDS.split(', ')}

    with closing(connect_db()) as conn:
        existing = replay(conn)
        if existing:
            return existing
        if conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0] >= MAX_IDEAS:
            raise HTTPException(status_code=507, detail='Public board capacity reached')
        parent = get_parent(conn, req.parent_id)
    new_content = req.content if req.mutation == Mutation.BASE else await run_mutation(req.mutation, parent['content'])
    async with idea_lock:
        with closing(connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = replay(conn)
            if existing:
                return existing
            if conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0] >= MAX_IDEAS:
                raise HTTPException(status_code=507, detail='Public board capacity reached')
            parent = get_parent(conn, req.parent_id)
            cursor = conn.execute('''INSERT INTO ideas (parent_id, content, mutation, created_at, root_id, depth, request_key, request_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
                req.parent_id, new_content, req.mutation.value, datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                parent['root_id'] if parent else None, parent['depth'] + 1 if parent else 0, idempotency_key, request_hash))
            idea_id = cursor.lastrowid
            if parent is None:
                conn.execute('UPDATE ideas SET root_id = ? WHERE id = ?', (idea_id, idea_id))
            idea = dict(conn.execute(f'SELECT {IDEA_FIELDS} FROM ideas WHERE id = ?', (idea_id,)).fetchone())
            conn.commit()
    await broadcast_idea({'event': 'ideas_changed'})
    return idea


@app.get('/api/idea')
async def get_ideas(response: Response, before: int | None = Query(default=None, gt=0),
                    after: int | None = Query(default=None, ge=0), limit: int = Query(default=200, ge=1, le=500),
                    q: str = Query(default='', max_length=200), root_id: int | None = Query(default=None, gt=0),
                    mutation: Mutation | None = None, roots_only: bool = False,
                    ids: str | None = Query(default=None, max_length=700)):
    if before is not None and after is not None:
        raise HTTPException(status_code=422, detail='Use either before or after')
    clauses, values = ['hidden=0'], []
    if roots_only:
        clauses.append('parent_id IS NULL')
    if ids is not None:
        parts = ids.split(',')
        if len(parts) > 100 or any(not re.fullmatch(r'[1-9][0-9]{0,9}', part) for part in parts):
            raise HTTPException(status_code=422, detail='Use up to 100 positive idea IDs')
        clauses.append('id IN (' + ','.join('?' for _ in parts) + ')')
        values.extend(int(part) for part in parts)
    for condition, value in [('id < ?', before), ('id > ?', after), ('root_id = ?', root_id), ('mutation = ?', mutation)]:
        if value is not None:
            clauses.append(condition)
            values.append(value)
    if q.strip():
        clauses.append("content LIKE ? ESCAPE '\\'")
        values.append('%' + q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%')
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    order = 'ASC' if after is not None else 'DESC'
    page_size = min(limit, MAX_RESULTS)
    with closing(connect_db()) as conn:
        conn.execute('BEGIN')
        response.headers['X-Board-Revision'] = str(board_revision(conn))
        rows = conn.execute(f'SELECT {IDEA_FIELDS} FROM ideas{where} ORDER BY id {order} LIMIT ?', (*values, page_size + 1)).fetchall()
    response.headers['X-Has-More'] = str(len(rows) > page_size).lower()
    rows = rows[:page_size]
    if rows:
        response.headers['X-Next-Cursor'] = str(rows[-1]['id'])
    if after is None:
        rows.reverse()
    return [dict(row) for row in rows]


@app.get('/api/idea/{idea_id}')
async def get_idea(idea_id: int):
    with closing(connect_db()) as conn:
        row = conn.execute(f'SELECT {IDEA_FIELDS} FROM ideas WHERE id = ? AND hidden=0', (idea_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Idea not found')
    return dict(row)


@app.get('/api/idea/{idea_id}/lineage')
async def get_lineage(idea_id: int):
    lineage, seen = [], set()
    with closing(connect_db()) as conn:
        conn.execute('BEGIN')
        while idea_id is not None and idea_id not in seen and len(lineage) <= MAX_DEPTH:
            seen.add(idea_id)
            row = conn.execute(f'SELECT {IDEA_FIELDS} FROM ideas WHERE id = ? AND hidden=0', (idea_id,)).fetchone()
            if row is None:
                if not lineage:
                    raise HTTPException(status_code=404, detail='Idea not found')
                break
            lineage.append(dict(row))
            idea_id = row['parent_id']
    return list(reversed(lineage))


@app.get('/api/stats')
async def get_stats():
    with closing(connect_db()) as conn:
        conn.execute('BEGIN')
        summary = dict(conn.execute('''SELECT COUNT(*) AS total, COALESCE(SUM(parent_id IS NULL), 0) AS seeds,
            COALESCE(MAX(depth), 0) AS max_depth, MAX(id) AS latest_id FROM ideas WHERE hidden=0''').fetchone())
        summary['board_revision'] = board_revision(conn)
        summary['mutations'] = {row['mutation']: row['count'] for row in conn.execute('SELECT mutation, COUNT(*) AS count FROM ideas WHERE hidden=0 GROUP BY mutation')}
    summary['capacity'] = MAX_IDEAS
    summary['max_branch_depth'] = MAX_DEPTH
    return summary


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: ReportReason


@app.post('/api/idea/{idea_id}/report', status_code=202)
async def report_idea(idea_id: int, req: ReportRequest):
    with closing(connect_db()) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM ideas WHERE id=? AND hidden=0', (idea_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail='Idea not found')
        existing = conn.execute("SELECT 1 FROM idea_reports WHERE idea_id=? AND reason=? AND status='open'", (idea_id, req.reason.value)).fetchone()
        if existing is None:
            if conn.execute('SELECT COUNT(*) FROM idea_reports').fetchone()[0] >= MAX_REPORTS:
                raise HTTPException(status_code=503, detail='Reporting is temporarily unavailable. Please try again later.')
            conn.execute('INSERT INTO idea_reports(idea_id,reason,created_at) VALUES(?,?,?)', (idea_id, req.reason.value, now()))
            conn.commit()
    # Do not expose report IDs, counts or previous reports. Reports never hide
    # content automatically, and no IP, browser identifier or free text is stored.
    return {'status': 'received'}


@app.get('/api/mutations')
async def get_mutations():
    return [
        {'id': 'expand', 'name': 'Expand', 'description': 'Elaborate on longer words and extend the premise.'},
        {'id': 'rephrase', 'name': 'Rephrase', 'description': 'Reverse word order for a retrospective perspective.'},
        {'id': 'mutate_keywords', 'name': 'Amplify', 'description': 'Emphasize longer keywords with uppercase and punctuation.'},
        {'id': 'synthesize', 'name': 'Synthesize', 'description': 'Keep alternating words to condense the idea.'},
    ]


@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    if websocket.headers.get('origin') != PUBLIC_ORIGIN:
        await websocket.close(code=1008, reason='Origin not allowed')
        return
    address = websocket.client.host if websocket.client else 'unknown'
    if len(clients) >= MAX_CLIENTS or sum(value == address for value in clients.values()) >= 4 or not socket_limiter.allow(address):
        await websocket.close(code=1013, reason='Connection limit reached')
        return
    clients[websocket] = address
    try:
        await websocket.accept()
        while True:
            message = await websocket.receive()
            if message['type'] == 'websocket.disconnect':
                break
            await websocket.close(code=1008, reason='This connection only receives updates')
            break
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        clients.pop(websocket, None)
