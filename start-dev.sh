#!/bin/sh
echo "Starting Python backend..."
PYTHON_CMD="python3"
if ! command -v $PYTHON_CMD >/dev/null 2>&1; then
    PYTHON_CMD="python"
fi

if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
fi
. venv/bin/activate
pip install -r agent_system/requirements.txt
uvicorn agent_system.api.main:app --host 127.0.0.1 --port 8000 &
echo "Starting Vite frontend..."
vite --port=3000 --host=0.0.0.0
