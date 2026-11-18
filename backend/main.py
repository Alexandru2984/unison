import asyncio
import hashlib
import json
import logging
import os
import re
import signal
import sqlite3
from collections import OrderedDict
from contextlib import asynccontextmanager, closing, suppress
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlsplit
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response, WebSocket, Path as PathParam
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.websockets import WebSocketDisconnect
from security import ApiSecurityMiddleware, RateLimiter, WriteBudget, client_key
from moderation import ReportReason, board_revision, init_moderation, now
from text_policy import PolicyError, clean_engine_text, clean_user_text, content_key
from social import WaterLedger, activity, add_water, discover_ids, init_social, utc_day, water_total

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
MAX_SQLITE_ID = 2**63 - 1
IdeaId = Annotated[int, PathParam(gt=0, le=MAX_SQLITE_ID)]
MAX_RESULT_CHARACTERS = 4096
MAX_PROCESS_BYTES = 65_536
MAX_CLIENTS = bounded_int('MAX_SOCKETS', 256, 8, 4096)
MAX_SOCKETS_PER_CLIENT = 4
MAX_REPORTS = 10_000
DAILY_IDEAS_PER_CLIENT = bounded_int('DAILY_IDEAS_PER_CLIENT', 150, 1, 10_000)
GLOBAL_IDEAS_PER_HOUR = bounded_int('GLOBAL_IDEAS_PER_HOUR', 600, 1, 100_000)
MODERATION_POLL_SECONDS = 1
MUTATION_TIMEOUT_SECONDS = bounded_int('MUTATION_TIMEOUT_SECONDS', 5, 1, 30)
IDEA_FIELDS = 'id, parent_id, content, mutation, created_at, root_id, depth'
# Public rows carry live counts of visible branches and of reactions.
PUBLIC_FIELDS = (IDEA_FIELDS + ', (SELECT COUNT(*) FROM ideas c WHERE c.parent_id = ideas.id AND c.hidden = 0) AS children'
                 ', (SELECT COALESCE(SUM(w.count), 0) FROM idea_water w WHERE w.idea_id = ideas.id) AS water')
PUBLIC_KEYS = [*IDEA_FIELDS.split(', '), 'children', 'water']
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
# Separate buckets: reporting or reacting never consumes the budget for new ideas.
limiters = {'idea': RateLimiter(capacity=16, per_minute=12), 'report': RateLimiter(capacity=6, per_minute=6),
            'water': RateLimiter(capacity=30, per_minute=60), 'preview': RateLimiter(capacity=10, per_minute=20)}
