FROM python:3.11-slim

WORKDIR /app

# System deps for pypdfium2, PIL, curl (healthcheck in ollama)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY wiki/ ./wiki/
COPY instructions.md ./
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Default model path (overridden by docker-compose env)
ENV GLM_OCR_MODEL_PATH=/app/models/glm-ocr

EXPOSE 8000

# entrypoint.sh handles model download then starts uvicorn
ENTRYPOINT ["/app/entrypoint.sh"]
