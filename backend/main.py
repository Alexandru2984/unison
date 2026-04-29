import os
import json
import asyncio
import subprocess
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "evolution.db"

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
    content: str
    parent_id: int = None
    mutation: str = "base"

async def broadcast_idea(idea):
    for client in clients:
        try:
            await client.send_json(idea)
        except:
            pass

@app.post("/api/idea")
async def create_idea(req: IdeaRequest):
    new_content = req.content
    
    if req.mutation != "base":
        try:
            # Call Unison Engine using subprocess
            result = subprocess.run(
                ["/home/micu/unisonTrying/ucm-bin/ucm-bin", "run.compiled", "/home/micu/unisonTrying/unison/evolution.uc", req.mutation, req.content],
                capture_output=True, text=True, check=True
            )
            new_content = result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise HTTPException(status_code=500, detail=f"Unison CLI failed: {e.stderr}")
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
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
    try:
        while True:
            await websocket.receive_text()
    except:
        clients.remove(websocket)