write_limiter = limiters['idea']
socket_limiter = RateLimiter(capacity=12, per_minute=12)
write_budget = WriteBudget(DAILY_IDEAS_PER_CLIENT, GLOBAL_IDEAS_PER_HOUR)
app.add_middleware(ApiSecurityMiddleware, public_origin=PUBLIC_ORIGIN, limiters=limiters)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.getenv(
    'ALLOWED_HOSTS', f'{urlsplit(PUBLIC_ORIGIN).hostname},127.0.0.1,localhost').split(','))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [{'location': error.get('loc', ()), 'message': str(error.get('msg', 'Invalid value')).removeprefix('Value error, '),
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
                     'request_key': 'TEXT', 'request_hash': 'TEXT', 'content_key': 'TEXT'}
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
        # Duplicate detection identity; legacy rows are keyed in place, text is unchanged.
        for row in conn.execute('SELECT id, content FROM ideas WHERE content_key IS NULL').fetchall():
            conn.execute('UPDATE ideas SET content_key = ? WHERE id = ?', (content_key(row['content']), row['id']))
        conn.execute('CREATE INDEX IF NOT EXISTS ideas_content_key ON ideas(content_key, parent_id)')
        init_moderation(conn)
        init_social(conn)
        conn.commit()


init_db()


class Mutation(StrEnum):
    BASE = 'base'
    EXPAND = 'expand'
    REPHRASE = 'rephrase'
    MUTATE_KEYWORDS = 'mutate_keywords'
    SYNTHESIZE = 'synthesize'
    QUESTION = 'question'
    TWIST = 'twist'
    HEADLINE = 'headline'
    FLIP = 'flip'


TRANSFORMATIONS = [mutation for mutation in Mutation if mutation != Mutation.BASE]
CATALOGUE = [
    {'id': 'expand', 'name': 'Expand', 'description': 'Elaborate on longer words and extend the premise.'},
    {'id': 'rephrase', 'name': 'Rephrase', 'description': 'Reverse word order for a retrospective perspective.'},
    {'id': 'mutate_keywords', 'name': 'Amplify', 'description': 'Emphasize longer keywords with uppercase and punctuation.'},
    {'id': 'synthesize', 'name': 'Synthesize', 'description': 'Keep alternating words to condense the idea.'},
    {'id': 'question', 'name': 'Question', 'description': 'Turn the idea into a what-if question; repeat it for new framings.'},
    {'id': 'twist', 'name': 'Twist', 'description': 'Add a surprising constraint chosen from the text itself.'},
    {'id': 'headline', 'name': 'Headline', 'description': 'Condense the idea into a title-case headline.'},
    {'id': 'flip', 'name': 'Flip', 'description': 'Swap words for their opposites to explore the reverse premise.'},
]
PREVIEW_CACHE_SIZE = 512


class IdeaRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(default='', max_length=2000, strict=True)
    parent_id: int | None = Field(default=None, gt=0, le=MAX_SQLITE_ID, strict=True)
    mutation: Mutation = Mutation.BASE

    @model_validator(mode='after')
    def validate_operation(self):
        if self.mutation == Mutation.BASE:
            if not self.content.strip():
                raise ValueError('Base ideas require content')
            try:
                self.content = clean_user_text(self.content)
            except PolicyError as exc:
                raise ValueError(str(exc)) from None
        else:
            if self.parent_id is None:
                raise ValueError('Mutations require a parent idea')
            if self.content.strip():
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


async def run_engine(mode: str, content: str) -> dict:
    """Run one bounded engine process and return its strict JSON object."""
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
            str(UNISON_BIN), 'run.compiled', str(UNISON_PROGRAM), mode, content,
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
            logger.warning('Mutation timed out mutation=%s', mode)
            raise HTTPException(status_code=504, detail='Mutation engine timed out') from None
        if process.returncode != 0:
            logger.error('Mutation failed mutation=%s code=%d', mode, process.returncode)
            raise HTTPException(status_code=502, detail='Mutation engine failed')
        try:
            payload = json.loads(stdout.decode('utf-8', errors='strict'))
        except ValueError:
            payload = None
        if not isinstance(payload, dict) or payload.get('mutation') != mode:
            raise HTTPException(status_code=502, detail='Mutation returned invalid or oversized text. Try a shorter idea or Synthesize first.')
        return payload
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


def valid_result(value) -> str | None:
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_RESULT_CHARACTERS:
        return None
    try:
        return clean_engine_text(value)
    except PolicyError:
        return None


async def run_mutation(mutation: Mutation, content: str) -> str:
    payload = await run_engine(mutation.value, content)
    result = payload.get('result')
    if not isinstance(result, str) or not result.strip() or len(result) > MAX_RESULT_CHARACTERS:
        raise HTTPException(status_code=502, detail='Mutation returned invalid or oversized text. Try a shorter idea or Synthesize first.')
    try:
        return clean_engine_text(result)
    except PolicyError:
        raise HTTPException(status_code=422, detail='This idea contains characters the transformation cannot publish.') from None


async def run_all(content: str) -> dict[str, str | None]:
    """Every transformation from one process; an unusable result becomes None."""
    results = (await run_engine('all', content)).get('results')
    if not isinstance(results, dict):
        raise HTTPException(status_code=502, detail='Mutation engine failed')
    return {mutation.value: valid_result(results.get(mutation.value)) for mutation in TRANSFORMATIONS}


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


def public_idea(row):
    return {key: row[key] for key in PUBLIC_KEYS}


def existing_duplicate(conn, parent_id, key=None, mutation=None):
    """A visible equivalent idea, None, or 409 when moderation removed that exact text."""
    if mutation is not None:
        row = conn.execute(f'SELECT {PUBLIC_FIELDS}, hidden FROM ideas WHERE parent_id = ? AND mutation = ? '
                           'ORDER BY hidden, id LIMIT 1', (parent_id, mutation)).fetchone()
    else:
        row = conn.execute(f'SELECT {PUBLIC_FIELDS}, hidden FROM ideas WHERE content_key = ? AND parent_id IS ? '
                           'ORDER BY hidden, id LIMIT 1', (key, parent_id)).fetchone()
    if row is None:
        return None
    if row['hidden']:
        raise HTTPException(status_code=409, detail='This text was removed by moderation and cannot be published again.')
    return public_idea(row)


@app.post('/api/idea', status_code=201)
async def create_idea(req: IdeaRequest, request: Request, response: Response,
                      idempotency_key: str | None = Header(default=None)):
    if idempotency_key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{16,64}', idempotency_key):
        raise HTTPException(status_code=422, detail='Invalid idempotency key')
    request_hash = hashlib.sha256(req.model_dump_json().encode()).hexdigest()
    client = client_key(request.client.host if request.client else None)

    def replay(conn):
        if idempotency_key is None:
            return None
        row = conn.execute(f'SELECT {PUBLIC_FIELDS}, request_hash, hidden FROM ideas WHERE request_key = ?', (idempotency_key,)).fetchone()
        if row is None:
            return None
        if row['hidden']:
            raise HTTPException(status_code=404, detail='Idea not found')
        if row['request_hash'] != request_hash:
            raise HTTPException(status_code=409, detail='Idempotency key was already used for a different idea')
        response.status_code = 200
        return public_idea(row)

    def duplicate(conn, key=None):
        # Deterministic rules always produce the same branch; reuse it instead of storing a copy.
        if req.mutation != Mutation.BASE:
            found = existing_duplicate(conn, req.parent_id, mutation=req.mutation.value)
        else:
            found = existing_duplicate(conn, req.parent_id, key or content_key(req.content))
        if found is not None:
            response.status_code = 200
            response.headers['X-Idea-Duplicate'] = 'true'
        return found

    def ensure_budget():
        wait, scope = write_budget.check(client)
        if wait:
            detail = ('The garden is growing very fast right now. New ideas resume shortly.' if scope == 'global'
                      else 'Daily limit for new ideas reached on this connection. Explore and branch again tomorrow.')
            raise HTTPException(status_code=429, detail=detail, headers={'Retry-After': str(wait)})

    with closing(connect_db()) as conn:
        existing = replay(conn)
        if existing:
            return existing
        parent = get_parent(conn, req.parent_id)
        existing = duplicate(conn)
        if existing:
            return existing
        if conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0] >= MAX_IDEAS:
            raise HTTPException(status_code=507, detail='Public board capacity reached')
    ensure_budget()
    new_content = req.content if req.mutation == Mutation.BASE else await run_mutation(req.mutation, parent['content'])
    key = content_key(new_content)
    if parent is not None and new_content.strip() == parent['content'].strip():
        raise HTTPException(status_code=422, detail='This would repeat the parent idea unchanged. Try another direction.')
    async with idea_lock:
        with closing(connect_db()) as conn:
            conn.execute('BEGIN IMMEDIATE')
            existing = replay(conn)
            if existing:
                return existing
            parent = get_parent(conn, req.parent_id)
            existing = duplicate(conn, key)
            if existing:
                return existing
            if req.mutation != Mutation.BASE:
                # A different rule can still reproduce text already stored under this parent.
                existing = existing_duplicate(conn, req.parent_id, key)
                if existing:
                    response.status_code = 200
                    response.headers['X-Idea-Duplicate'] = 'true'
                    return existing
            if conn.execute('SELECT COUNT(*) FROM ideas').fetchone()[0] >= MAX_IDEAS:
                raise HTTPException(status_code=507, detail='Public board capacity reached')
            ensure_budget()
            cursor = conn.execute('''INSERT INTO ideas (parent_id, content, mutation, created_at, root_id, depth, request_key, request_hash, content_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
                req.parent_id, new_content, req.mutation.value, datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                parent['root_id'] if parent else None, parent['depth'] + 1 if parent else 0, idempotency_key, request_hash, key))
            idea_id = cursor.lastrowid
            if parent is None:
                conn.execute('UPDATE ideas SET root_id = ? WHERE id = ?', (idea_id, idea_id))
            idea = dict(conn.execute(f'SELECT {PUBLIC_FIELDS} FROM ideas WHERE id = ?', (idea_id,)).fetchone())
            conn.commit()
            write_budget.consume(client)
    await broadcast_idea({'event': 'ideas_changed'})
    return idea


@app.get('/api/idea')
async def get_ideas(response: Response, before: int | None = Query(default=None, gt=0, le=MAX_SQLITE_ID),
                    after: int | None = Query(default=None, ge=0, le=MAX_SQLITE_ID), limit: int = Query(default=200, ge=1, le=500),
                    q: str = Query(default='', max_length=200), root_id: int | None = Query(default=None, gt=0, le=MAX_SQLITE_ID),
                    mutation: Mutation | None = None, roots_only: bool = False, leaves_only: bool = False,
                    ids: str | None = Query(default=None, max_length=700)):
    if before is not None and after is not None:
        raise HTTPException(status_code=422, detail='Use either before or after')
    clauses, values = ['hidden=0'], []
    if roots_only:
        clauses.append('parent_id IS NULL')
    if leaves_only:
        clauses.append('NOT EXISTS (SELECT 1 FROM ideas c WHERE c.parent_id = ideas.id AND c.hidden = 0)')
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
        rows = conn.execute(f'SELECT {PUBLIC_FIELDS} FROM ideas{where} ORDER BY id {order} LIMIT ?', (*values, page_size + 1)).fetchall()
    response.headers['X-Has-More'] = str(len(rows) > page_size).lower()
    rows = rows[:page_size]
    if rows:
        response.headers['X-Next-Cursor'] = str(rows[-1]['id'])
    if after is None:
        rows.reverse()
    return [dict(row) for row in rows]


@app.get('/api/idea/{idea_id}')
async def get_idea(idea_id: IdeaId):
    with closing(connect_db()) as conn:
        row = conn.execute(f'SELECT {PUBLIC_FIELDS} FROM ideas WHERE id = ? AND hidden=0', (idea_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='Idea not found')
    return dict(row)


@app.get('/api/idea/{idea_id}/lineage')
async def get_lineage(idea_id: IdeaId):
    lineage, seen = [], set()
    with closing(connect_db()) as conn:
        conn.execute('BEGIN')
        while idea_id is not None and idea_id not in seen and len(lineage) <= MAX_DEPTH:
            seen.add(idea_id)
            row = conn.execute(f'SELECT {PUBLIC_FIELDS} FROM ideas WHERE id = ? AND hidden=0', (idea_id,)).fetchone()
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
        summary['water'] = conn.execute('SELECT COALESCE(SUM(w.count), 0) FROM idea_water w JOIN ideas i ON i.id = w.idea_id '
                                        'WHERE i.hidden = 0').fetchone()[0]
        summary['activity'] = activity(conn)
    summary['capacity'] = MAX_IDEAS
    summary['max_branch_depth'] = MAX_DEPTH
    return summary


class ReportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    reason: ReportReason


@app.post('/api/idea/{idea_id}/report', status_code=202)
async def report_idea(idea_id: IdeaId, req: ReportRequest):
    with closing(connect_db()) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM ideas WHERE id=? AND hidden=0', (idea_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail='Idea not found')
        existing = conn.execute("SELECT 1 FROM idea_reports WHERE idea_id=? AND reason=? AND status='open'", (idea_id, req.reason.value)).fetchone()
        if existing is None:
            if conn.execute("SELECT COUNT(*) FROM idea_reports WHERE status='open'").fetchone()[0] >= MAX_REPORTS:
                raise HTTPException(status_code=503, detail='Reporting is temporarily unavailable. Please try again later.')
            conn.execute('INSERT INTO idea_reports(idea_id,reason,created_at) VALUES(?,?,?)', (idea_id, req.reason.value, now()))
            conn.commit()
    # Do not expose report IDs, counts or previous reports. Reports never hide
    # content automatically, and no IP, browser identifier or free text is stored.
    return {'status': 'received'}


water_ledger = WaterLedger()


@app.post('/api/idea/{idea_id}/water')
async def water_idea(idea_id: IdeaId, request: Request):
    """Anonymous appreciation: one counted reaction per connection, idea and UTC day."""
    client = client_key(request.client.host if request.client else None)
    day = utc_day()
    with closing(connect_db()) as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM ideas WHERE id = ? AND hidden = 0', (idea_id,)).fetchone() is None:
            raise HTTPException(status_code=404, detail='Idea not found')
        counted = water_ledger.first_today(client, idea_id, day)
        if counted:
            add_water(conn, idea_id, day)
        total = water_total(conn, idea_id)
        conn.commit()
    if counted:
        await broadcast_idea({'event': 'water', 'id': idea_id, 'water': total})
    return {'idea_id': idea_id, 'water': total, 'counted': counted}


def public_rows_by_id(conn, ids):
    if not ids:
        return {}
    rows = conn.execute(f"SELECT {PUBLIC_FIELDS} FROM ideas WHERE hidden = 0 AND id IN ({','.join('?' for _ in ids)})", ids)
    return {row['id']: dict(row) for row in rows}


@app.get('/api/discover')
async def discover(response: Response):
    with closing(connect_db()) as conn:
        conn.execute('BEGIN')
        response.headers['X-Board-Revision'] = str(board_revision(conn))
        sections = discover_ids(conn, MAX_DEPTH)
        rows = public_rows_by_id(conn, sorted({idea_id for ids in sections.values() for idea_id in ids}))
    return {name: [rows[idea_id] for idea_id in ids if idea_id in rows] for name, ids in sections.items()}


@app.get('/api/random')
async def random_idea():
    with closing(connect_db()) as conn:
        row = conn.execute(f'SELECT {PUBLIC_FIELDS} FROM ideas WHERE hidden = 0 ORDER BY RANDOM() LIMIT 1').fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail='The garden is empty')
    return dict(row)


@app.get('/api/mutations')
async def get_mutations():
    return CATALOGUE


preview_cache: OrderedDict[int, dict[str, str | None]] = OrderedDict()


def preview_rows(results, parent_content, existing=None):
    existing = existing or {}
    return [{'mutation': name, 'content': text, 'unchanged': text is not None and text.strip() == parent_content.strip(),
             'existing_id': existing.get(name)} for name, text in results.items()]


def check_preview_rate(request: Request):
    if not limiters['preview'].allow(client_key(request.client.host if request.client else None)):
        raise HTTPException(status_code=429, detail='Too many previews. Please try again shortly.', headers={'Retry-After': '30'})


@app.get('/api/idea/{idea_id}/preview')
async def preview_idea(idea_id: IdeaId, request: Request):
    """What every rule would produce from this idea; nothing is stored."""
    with closing(connect_db()) as conn:
        row = conn.execute('SELECT content FROM ideas WHERE id = ? AND hidden=0', (idea_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail='Idea not found')
        existing = {}
        for child in conn.execute('SELECT mutation, MIN(id) AS id FROM ideas WHERE parent_id = ? AND hidden=0 '
                                  "AND mutation != 'base' GROUP BY mutation", (idea_id,)):
            existing[child['mutation']] = child['id']
    results = preview_cache.get(idea_id)
    if results is None:
        check_preview_rate(request)
        results = await run_all(row['content'])
        # Stored ideas are immutable, so a computed preview stays valid.
        preview_cache[idea_id] = results
        while len(preview_cache) > PREVIEW_CACHE_SIZE:
            preview_cache.popitem(last=False)
    else:
        preview_cache.move_to_end(idea_id)
    return {'idea_id': idea_id, 'results': preview_rows(results, row['content'], existing)}


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=2000, strict=True)

    @model_validator(mode='after')
    def validate_text(self):
        try:
            self.content = clean_user_text(self.content)
        except PolicyError as exc:
            raise ValueError(str(exc)) from None
        return self


@app.post('/api/preview')
async def preview_draft(req: PreviewRequest):
    """Try every rule on a draft before publishing it; nothing is stored."""
    return {'results': preview_rows(await run_all(req.content), req.content)}


@app.websocket('/ws')
async def websocket_endpoint(websocket: WebSocket):
    if websocket.headers.get('origin') != PUBLIC_ORIGIN:
        await websocket.close(code=1008, reason='Origin not allowed')
        return
    address = client_key(websocket.client.host if websocket.client else None)
    if (len(clients) >= MAX_CLIENTS or sum(value == address for value in clients.values()) >= MAX_SOCKETS_PER_CLIENT
            or not socket_limiter.allow(address)):
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
