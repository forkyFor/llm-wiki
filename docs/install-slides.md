---
marp: true
theme: default
paginate: true
style: |
  section {
    background: #0f1117;
    color: #e1e4f0;
    font-family: "Segoe UI", sans-serif;
  }
  h1 { color: #6c8ef5; }
  h2 { color: #6c8ef5; border-bottom: 1px solid #2a2d3e; padding-bottom: 8px; }
  code { background: #1a1d27; color: #e1e4f0; padding: 2px 6px; border-radius: 4px; }
  pre { background: #1a1d27; padding: 16px; border-radius: 8px; }
  pre code { background: none; padding: 0; }
  table { width: 100%; border-collapse: collapse; }
  th { background: #1a1d27; color: #6c8ef5; padding: 8px; }
  td { border-top: 1px solid #2a2d3e; padding: 8px; }
  .green { color: #4eca8b; }
  .orange { color: #f0a84e; }
  .blue { color: #6c8ef5; }
---

# LLM Wiki
## Guida all'Installazione

Wiki personale con **OCR automatico** e **chat AI** — completamente offline.

---

## Cos'è LLM Wiki?

- **Drag & drop** documenti PDF, immagini, testo
- **OCR automatico**: estrae testo embedded o scansionato
- **Summarizzazione AI**: genera pagine wiki strutturate
- **Chat con RAG**: fai domande sui tuoi documenti
- **100% offline**: nessun dato esce dalla tua macchina

```
raw/documento.pdf  →  OCR  →  LLM  →  wiki/sources/2025-01-01_documento.md
                                           ↓
                                     Chat con BM25 + Ollama
```

---

## Architettura

```
┌─────────────────────────────────────────────┐
│  Browser (localhost:8000)                   │
│  Upload · Chat · Log panel                  │
└──────────────┬──────────────────────────────┘
               │ HTTP + SSE
┌──────────────▼──────────────────────────────┐
│  FastAPI                                    │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ /files   │  │ /chat    │  │ /logs    │  │
│  └────┬─────┘  └────┬─────┘  └──────────┘  │
│       │ ingest      │ BM25 + LLM            │
│  ┌────▼─────────────▼──────────────────┐    │
│  │ OCR (pypdfium2 · Tesseract)         │    │
│  │ LLM (httpx → Ollama :11434)         │    │
│  │ Search (BM25Okapi)                  │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

---

## Prerequisiti

| Componente | Versione | Come installare |
|-----------|---------|----------------|
| **Python** | ≥ 3.11 | `winget install Python.Python.3.11` |
| **Ollama** | qualsiasi | `winget install Ollama.Ollama` |
| **Tesseract** | qualsiasi | `winget install UB-Mannheim.TesseractOCR` |

Tesseract è **opzionale** — serve solo per PDF scansionati e immagini.
PDF con testo embedded funzionano senza.

---

## Scegli il modello in base all'hardware

| RAM disponibile | GPU VRAM | Tag Ollama | Dimensione |
|----------------|---------|-----------|-----------|
| qualsiasi | ≥ 12 GB | `qwen3:32b-a3b` | ~20 GB |
| qualsiasi | ≥ 8 GB | `qwen3:14b` | ~9 GB |
| ≤ 4 GB | — | `qwen3:1.7b` | ~1.5 GB |
| 4–6 GB | — | `qwen3:4b` | ~2.6 GB |
| 6–10 GB (velocità) | — | `qwen3:8b` | ~5.2 GB |
| 10–14 GB | — | `qwen3:14b` | ~9.3 GB |
| 14–20 GB (velocità) | — | `qwen3:30b-a3b` | ~20 GB |
| > 20 GB | — | `qwen3:32b` | ~20 GB |

---

## Step 1 — Installa Ollama

**Windows:**
```powershell
winget install Ollama.Ollama
# riavvia il terminale dopo l'installazione
ollama --version
```

**Linux / macOS:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Verifica:**
```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags"
# atteso: JSON con chiave "models"
```

---

## Step 2 — Scarica il modello

```bash
# Sostituisci con il tag scelto dalla tabella
ollama pull qwen3:14b
```

Tempo stimato:
- Modelli piccoli (1.7b–8b): **2–5 minuti**
- Modelli grandi (14b–32b): **10–40 minuti**

Se `ollama pull` fallisce con 404:
```bash
ollama search qwen3   # cerca tag disponibili
```

---

## Step 3 — Installa dipendenze Python

```bash
pip install -r backend/requirements.txt
```

Dipendenze principali:

| Pacchetto | Scopo |
|-----------|-------|
| `fastapi` + `uvicorn` | Server API |
| `pypdfium2` | Estrazione testo PDF |
| `pytesseract` + `Pillow` | OCR immagini |
| `rank-bm25` | Ricerca full-text |
| `httpx` | Chiamate a Ollama |
| `python-frontmatter` | Parsing YAML wiki |

---

## Step 4 — Configura .env

Crea il file `.env` nella root del progetto:

```env
OLLAMA_URL=http://localhost:11434
MODEL_NAME=qwen3:14b
OCR_DEVICE=cpu
RAW_DIR=raw
WIKI_DIR=wiki
```

Se Tesseract non è nel PATH di sistema:
```env
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

Copia da `.env.example` come punto di partenza.

---

## Step 5 — Avvia

**Terminale 1** — avvia Ollama (se non parte in automatico):
```bash
ollama serve
```

**Terminale 2** — avvia il backend:
```bash
uvicorn backend.main:app --reload
```

Oppure tutto-in-uno con il launcher:
```bash
python launcher.py
```

Apri il browser su **http://localhost:8000**

---

## Verifica installazione

```powershell
# 1. Ollama risponde e ha il modello
Invoke-RestMethod -Uri "http://localhost:11434/api/tags" | ConvertTo-Json

# 2. Test chat one-shot
$body = '{"model":"qwen3:14b","messages":[{"role":"user","content":"ciao"}],"stream":false}'
Invoke-RestMethod -Uri "http://localhost:11434/v1/chat/completions" `
  -Method Post -Body $body -ContentType "application/json"

# 3. Config Python OK
python -c "from backend.config import settings; print('OK:', settings.model_name)"
```

---

## Installazione completata

Apri **http://localhost:8000** e:

1. **Carica un documento** — drag & drop nella sidebar
2. **Attendi l'ingest** — 10–30 min su CPU (visibile nel log panel)
3. **Fai una domanda** — la chat usa BM25 + Ollama per rispondere

---

Per la selezione guidata del modello e troubleshooting completo:

```
install.ps1   (Windows)
install.sh    (Linux/macOS)
```

> Avvia `.\install.ps1` o `./install.sh` per l'installazione guidata automatica
