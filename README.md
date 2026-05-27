# LLM Wiki

Offline personal wiki with automatic OCR and AI chat — no cloud, no external services.

**Stack**: FastAPI · Ollama (Qwen3) · pypdfium2 · Tesseract/EasyOCR/GOT-OCR2/Ollama-vision · BM25 · vanilla JS

---

## Prerequisites

### Operating system
- Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+

### Hardware

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Storage | 6 GB free | 15 GB free |
| CPU | any x86-64 | 8+ cores |
| GPU | not required | NVIDIA ≥ 4 GB VRAM (CUDA) — 5–10x speedup |

### Required software

| Software | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | [python.org](https://python.org) |
| Tesseract OCR | any | + language packs for your language |
| Ollama | ≥ 0.3 | [ollama.com](https://ollama.com) |

### Internet connection
Required only during installation (model downloads + pip). **Runtime: fully offline.**

### Optional
- **NVIDIA GPU** + CUDA drivers → TTFT 2–8s instead of 15–30s
- **EasyOCR**: `pip install easyocr` (~120 MB) for non-standard fonts
- **GOT-OCR2**: `pip install transformers torch torchvision` (~580 MB) for complex layouts and tables
- **Ollama vision** (`minicpm-v`, ~5.5 GB) for highest-quality OCR on manuscripts

---

## Quick start

```bash
# 1. Start Ollama
ollama serve

# 2. Download models (once)
ollama pull qwen3:8b      # chat/RAG — 5.2 GB
ollama pull qwen3:14b     # ingest OCR→wiki — 8.2 GB

# 3. Install Python dependencies
pip install -r backend/requirements.txt

# 4. Configure
cp .env.example .env       # edit if needed

# 5. Start
uvicorn backend.main:app --reload
```

Open http://localhost:8000

> **Guided install**: use `.\install.ps1` (Windows) or `./install.sh` (Linux/macOS)
> for an interactive setup that detects your hardware and selects optimal models.

---

## Features

- **File upload**: PDF, images, `.txt`, `.md`, `.docx` — drag-drop or button
- **Automatic OCR**: pypdfium2 (embedded text) + Tesseract/EasyOCR/GOT-OCR2 (scanned pages)
- **Wiki ingest**: Qwen3 summarizes with map-reduce and writes `wiki/sources/YYYY-MM-DD_slug.md`
- **RAG chat**: BM25 retrieves relevant passages → Qwen3 streaming with source citations
- **Semantic cache**: similar previously seen questions → instant response (~0ms) without calling the model
- **Log stream**: UI shows ingest logs in real time via SSE
- **Delete files**: removes raw + wiki pages in cascade

---

## Architecture

```
Browser (frontend/)
    │
    ├── POST /api/files        → upload + trigger ingest
    ├── GET  /api/files        → file list with status
    ├── POST /api/chat         → RAG chat (SSE streaming)
    └── GET  /api/logs/stream  → ingest logs in real time (SSE)
         │
    FastAPI (backend/)
         │
    ┌────┴────────────────────────┐
    │  services/                  │
    │  ├── ocr.py    pypdfium2+  │
    │  │             Tesseract   │
    │  ├── ingest.py map-reduce  │── Ollama :11434
    │  ├── llm.py    httpx       │   qwen3:8b  (chat)
    │  ├── search.py BM25Okapi   │   qwen3:14b (ingest)
    │  └── watcher.py watchdog   │
    └─────────────────────────────┘
         │
    raw/            ← source files
    wiki/sources/   ← generated markdown pages
    wiki/index.md   ← catalog
    wiki/log.md     ← operation log
```

### Ingest pipeline

```
File upload
    → OCR Tier 1: pypdfium2 (embedded text, instant)
    → OCR Tier 2: Tesseract/EasyOCR/GOT-OCR2/Ollama-vision (scanned pages)
                  ↳ parallel: ThreadPoolExecutor(max_workers=4) per page
    → Dedup check: embed(first 800 chars) → cosine sim against existing wiki
                   if similarity ≥ 0.95 → skip (duplicate content)
    → if doc ≤ 50k chars: 1 LLM call (ingest_model, max_tokens=800)
    → if doc > 50k chars: map-reduce
        map:    chat_model, max_tokens=200 per chunk (fast)
        reduce: chat_model, max_tokens=700 (merge into wiki page)
    → write wiki/sources/YYYY-MM-DD_slug.md
    → BM25 index rebuild
```

### Estimated ingest times (CPU-only, qwen3:8b chat / qwen3:14b ingest)

| Document | OCR | LLM | Total |
|---|---|---|---|
| 50-page text PDF (1 chunk) | <1s | ~114s (800 tok @ 7t/s) | **~2 min** |
| 50-page scanned PDF | ~25s (4 threads) | ~114s | **~2.5 min** |
| 200-page text PDF (4 chunks) | <1s | map 4×29s + reduce 100s = 216s | **~4 min** |
| Duplicate content | <1s | 0 (skip) | **<2s** |

### RAG chat pipeline

```
User question
    → embed(query) via nomic-embed-text (~50ms)
    → Semantic cache check (cosine similarity ≥ 0.85)
        HIT:  instant response (~500ms total)
        MISS: BM25 search (top_k=3, 300 chars/passage)
              → Build prompt → Ollama qwen3:8b streaming
              → Accumulate response → store in semantic cache
    → SSE stream to browser
```

---

## Configuration (`.env`)

`CHAT_MODEL_NAME`, `INGEST_MODEL_NAME`, and `OCR_DEVICE` are **auto-detected** at every startup based on hardware (GPU VRAM → CPU RAM). The `.env` file overrides them when set.

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `CHAT_MODEL_NAME` | _(auto-detected)_ | Chat/RAG model — optional manual override |
| `INGEST_MODEL_NAME` | _(auto-detected)_ | Ingest OCR→wiki model — optional manual override |
| `EMBED_MODEL_NAME` | `nomic-embed-text` | Embedding model for semantic cache |
| `CACHE_SIMILARITY_THRESHOLD` | `0.85` | Cosine similarity threshold for cache hit |
| `CACHE_MAX_ENTRIES` | `500` | Max cached responses |
| `OCR_BACKEND` | `tesseract` | OCR backend: `tesseract` · `easyocr` · `got_ocr2` · `ollama` |
| `OCR_MODEL_NAME` | `minicpm-v` | Vision model used with `OCR_BACKEND=ollama` |
| `OCR_DEVICE` | _(auto-detected)_ | `cpu` or `cuda` — set based on available GPU |
| `RAW_DIR` | `raw` | Source files directory |
| `WIKI_DIR` | `wiki` | Wiki markdown directory |
| `TESSERACT_CMD` | _(PATH)_ | Tesseract path if not in PATH |

Startup log shows the detection result:
```
Hardware: CPU-only RAM=15.3GB | chat=qwen3:8b ingest=qwen3:14b ocr_device=cpu (auto)
Hardware: GPU CUDA 12.0GB    | chat=qwen3:14b ingest=qwen3:32b-a3b ocr_device=cuda (auto)
```

---

## Hardware-adaptive model selection

The two models are **never** in memory at the same time (Ollama loads on demand and unloads after 5 min idle).

`config.py` detects hardware at every startup (`nvidia-smi` for GPU, `wmic`/`/proc/meminfo` for RAM) and sets defaults. `.env` always overrides.

### With NVIDIA GPU (CUDA — recommended)

Ollama detects CUDA automatically. No extra configuration — just have NVIDIA drivers installed.

| GPU VRAM | CHAT_MODEL_NAME | INGEST_MODEL_NAME | Quantization | Chat response |
|---|---|---|---|---|
| ≥ 24 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 1–3s |
| ≥ 12 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 2–5s |
| ≥ 8 GB | `qwen3:8b` | `qwen3:14b` | q5_K_M | 3–8s |
| ≥ 4 GB | `qwen3:4b` | `qwen3:8b` | q4_K_M | 5–12s |

With GPU: `ollama pull qwen3:14b-q5_K_M` for higher ingest quality.

### Without GPU / CPU-only (AMD on Windows, Intel iGPU, no GPU)

AMD on Windows and integrated GPUs are **not supported** by Ollama for acceleration.

| Available RAM | CHAT_MODEL_NAME | INGEST_MODEL_NAME | Chat response |
|---|---|---|---|
| ≤ 4 GB | `qwen3:1.7b` | `qwen3:1.7b` | 20–40s |
| 4–6 GB | `qwen3:1.7b` | `qwen3:4b` | 30–60s |
| 6–10 GB | `qwen3:4b` | `qwen3:8b` | 60–120s |
| 10–14 GB | `qwen3:4b` | `qwen3:14b` | 90–150s |
| 14–20 GB | `qwen3:8b` | `qwen3:14b` | 120–190s |
| > 20 GB | `qwen3:14b` | `qwen3:30b-a3b` | 150–300s |

---

## Project structure

```
llm_wiki/
├── backend/
│   ├── main.py              ← FastAPI app, lifespan, router mount
│   ├── config.py            ← pydantic-settings, hardware auto-detection
│   ├── log_stream.py        ← SSELogHandler
│   ├── auth/
│   │   ├── db.py            ← SQLite users (asyncio + run_in_executor)
│   │   ├── crypto.py        ← PBKDF2 + HS256 JWT (stdlib only)
│   │   ├── middleware.py    ← JWT cookie AuthMiddleware
│   │   ├── dependencies.py  ← get_current_user, require_admin
│   │   ├── routers.py       ← /api/auth/* endpoints
│   │   └── bootstrap.py     ← first-run admin creation
│   ├── routers/
│   │   ├── files.py         ← upload / list / download / delete
│   │   ├── chat.py          ← RAG chat SSE
│   │   └── logs.py          ← log stream SSE
│   └── services/
│       ├── ocr.py           ← pypdfium2 + Tesseract/EasyOCR/GOT-OCR2
│       ├── ingest.py        ← map-reduce pipeline
│       ├── llm.py           ← httpx → Ollama
│       ├── search.py        ← BM25Okapi
│       └── watcher.py       ← watchdog on raw/
├── frontend/                ← vanilla JS + CSS
├── docs/
│   ├── architecture.md      ← Mermaid diagrams
│   ├── install-slides.md    ← Marp slides
│   └── install-slides.pdf   ← rendered PDF
├── tests/                   ← pytest (no models required)
├── launcher.py              ← ensure ollama serve + uvicorn
├── install.ps1              ← interactive installer for Windows
├── install.sh               ← interactive installer for Linux/macOS
└── .env.example
```

---

## OCR backends

### Comparison

| Backend | Quality | Speed | Size | Min hardware | Best for |
|---|---|---|---|---|---|
| `tesseract` (default) | good | fast | ~50 MB | CPU, 4 GB RAM | clean scans, daily use |
| `easyocr` | better | medium | ~120 MB | CPU, 6 GB RAM | non-standard fonts, rotated text |
| `got_ocr2` | great | medium | ~580 MB | CPU 8 GB RAM / GPU 4 GB VRAM | multi-column layouts, tables, multilingual |
| `ollama` | best | slow | ~5.5 GB | GPU 8 GB VRAM (or slow CPU) | manuscripts, complex layouts |

> **GOT-OCR2** (`stepfun-ai/GOT-OCR-2.0-hf`, Apache 2.0): ~580 MB transformer model, handles full pages with complex layouts, tables, and multilingual text — better than EasyOCR without requiring a dedicated GPU.

### Recommended by hardware

| Available hardware | Recommended backend |
|---|---|
| CPU ≤ 6 GB RAM | `tesseract` |
| CPU 6–14 GB RAM, simple documents | `easyocr` |
| CPU 8+ GB RAM, complex documents | `got_ocr2` |
| GPU 4+ GB VRAM | `got_ocr2` (GPU auto-detect) |
| GPU 8+ GB VRAM, best quality | `ollama` (minicpm-v) |

### Supported formats

| Format | Tier 1 (always) | Tier 2 (selected backend) |
|---|---|---|
| PDF with embedded text | pypdfium2 (instant) | — |
| Scanned PDF | pypdfium2 rasterize | Tesseract / EasyOCR / GOT-OCR2 / Ollama vision |
| PNG/JPG/TIFF/BMP/WebP | — | Tesseract / EasyOCR / GOT-OCR2 / Ollama vision |
| DOCX / DOC | python-docx | — |
| TXT / MD | UTF-8 read | — |

### Backend installation

```bash
# tesseract (default — always recommended as base)
winget install UB-Mannheim.TesseractOCR                # Windows
sudo apt install tesseract-ocr tesseract-ocr-eng       # Linux

# easyocr (~120 MB auto-download on first use)
pip install easyocr
# .env: OCR_BACKEND=easyocr

# got_ocr2 (complex layouts — ~580 MB auto-download on first use)
pip install transformers torch torchvision
# .env: OCR_BACKEND=got_ocr2
# NVIDIA GPU auto-detected by torch/transformers

# ollama vision (best quality, 5.5 GB)
ollama pull minicpm-v
# .env: OCR_BACKEND=ollama
#       OCR_MODEL_NAME=minicpm-v
```

---

## Tests

```bash
pytest tests/ -v
# no models or Ollama required (all mocked)
```

---

## Multi-user Authentication

### First run

On first startup with no users in the database, an admin account is auto-created:
- If `ADMIN_USERNAME` / `ADMIN_PASSWORD` are set in `.env`, those credentials are used.
- Otherwise a random password is generated and printed in the startup log — save it.

### User management

Only admin users can create or delete accounts. Access the admin panel at `/admin.html`.

### Shared data model

All wiki content is **shared across all users**. The `raw/` and `wiki/` directories are global — any authenticated user can upload, delete, and query documents. The `data/users.db` SQLite database stores only identity information (credentials, roles, timestamps) and has no relation to document storage. The BM25 search index, semantic cache, and Ollama LLM services are global singletons shared across all sessions.

### Auth configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DATA_DIR` | `data` | Directory for `users.db` SQLite database |
| `JWT_SECRET` | _(auto-generated)_ | HMAC key for JWT signing — set for stable sessions across restarts |
| `JWT_EXPIRE_HOURS` | `24` | Session duration in hours |
| `JWT_SECURE_COOKIE` | `false` | Set to `true` only when serving over HTTPS |
| `ADMIN_USERNAME` | `admin` | Admin username for first-run bootstrap |
| `ADMIN_PASSWORD` | _(auto-generated)_ | Admin password — if empty, a random one is generated and logged |

### Security

- JWT stored in `HttpOnly` + `SameSite=Strict` cookie — not accessible from JavaScript
- Passwords hashed with PBKDF2-HMAC-SHA256, 480,000 iterations (OWASP 2024)
- No new Python dependencies — stdlib only (`sqlite3`, `hashlib`, `hmac`, `secrets`)
- Last admin account cannot be deleted

---

## Security notes

- Endpoints bound to localhost by default (`127.0.0.1:8000`) — set `HOST=0.0.0.0` to expose on LAN
- Path traversal blocked on upload/download/delete via `Path.relative_to()`
- Upload limited to 50 MB and an allow-listed set of extensions
- Exposing on LAN/WAN requires `JWT_SECURE_COOKIE=true` + HTTPS

---

## Documentation

- `docs/architecture.md` — Mermaid component, ingest, RAG, and module diagrams
- `docs/install-slides.pdf` — installation slides (renderable with Marp)
