#!/bin/bash

# === Config ===
CONDA_ENV_NAME="annotator"
BACKEND_DIR="backend"
FRONTEND_DIR="frontend"
LOG_DIR="logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/annotator_$TIMESTAMP.log"

# === Helper: find a free port ===
find_free_port() {
  python -c 'import socket; s=socket.socket(); s.bind(("", 0)); print(s.getsockname()[1]); s.close()'
}

# === Prepare logging ===
mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "🗒️ Logging to $LOG_FILE"

# === Conda activation ===
echo "🐍 Activating Conda environment: $CONDA_ENV_NAME"
. ~/.bashrc
ca "$CONDA_ENV_NAME"

# === Start Redis server ===
echo "🔄 Starting Redis server..."
redis-server --daemonize yes
REDIS_PID=$(pgrep -f "redis-server")

if [ -z "$REDIS_PID" ]; then
  echo "❌ Failed to start Redis."
  exit 1
else
  echo "✅ Redis started with PID $REDIS_PID"
fi

# === Find free ports ===
BACKEND_PORT=$(find_free_port)
FRONTEND_PORT=$(find_free_port)

echo "✅ Found backend port: $BACKEND_PORT"
echo "✅ Found frontend port: $FRONTEND_PORT"

# === Launch backend ===
echo "🚀 Starting FastAPI backend..."
cd "$BACKEND_DIR" || exit 1
uvicorn main:app --host 127.0.0.1 --port $BACKEND_PORT --reload &
BACKEND_PID=$!
cd ..

# === Write frontend .env file dynamically ===
echo "🌐 Setting backend URL in frontend .env file..."
echo "REACT_APP_BACKEND=http://localhost:$BACKEND_PORT" > "$FRONTEND_DIR/.env.local"

# === Launch frontend ===
echo "🎨 Starting React frontend..."
cd "$FRONTEND_DIR" || exit 1
PORT=$FRONTEND_PORT npm start &
FRONTEND_PID=$!
cd ..

# === Trap cleanup ===
trap "echo '🛑 Shutting down...'; kill $BACKEND_PID $FRONTEND_PID $REDIS_PID; redis-cli shutdown; exit" SIGINT

echo ""
echo "==========================================="
echo "📡 Backend running at: http://localhost:$BACKEND_PORT"
echo "🖼️ Frontend running at: http://localhost:$FRONTEND_PORT"
echo ""
echo "🔁 To view locally, use SSH tunnel:"
echo "    ssh -N -L $BACKEND_PORT:localhost:$BACKEND_PORT -L $FRONTEND_PORT:localhost:$FRONTEND_PORT youruser@your.remote.server"
echo "==========================================="

# Keep script running and logging
wait