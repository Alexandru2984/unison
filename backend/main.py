import os
import json
import asyncio
import subprocess
import logging
from typing import Optional
from fastapi import FastAPI, WebSocket, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
import sqlite3
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()} | Body: {await request.body()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "body": str(await request.body())},
    )

DB_PATH = os.path.join(os.path.dirname(__file__), "evolution.db")

# Store active websockets
clients = set()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS ideas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            parent_id INTEGER,
            content TEXT,
            mutation TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

class IdeaRequest(BaseModel):
    content: Optional[str] = ""
    parent_id: Optional[int] = None
    mutation: str = "base"

async def broadcast_idea(idea):
    for client in clients:
        try:
            await client.send_json(idea)
        except Exception as e:
            logger.error(f"Failed to broadcast: {e}")

@app.post("/api/idea")
async def create_idea(req: IdeaRequest):
    new_content = req.content
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if req.mutation != "base":
        source_content = req.content
        if req.parent_id is not None:
            c.execute("SELECT content FROM ideas WHERE id = ?", (req.parent_id,))
            row = c.fetchone()
            if row:
                source_content = row[0]
        
        if not source_content:
            source_content = ""

        try:
            # Call Unison Engine using subprocess
            result = subprocess.run(
                ["/home/micu/unisonTrying/ucm-bin/ucm-bin", "run.compiled", "/home/micu/unisonTrying/unison/evolution.uc", req.mutation, source_content],
                capture_output=True, text=True, check=True
            )
            output = result.stdout.strip()
            try:
                unison_json = json.loads(output)
                new_content = unison_json.get("result", output)
            except json.JSONDecodeError:
                new_content = output
        except subprocess.CalledProcessError as e:
            conn.close()
            logger.error(f"Unison CLI failed: {e.stderr}")
            raise HTTPException(status_code=500, detail=f"Unison CLI failed: {e.stderr}")
    
    c.execute("INSERT INTO ideas (parent_id, content, mutation) VALUES (?, ?, ?)",
              (req.parent_id, new_content, req.mutation))
    idea_id = c.lastrowid
    conn.commit()
    conn.close()
    
    idea_obj = {"id": idea_id, "content": new_content, "parent_id": req.parent_id, "mutation": req.mutation}
    await broadcast_idea(idea_obj)
    
    return idea_obj

@app.get("/api/idea")
async def get_ideas():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, parent_id, content, mutation FROM ideas")
    rows = c.fetchall()
    conn.close()
    
    ideas = [{"id": r[0], "parent_id": r[1], "content": r[2], "mutation": r[3]} for r in rows]
    return ideas

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    clients.add(websocket)
    logger.info("New WebSocket connection")
    try:
        while True:
            await websocket.receive_text()
    except Exception as e:
        logger.info(f"WebSocket disconnected: {e}")
    finally:
        if websocket in clients:
            clients.remove(websocket)
