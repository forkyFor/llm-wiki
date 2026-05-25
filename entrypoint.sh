#!/bin/bash
set -e

# ── Ollama ────────────────────────────────────────────────────────────────────
which ollama || curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
for i in $(seq 1 30); do
    sleep 2
    curl -sf http://localhost:11434/api/tags > /dev/null 2>&1 && break
done
MODEL_TAG="${MODEL_NAME:-qwen3:14b}"
ollama list | grep -q "$MODEL_TAG" || ollama pull "$MODEL_TAG"
export OLLAMA_URL="http://localhost:11434"

echo "[SETUP] Avvio LLM Wiki..."
exec uvicorn backend.main:app --host 0.0.0.0 --port 8000
