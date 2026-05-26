# LLM Wiki

Wiki personale con OCR automatico e chat AI — completamente offline, zero servizi cloud.

**Stack**: FastAPI · Ollama (Qwen3) · pypdfium2 · Tesseract/EasyOCR/GOT-OCR2/Ollama-vision · BM25 · vanilla JS

---

## Prerequisiti

### Sistema operativo
- Windows 10/11, Linux (Ubuntu 20.04+), macOS 12+

### Hardware

| Componente | Minimo | Consigliato |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Storage | 6 GB liberi | 15 GB liberi |
| CPU | x86-64 qualsiasi | 8+ core |
| GPU | Non richiesta | NVIDIA ≥ 4 GB VRAM (CUDA) — 5–10x speedup |

### Software obbligatorio

| Software | Versione | Note |
|---|---|---|
| Python | ≥ 3.11 | [python.org](https://python.org) |
| Tesseract OCR | qualsiasi | + language pack `ita` + `eng` |
| Ollama | ≥ 0.3 | [ollama.com](https://ollama.com) |

### Connessione internet
Solo durante l'installazione (download modelli + pip). **Runtime: completamente offline.**

### Opzionale
- **NVIDIA GPU** + driver CUDA → TTFT 2–8s invece di 15–30s
- **EasyOCR**: `pip install easyocr` (~120 MB) per font non standard
- **GOT-OCR2**: `pip install transformers torch torchvision` (~580 MB) per layout complessi e tabelle
- **Ollama vision** (`minicpm-v`, ~5.5 GB) per OCR di massima qualità su manoscritti

---

## Avvio rapido

```bash
# 1. Avvia Ollama
ollama serve

# 2. Scarica i modelli (una volta sola)
ollama pull qwen3:8b      # chat/RAG — 5.2 GB
ollama pull qwen3:14b     # ingest OCR→wiki — 8.2 GB

# 3. Installa dipendenze Python
pip install -r backend/requirements.txt

# 4. Configura
cp .env.example .env       # modifica se necessario

# 5. Avvia
uvicorn backend.main:app --reload
```

Apri http://localhost:8000

> **Installazione guidata**: usa `.\install.ps1` (Windows) o `./install.sh` (Linux/macOS)
> per procedura interattiva che rileva hardware e seleziona i modelli ottimali.

---

## Funzionalità

- **Upload file**: PDF, immagini, `.txt`, `.md`, `.docx` — drag-drop o bottone
- **OCR automatico**: pypdfium2 (testo embedded) + Tesseract (scansionati/immagini)
- **Ingest wiki**: Qwen3 riassume con map-reduce e scrive `wiki/sources/YYYY-MM-DD_slug.md`
- **Chat RAG**: BM25 recupera passaggi rilevanti → Qwen3 streaming con citazione sorgenti
- **Semantic cache**: domande simili già viste → risposta istantanea (~0ms) senza chiamare il modello
- **Log stream**: UI mostra log ingest in tempo reale via SSE
- **Elimina file**: rimuove raw + wiki pages in cascade

---

## Architettura

```
Browser (frontend/)
    │
    ├── POST /api/files        → upload + trigger ingest
    ├── GET  /api/files        → lista file con status
    ├── POST /api/chat         → chat RAG (SSE streaming)
    └── GET  /api/logs/stream  → log ingest in tempo reale (SSE)
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
    raw/            ← file originali
    wiki/sources/   ← pagine markdown generate
    wiki/index.md   ← catalogo
    wiki/log.md     ← log operazioni
```

### Pipeline ingest

```
File upload
    → OCR Tier 1: pypdfium2 (testo embedded, istantaneo)
    → OCR Tier 2: Tesseract/EasyOCR/GOT-OCR2/Ollama-vision (scansioni)
                  ↳ parallel: ThreadPoolExecutor(max_workers=4) su ogni pagina
    → Dedup check: embed(primi 800 chars) → cosine sim con wiki esistenti
                   se similarity ≥ 0.95 → skip (contenuto già presente)
    → se doc ≤ 50k chars: 1 LLM call (ingest_model, max_tokens=800)
    → se doc > 50k chars: map-reduce
        map:    chat_model, max_tokens=200 per chunk (veloce)
        reduce: chat_model, max_tokens=700 (merge in wiki page)
    → write wiki/sources/YYYY-MM-DD_slug.md
    → BM25 index rebuild
```

### Tempi ingest stimati (CPU-only, qwen3:8b chat / qwen3:14b ingest)

| Documento | OCR | LLM | Totale |
|---|---|---|---|
| PDF testo 50 pag (1 chunk) | <1s | ~114s (800 tok @ 7t/s) | **~2 min** |
| PDF scansionato 50 pag | ~25s (4 thread) | ~114s | **~2.5 min** |
| PDF testo 200 pag (4 chunks) | <1s | map 4×29s + reduce 100s = 216s | **~4 min** |
| Duplicato contenuto | <1s | 0 (skip) | **<2s** |

### Pipeline chat RAG

```
Domanda utente
    → embed(query) via nomic-embed-text (~50ms)
    → Semantic cache check (cosine similarity ≥ 0.85)
        HIT:  risposta istantanea (~500ms totali)
        MISS: BM25 search (top_k=3, 300 chars/passage)
              → Build prompt → Ollama qwen3:8b streaming
              → Accumula response → store in semantic cache
    → SSE stream al browser
```

---

## Configurazione (`.env`)

`CHAT_MODEL_NAME`, `INGEST_MODEL_NAME` e `OCR_DEVICE` vengono **auto-rilevati** a ogni avvio in base all'hardware (VRAM GPU → RAM CPU). Il `.env` li sovrascrive se presenti.

| Variabile | Default | Descrizione |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Endpoint Ollama |
| `CHAT_MODEL_NAME` | _(auto-rilevato)_ | Modello chat/RAG — override manuale opzionale |
| `INGEST_MODEL_NAME` | _(auto-rilevato)_ | Modello ingest OCR→wiki — override manuale opzionale |
| `EMBED_MODEL_NAME` | `nomic-embed-text` | Modello embedding per semantic cache |
| `CACHE_SIMILARITY_THRESHOLD` | `0.85` | Soglia cosine similarity per cache hit |
| `CACHE_MAX_ENTRIES` | `500` | Max risposte memorizzate in cache |
| `OCR_BACKEND` | `tesseract` | Backend OCR: `tesseract` · `easyocr` · `ollama` |
| `OCR_MODEL_NAME` | `minicpm-v` | Vision model usato con `OCR_BACKEND=ollama` |
| `OCR_DEVICE` | _(auto-rilevato)_ | `cpu` o `cuda` — impostato in base alla GPU disponibile |
| `RAW_DIR` | `raw` | Cartella file sorgente |
| `WIKI_DIR` | `wiki` | Cartella wiki markdown |
| `TESSERACT_CMD` | _(PATH)_ | Path Tesseract se non in PATH |

Il log di avvio mostra il risultato del rilevamento:
```
Hardware: CPU-only RAM=15.3GB | chat=qwen3:8b ingest=qwen3:14b ocr_device=cpu (auto)
Hardware: GPU CUDA 12.0GB    | chat=qwen3:14b ingest=qwen3:32b-a3b ocr_device=cuda (auto)
```

---

## Selezione modelli per hardware

I due modelli **non** sono mai in memoria insieme (Ollama li carica su richiesta e scarica dopo 5 min idle).

`config.py` rileva hardware a ogni avvio (`nvidia-smi` per GPU, `wmic/proc` per RAM) e imposta i default. Il `.env` sovrascrive sempre.

### Con GPU NVIDIA (CUDA — consigliato)

Ollama rileva CUDA automaticamente. Nessuna config aggiuntiva — basta avere driver NVIDIA installati.

| VRAM GPU | CHAT_MODEL_NAME | INGEST_MODEL_NAME | Quantizzazione | Risposta chat |
|---|---|---|---|---|
| ≥ 24 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 1–3s |
| ≥ 12 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 2–5s |
| ≥ 8 GB | `qwen3:8b` | `qwen3:14b` | q5_K_M | 3–8s |
| ≥ 4 GB | `qwen3:4b` | `qwen3:8b` | q4_K_M | 5–12s |

Con GPU: `ollama pull qwen3:14b-q5_K_M` per qualità superiore in ingest.

### Senza GPU / CPU-only (AMD Windows, Intel iGPU, no GPU)

AMD su Windows e GPU integrate **non supportate** da Ollama per accelerazione.

| RAM disponibile | CHAT_MODEL_NAME | INGEST_MODEL_NAME | Risposta chat |
|---|---|---|---|
| ≤ 4 GB | `qwen3:1.7b` | `qwen3:1.7b` | 20–40s |
| 4–6 GB | `qwen3:1.7b` | `qwen3:4b` | 30–60s |
| 6–10 GB | `qwen3:4b` | `qwen3:8b` | 60–120s |
| 10–14 GB | `qwen3:4b` | `qwen3:14b` | 90–150s |
| 14–20 GB | `qwen3:8b` | `qwen3:14b` | 120–190s |
| > 20 GB | `qwen3:14b` | `qwen3:30b-a3b` | 150–300s |

---

## Struttura progetto

```
llm_wiki/
├── backend/
│   ├── main.py              ← FastAPI app, lifespan, router mount
│   ├── config.py            ← pydantic-settings
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
│       ├── ocr.py           ← pypdfium2 + Tesseract + python-docx
│       ├── ingest.py        ← map-reduce pipeline
│       ├── llm.py           ← httpx → Ollama
│       ├── search.py        ← BM25Okapi
│       └── watcher.py       ← watchdog su raw/
├── frontend/                ← vanilla JS + CSS
├── docs/
│   ├── architecture.md      ← diagrammi Mermaid
│   ├── install-slides.md    ← slide Marp installazione
│   └── install-slides.pdf   ← render PDF slide
├── tests/                   ← 36 pytest (no modelli richiesti)
├── launcher.py              ← ensure ollama serve + uvicorn
├── install.ps1              ← installer interattivo Windows
├── install.sh               ← installer interattivo Linux/macOS
└── .env.example
```

---

## OCR — backend e formati

### Confronto backend

| Backend | Qualità | Velocità | Peso | Hardware minimo | Ideale per |
|---|---|---|---|---|---|
| `tesseract` (default) | buona | veloce | ~50 MB | CPU, 4 GB RAM | scan puliti, uso quotidiano |
| `easyocr` | migliore | media | ~120 MB | CPU, 6 GB RAM | font non-standard, testo ruotato |
| `got_ocr2` | ottima | media | ~580 MB | CPU 8 GB RAM / GPU 4 GB VRAM | layout multi-colonna, tabelle, multilingua |
| `ollama` | massima | lenta | ~5.5 GB | GPU 8 GB VRAM (o CPU lento) | manoscritti, layout complessi |

> **GOT-OCR2** (`stepfun-ai/GOT-OCR-2.0-hf`, Apache 2.0): modello transformer ~580 MB, gestisce pagine intere con layout complessi, tabelle e testo multilingue — qualità superiore a EasyOCR senza richiedere GPU dedicata.

### Selezione consigliata per hardware

| Hardware disponibile | Backend consigliato |
|---|---|
| CPU ≤ 6 GB RAM | `tesseract` |
| CPU 6–14 GB RAM, documenti semplici | `easyocr` |
| CPU 8+ GB RAM, documenti complessi | `got_ocr2` |
| GPU 4+ GB VRAM | `got_ocr2` (GPU auto-detect) |
| GPU 8+ GB VRAM, massima qualità | `ollama` (minicpm-v) |

### Formati supportati

| Formato | Tier 1 (sempre) | Tier 2 (backend selezionato) |
|---|---|---|
| PDF con testo embedded | pypdfium2 (istantaneo) | — |
| PDF scansionato | pypdfium2 rasterize | Tesseract / EasyOCR / GOT-OCR2 / Ollama vision |
| PNG/JPG/TIFF/BMP/WebP | — | Tesseract / EasyOCR / GOT-OCR2 / Ollama vision |
| DOCX / DOC | python-docx | — |
| TXT / MD | Lettura UTF-8 | — |

### Installazione backend

```bash
# tesseract (default — sempre consigliato come base)
winget install UB-Mannheim.TesseractOCR                # Windows
sudo apt install tesseract-ocr tesseract-ocr-ita       # Linux

# easyocr (upgrade qualità, ~120 MB download automatico primo uso)
pip install easyocr
# .env: OCR_BACKEND=easyocr

# got_ocr2 (ottima qualità, layout complessi — ~580 MB download automatico primo uso)
pip install transformers torch torchvision
# .env: OCR_BACKEND=got_ocr2
# GPU NVIDIA rilevata automaticamente da torch/transformers

# ollama vision (massima qualità, 5.5 GB)
ollama pull minicpm-v
# .env: OCR_BACKEND=ollama
#       OCR_MODEL_NAME=minicpm-v
```

---

## Test

```bash
pytest tests/ -v
# 36 test, nessun modello o Ollama richiesti (tutto mockato)
```

---

## Multi-user Authentication

LLM Wiki includes a full JWT-based authentication system.

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

## Sicurezza

- Endpoint accessibili **solo da localhost** (default `127.0.0.1:8000`) — cambia `HOST=0.0.0.0` per LAN
- Path traversal bloccato su upload/download/delete via `Path.relative_to()`
- Upload limitato a 50 MB e a estensioni allow-listed
- Autenticazione JWT HttpOnly cookie — esporre su LAN/WAN richiede `JWT_SECURE_COOKIE=true` + HTTPS

---

## Documentazione

- `docs/architecture.md` — diagrammi Mermaid componenti, ingest, RAG, moduli
- `docs/install-slides.pdf` — slide installazione (renderizzabile con Marp)
