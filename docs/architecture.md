# LLM Wiki — Architettura

## 1. Componenti e interazioni

```mermaid
graph LR
  subgraph Browser
    UI["Frontend\napp.js"]
  end

  subgraph FastAPI["FastAPI :8000"]
    FILES["routers/files.py\nGET · POST · DELETE /api/files"]
    CHAT["routers/chat.py\nPOST /api/chat"]
    LOGS["routers/logs.py\nGET /api/logs/stream"]
    INGEST["services/ingest.py\nmap-reduce + dedup"]
    OCR["services/ocr.py\nThreadPoolExecutor(4)"]
    LLM["services/llm.py\n/api/chat native"]
    EMBED["services/embeddings.py\n/api/embed"]
    CACHE["services/cache.py\nSemanticCache\ncosine sim ≥ 0.85"]
    SEARCH["services/search.py\nBM25Okapi"]
    WATCHER["services/watcher.py\nWatchdog"]
    LOGSTREAM["log_stream.py\nSSELogHandler"]
  end

  subgraph External["Servizi Esterni"]
    OLLAMA["Ollama :11434\nqwen3:8b (chat)\nqwen3:14b (ingest)\nnomic-embed-text (cache)\nminicpm-v (OCR vision, opzionale)"]
    TESS["Tesseract OCR\nita+eng (default)"]
    EASYOCR["EasyOCR\n(opzionale, upgrade)"]
    GOTOCR["GOT-OCR2\nstepfun-ai ~580MB\n(opzionale, layout complessi)"]
  end

  subgraph FS["File System"]
    RAW["raw/"]
    WIKI["wiki/sources/"]
    IDX["wiki/index.md"]
  end

  UI -->|"POST /api/files"| FILES
  UI -->|"POST /api/chat SSE"| CHAT
  UI -->|"GET /api/logs/stream SSE"| LOGS
  UI -->|"GET /api/files ogni 5s"| FILES

  FILES --> INGEST
  FILES <--> RAW

  CHAT --> EMBED
  EMBED --> CACHE
  CACHE -->|"HIT: risposta istantanea"| CHAT
  CACHE -->|"MISS: procedi"| SEARCH
  CHAT --> SEARCH
  CHAT --> LLM
  EMBED --> OLLAMA

  INGEST --> OCR
  INGEST --> LLM
  INGEST --> SEARCH
  INGEST <--> WIKI
  INGEST <--> IDX

  OCR --> TESS
  OCR -.->|"OCR_BACKEND=easyocr"| EASYOCR
  OCR -.->|"OCR_BACKEND=got_ocr2"| GOTOCR
  OCR -.->|"OCR_BACKEND=ollama"| OLLAMA
  LLM --> OLLAMA

  WATCHER -->|"on_created\ndebounce 2s"| INGEST
  WATCHER -.->|"monitora"| RAW

  LOGS --- LOGSTREAM
```

---

## 2. Pipeline di ingest (file → wiki)

```mermaid
sequenceDiagram
  actor User
  participant FE as Frontend
  participant API as FastAPI
  participant OCR as ocr.py
  participant LLM as "Ollama\n(qwen3)"
  participant FS as "wiki/"

  User->>FE: Drag & drop documento
  FE->>API: POST /api/files (multipart)
  API->>FS: salva raw/file.pdf
  API-->>FE: {status: "pending"}
  API->>API: asyncio.create_task(ingest)

  note over API,FS: Pipeline asincrona (~2–4 min su CPU)

  API->>OCR: extract_text(raw/file.pdf)
  alt PDF con testo embedded (≥ 50 chars)
    OCR-->>API: Tier 1 — pypdfium2 (istantaneo)
  else PDF scansionato o immagine
    OCR->>OCR: rasterizza pagine a 2x
    note over OCR: ThreadPoolExecutor(4) — OCR parallelo
    OCR->>OCR: Tesseract/EasyOCR/Ollama-vision (4 pag. contemporaneamente)
    OCR-->>API: Tier 2 — testo estratto
  else DOCX/DOC
    OCR-->>API: Tier 3 — python-docx
  end

  API->>LLM: embed(testo[:800]) — dedup check
  LLM-->>API: embedding vector
  alt Contenuto già presente (cosine sim ≥ 0.95)
    API-->>FE: skip — duplicato rilevato
  else Nuovo documento

    alt Documento breve (≤ 50k chars)
      API->>LLM: /api/chat {model: ingest_model, max_tokens: 800}
      LLM-->>API: markdown con frontmatter YAML
    else Documento lungo (> 50k chars) — map-reduce
      loop ogni chunk 50k chars (overlap 1k)
        API->>LLM: /api/chat {model: chat_model, max_tokens: 200}
        LLM-->>API: summary parziale
      end
      API->>LLM: /api/chat merge {model: chat_model, max_tokens: 700}
      LLM-->>API: markdown con frontmatter YAML
    end

    API->>FS: write wiki/sources/YYYY-MM-DD_slug.md
    API->>FS: update wiki/index.md
    API->>API: search.rebuild_index()
    API-->>FE: done
  end
```

