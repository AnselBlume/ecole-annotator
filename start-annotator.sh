#!/bin/bash

# === Command-line options ===
DEPLOY_MODE="host"  # Default to host mode (0.0.0.0)

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --local)
      DEPLOY_MODE="local"  # Local mode (127.0.0.1)
      shift
      ;;
    --host)
      DEPLOY_MODE="host"  # Host mode (0.0.0.0)
      shift
      ;;
    *)
      echo "Unknown option: $key"
      echo "Usage: $0 [--local|--host]"
      echo "  --local: Run on localhost only (127.0.0.1)"
      echo "  --host: Run on all interfaces (0.0.0.0) - this is the default"
      exit 1
      ;;
  esac
done

# === Config ===
CUDA_DEVICE="0"
CONDA_ENV_NAME="annotator"
BACKEND_DIR="backend"
FRONTEND_DIR="frontend"
LOG_DIR="logs"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$LOG_DIR/annotator_$TIMESTAMP.log"

# Set host based on deploy mode
if [ "$DEPLOY_MODE" = "local" ]; then
  HOST="127.0.0.1"
  HOSTNAME="localhost"
else
  HOST="0.0.0.0"
  HOSTNAME=$(hostname -f)
fi

echo "🌐 Running in $DEPLOY_MODE mode (Host: $HOST, Hostname: $HOSTNAME)"

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
FRONTEND_PORT=3015

echo "✅ Found backend port: $BACKEND_PORT"
echo "✅ Found frontend port: $FRONTEND_PORT"

# === Launch backend ===
echo "🚀 Starting FastAPI backend..."
cd "$BACKEND_DIR" || exit 1
CUDA_VISIBLE_DEVICES=$CUDA_DEVICE uvicorn main:app --host $HOST --port $BACKEND_PORT --reload &
BACKEND_PID=$!
cd ..

# === Write frontend .env file dynamically ===
echo "🌐 Setting backend URL in frontend .env file..."
echo "REACT_APP_BACKEND=http://$HOSTNAME:$BACKEND_PORT" > "$FRONTEND_DIR/.env.local"

# === Launch frontend ===
PUBLIC_URL=/partonomy-annotator

echo "🎨 Starting React frontend..."
cd "$FRONTEND_DIR" || exit 1
PORT=$FRONTEND_PORT HOST=$HOST PUBLIC_URL=$PUBLIC_URL npm start &
FRONTEND_PID=$!
cd ..

# === Trap cleanup ===
trap "echo '🛑 Shutting down...'; kill $BACKEND_PID $FRONTEND_PID $REDIS_PID; redis-cli shutdown; exit" SIGINT

echo ""
echo "==========================================="
echo "📡 Backend running at: http://$HOSTNAME:$BACKEND_PORT/docs"
echo "🖼️ Frontend running at: http://$HOSTNAME:$FRONTEND_PORT${PUBLIC_URL}"
echo ""
if [ "$DEPLOY_MODE" = "host" ]; then
  echo "🌍 Services accessible from: http://$HOSTNAME:$FRONTEND_PORT"
else
  echo "🔁 To view from other machines, use SSH tunnel:"
  echo "    ssh -N -L $BACKEND_PORT:localhost:$BACKEND_PORT -L $FRONTEND_PORT:localhost:$FRONTEND_PORT youruser@$(hostname -f)"
fi
echo "==========================================="

# Keep script running and logging
wait