#!/bin/bash
PORT=8088

echo "Starting backend on port $PORT"
cd /home/micu/unisonTrying/backend
source .venv/bin/activate
exec uvicorn main:app --host 127.0.0.1 --port $PORT