---

## 3. Chat con RAG (BM25 + Ollama)

```mermaid
sequenceDiagram
  actor User
  participant FE as Frontend
  participant CHAT as "chat.py"
  participant BM25 as "search.py\nBM25Okapi"
  participant LLM as "Ollama\n(qwen3)"

  User->>FE: digita domanda + invio
  FE->>CHAT: POST /api/chat\n{message, history}

  CHAT->>BM25: search(message, top_k=5)
  BM25->>BM25: tokenize query\nget_scores() su tutti i doc
  BM25-->>CHAT: [SearchResult(passage 800 chars, source_file)]

  CHAT->>CHAT: build system prompt\ncon contesto wiki

  CHAT->>LLM: POST /v1/chat/completions\n{stream: true, temperature: 0.7}

  loop SSE token stream
    LLM-->>CHAT: delta.content token
    CHAT-->>FE: data: {"token": "..."}
  end

  LLM-->>CHAT: [DONE]
  CHAT-->>FE: data: {"sources": ["doc.pdf", ...], "done": true}
  FE->>FE: render risposta + source chips
```

---

## 4. Struttura moduli e dipendenze

```mermaid
graph TB
  main["main.py\nlifespan · router mount\nstartup: log_stream → search → watcher\nlog hardware_summary()"]
  config["config.py\nSettings + hardware auto-detect\nnvidia-smi → VRAM · wmic → RAM\nchat_model · ingest_model · ocr_device\n.env override sempre"]

  main --> config

  subgraph Routers
    files_r["routers/files.py\nGET · POST · DELETE /api/files"]
    chat_r["routers/chat.py\nPOST /api/chat"]
    logs_r["routers/logs.py\nGET /api/logs/stream"]
  end

  main --> files_r
  main --> chat_r
  main --> logs_r
  main --> logstream["log_stream.py\nSSELogHandler\ndeque replay 50"]
  main --> watcher_s["services/watcher.py\nObserver + debounce 2s"]
  main --> search_s["services/search.py\nBM25Okapi\nrebuild_index()"]

  files_r --> ingest_s["services/ingest.py\nOCR → LLM → wiki/\nfrontmatter · index · log"]
  chat_r --> search_s
  chat_r --> llm_s["services/llm.py\nhttpx async\nchat_stream · chat_once\nis_llm_ready"]

  ingest_s --> ocr_s["services/ocr.py\nTier1: pypdfium2 (embedded text)\nTier2: backend selezionato\n  tesseract (default)\n  easyocr (upgrade)\n  ollama vision (max qualità)\nTier3: python-docx\nTier4: UTF-8"]
  ingest_s --> llm_s
  ingest_s --> search_s
  watcher_s --> ingest_s

  config --> llm_s
  config --> ingest_s
  config --> search_s
  config --> watcher_s
```

---

## Riepilogo tecnologie

| Layer | Tecnologia | Scopo |
|-------|-----------|-------|
| Frontend | Vanilla JS + HTML/CSS | UI upload, chat, log panel |
| API | FastAPI + uvicorn | REST + SSE streaming |
| LLM chat | Ollama (auto: qwen3:4b–14b) | RAG streaming — modello scelto da VRAM/RAM |
| LLM ingest | Ollama (auto: qwen3:8b–32b-a3b) | Summarizzazione batch PDF→wiki |
| OCR Tier1 | pypdfium2 | Estrazione testo embedded da PDF |
| OCR Tier2 | Tesseract (default) / EasyOCR / GOT-OCR2 / Ollama vision | Scanned PDF, immagini |
| DOCX | python-docx | Documenti Word |
| Search | rank-bm25 (BM25Okapi) | Retrieval per RAG |
| Config | pydantic-settings + `nvidia-smi`/`wmic` | Auto-detect GPU/RAM → model defaults · `.env` override |
| File watch | watchdog | Auto-ingest su drop in raw/ |
| Logging | logging + SSE | Stream log in tempo reale — include hardware summary al boot |
