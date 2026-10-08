import asyncio
import json
import logging
import os
import sqlite3
from contextlib import closing
from enum import StrEnum
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator


PROJECT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_DIR / ".env", override=False)


def bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


DB_PATH = Path(os.getenv("DB_PATH", Path(__file__).resolve().parent / "evolution.db")).resolve()
UNISON_BIN = Path(os.getenv("UNISON_BIN", PROJECT_DIR / "ucm-bin" / "ucm-bin")).resolve()
UNISON_PROGRAM = Path(os.getenv("UNISON_PROGRAM", PROJECT_DIR / "unison" / "evolution.uc")).resolve()
PUBLIC_ORIGIN = os.getenv("PUBLIC_ORIGIN", "https://unison.micutu.com").rstrip("/")
MAX_IDEAS = bounded_int("MAX_IDEAS", 10_000, 100, 100_000)
MAX_RESULTS = bounded_int("MAX_RESULTS", 500, 10, 2_000)
MUTATION_TIMEOUT_SECONDS = bounded_int("MUTATION_TIMEOUT_SECONDS", 5, 1, 30)
MAX_RESULT_CHARACTERS = 4_096

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

docs_enabled = os.getenv("ENABLE_API_DOCS", "").lower() == "true"
app = FastAPI(
    docs_url="/docs" if docs_enabled else None,
    redoc_url="/redoc" if docs_enabled else None,
    openapi_url="/openapi.json" if docs_enabled else None,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {
            "location": error.get("loc", ()),
            "message": error.get("msg", "Invalid value"),
            "type": error.get("type", "value_error"),
        }
        for error in exc.errors()
    ]
    logger.warning("Request validation failed path=%s errors=%d", request.url.path, len(errors))
    return JSONResponse(status_code=422, content={"detail": errors})


def connect_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_db()) as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id INTEGER,
                content TEXT NOT NULL,
                mutation TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()


class Mutation(StrEnum):
    BASE = "base"
    EXPAND = "expand"
    REPHRASE = "rephrase"
    MUTATE_KEYWORDS = "mutate_keywords"
    SYNTHESIZE = "synthesize"


class IdeaRequest(BaseModel):
    content: str = Field(default="", max_length=2_000)
    parent_id: int | None = Field(default=None, gt=0)
    mutation: Mutation = Mutation.BASE

    @model_validator(mode="after")
    def validate_operation(self):
        self.content = self.content.strip()
        if self.mutation == Mutation.BASE and not self.content:
            raise ValueError("Base ideas require content")
        if self.mutation != Mutation.BASE and self.parent_id is None:
            raise ValueError("Mutations require a parent idea")
        return self


clients: set[WebSocket] = set()
idea_lock = asyncio.Lock()


async def broadcast_idea(idea: dict) -> None:
    disconnected = []
    for client in tuple(clients):
        try:
            await client.send_json(idea)
        except Exception:
            disconnected.append(client)
    for client in disconnected:
        clients.discard(client)


async def run_mutation(mutation: Mutation, content: str) -> str:
    if not UNISON_BIN.is_file() or not UNISON_PROGRAM.is_file():
        logger.error("Unison runtime files are unavailable")
        raise HTTPException(status_code=503, detail="Mutation engine unavailable")

    process = await asyncio.create_subprocess_exec(
        str(UNISON_BIN),
        "run.compiled",
        str(UNISON_PROGRAM),
        mutation.value,
        content,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _stderr = await asyncio.wait_for(process.communicate(), timeout=MUTATION_TIMEOUT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.communicate()
        logger.warning("Unison mutation timed out mutation=%s", mutation.value)
        raise HTTPException(status_code=504, detail="Mutation engine timed out") from None

    if process.returncode != 0:
        logger.error("Unison mutation failed mutation=%s returncode=%d", mutation.value, process.returncode)
        raise HTTPException(status_code=502, detail="Mutation engine failed")

    output = stdout.decode("utf-8", errors="replace").strip()
    try:
        payload = json.loads(output)
        result = payload.get("result")
    except (json.JSONDecodeError, AttributeError):
        result = output

    if not isinstance(result, str) or not result or len(result) > MAX_RESULT_CHARACTERS:
        logger.error("Unison mutation returned an invalid result mutation=%s", mutation.value)
        raise HTTPException(status_code=502, detail="Mutation engine returned an invalid result")
    return result


@app.get("/api/health")
async def health():
    with closing(connect_db()) as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@app.post("/api/idea", status_code=201)
async def create_idea(req: IdeaRequest):
    async with idea_lock:
        with closing(connect_db()) as conn:
            if conn.execute("SELECT COUNT(*) FROM ideas").fetchone()[0] >= MAX_IDEAS:
                raise HTTPException(status_code=507, detail="Idea capacity reached")

            new_content = req.content
            if req.mutation != Mutation.BASE:
                row = conn.execute("SELECT content FROM ideas WHERE id = ?", (req.parent_id,)).fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Parent idea not found")
                new_content = await run_mutation(req.mutation, row["content"])

            cursor = conn.execute(
                "INSERT INTO ideas (parent_id, content, mutation) VALUES (?, ?, ?)",
                (req.parent_id, new_content, req.mutation.value),
            )
            idea_id = cursor.lastrowid
            conn.commit()

    idea = {
        "id": idea_id,
        "content": new_content,
        "parent_id": req.parent_id,
        "mutation": req.mutation.value,
    }
    await broadcast_idea(idea)
    return idea


@app.get("/api/idea")
async def get_ideas():
    with closing(connect_db()) as conn:
        rows = conn.execute(
            "SELECT id, parent_id, content, mutation FROM ideas ORDER BY id DESC LIMIT ?",
            (MAX_RESULTS,),
        ).fetchall()
    rows.reverse()
    return [dict(row) for row in rows]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    if websocket.headers.get("origin") != PUBLIC_ORIGIN:
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await websocket.accept()
    clients.add(websocket)
    try:
        while True:
            message = await websocket.receive_text()
            if len(message) > 1_024:
                await websocket.close(code=1009, reason="Message too large")
                return
    except Exception:
        pass
    finally:
        clients.discard(websocket)
