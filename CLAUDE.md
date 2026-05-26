# LLM Wiki

Wiki personale con OCR automatico e chat AI — completamente offline.
Backend: FastAPI + pytesseract + Ollama (famiglia Qwen3).

## Context-mode (token savings — sempre attivo)

MCP `context-mode` è configurato con hooks SessionStart + PreToolUse.
Indicizza i file chiave all'inizio di ogni sessione per evitare read ripetuti.

**Regole**:
- Usa `ctx_search` per trovare funzioni/variabili prima di fare `Read` su file grandi
- Riindicizza con `ctx_index` dopo modifiche significative a un file
- File da indicizzare a ogni sessione: `backend/services/llm.py`, `backend/routers/chat.py`, `backend/config.py`, `backend/main.py`, `backend/services/ingest.py`

## Struttura progetto

```
llm_wiki/
├── backend/
│   ├── config.py          ← pydantic-settings: OLLAMA_URL, CHAT_MODEL_NAME, INGEST_MODEL_NAME
│   ├── services/llm.py    ← httpx → http://localhost:11434/v1/chat/completions
│   └── requirements.txt
├── launcher.py            ← ensure ollama serve, poi uvicorn
├── .env                   ← OLLAMA_URL, CHAT_MODEL_NAME, INGEST_MODEL_NAME (scritto da /install)
└── CLAUDE.md              ← questo file
```

## Avvio (sviluppo)

```bash
ollama serve
uvicorn backend.main:app --reload   # http://localhost:8000
```

## Variabili d'ambiente (.env)

`CHAT_MODEL_NAME`, `INGEST_MODEL_NAME`, `OCR_DEVICE` sono **auto-rilevati** da `config.py` a ogni avvio (NVIDIA VRAM → RAM → fallback). Il `.env` sovrascrive sempre i default auto-rilevati.

| Variabile | Default | Descrizione |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Endpoint Ollama |
| `CHAT_MODEL_NAME` | _(auto-rilevato)_ | Override modello chat — se assente usa selezione hardware |
| `INGEST_MODEL_NAME` | _(auto-rilevato)_ | Override modello ingest — se assente usa selezione hardware |
| `OCR_DEVICE` | _(auto-rilevato)_ | `cpu` o `cuda` — auto `cuda` se NVIDIA ≥ 4 GB VRAM |
| `RAW_DIR` | `raw` | Cartella documenti sorgente |
| `WIKI_DIR` | `wiki` | Cartella wiki markdown |
| `TESSERACT_CMD` | _(sistema)_ | Path Tesseract se non in PATH |

Funzioni esposte da `config.py`:
- `DETECTED_VRAM_GB` — VRAM NVIDIA rilevata (0.0 se nessuna)
- `DETECTED_RAM_GB` — RAM totale sistema
- `hardware_summary()` → stringa log, es. `"GPU CUDA 12.0GB | chat=qwen3:14b ingest=qwen3:32b-a3b ocr_device=cuda (auto)"`

---

# /install — Installazione Adattiva

**Trigger**: utente scrive `/install` oppure "installa il progetto".

## Approccio: chat + script unificato

1. Rileva hardware (step 1 sotto) — esegui i comandi in chat.
2. Conduci intervista in chat (step 2) — raccogli tutte le risposte.
3. **Invoca lo script con i parametri** — il banner, le barre di progresso e l'output colorato appaiono nel terminale dell'utente:

```powershell
# Windows — esegui con ! per vedere l'output nel terminale
.\install.ps1 -NonInteractive [-UseGpu] [-RamLlm X] [-PreferSpeed] [-OcrBackend "backend"] [-OverwriteEnv]
```
```bash
# Linux/macOS
./install.sh --non-interactive [--use-gpu] [--ram-llm=X] [--prefer-speed] [--ocr-backend=backend] [--overwrite-env]
```

**Parametri disponibili:**

| Parametro PS1 | Flag sh | Descrizione |
|---|---|---|
| `-UseGpu` | `--use-gpu` | Abilita accelerazione GPU |
| `-RamLlm 8` | `--ram-llm=8` | GB RAM da allocare all'LLM |
| `-PreferSpeed` | `--prefer-speed` | Modelli più veloci (qualità ridotta) |
| `-OcrBackend tesseract` | `--ocr-backend=tesseract` | Backend OCR scelto |
| `-ChatModel qwen3:8b` | `--chat-model=qwen3:8b` | Override modello chat |
| `-IngestModel qwen3:14b` | `--ingest-model=qwen3:14b` | Override modello ingest |
| `-OverwriteEnv` | `--overwrite-env` | Sovrascrivi .env esistente |

Esegui questi step in ordine. Non saltare nessuno step.

---

## Step 1 — Rileva hardware

Esegui questi comandi e registra i valori:

```powershell
# RAM totale in GB
[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)

# Core CPU logici
(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors

# GPU — tutti gli adattatori video con VRAM
Get-CimInstance Win32_VideoController |
  Select-Object Name, @{N='VRAM_GB';E={[math]::Round($_.AdapterRAM/1GB,1)}} |
  Format-Table -AutoSize

# NVIDIA: verifica driver CUDA (OK se trovato, errore = assente)
try { nvidia-smi --query-gpu=name,memory.total --format=csv,noheader } catch { "no NVIDIA GPU" }
```

Su Linux/macOS:
```bash
free -g | awk '/Mem:/{print $2}'
nproc
# GPU:
lspci | grep -Ei 'vga|3d|display'
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "no NVIDIA GPU"
```

**Classifica GPU rilevata** (salva come `GPU_TYPE`):

| Condizione | GPU_TYPE | Note |
|---|---|---|
| `nvidia-smi` risponde, VRAM ≥ 4 GB | `nvidia` | CUDA disponibile — accelerazione piena |
| `nvidia-smi` risponde, VRAM < 4 GB | `nvidia-low` | Accelerazione parziale, modelli piccoli |
| Nome contiene "AMD" + VRAM ≥ 4 GB + Linux | `amd-rocm` | ROCm su Linux (sperimentale) |
| Nome contiene "AMD"/"Intel" + Windows + iGPU | `none` | GPU integrata — CPU-only |
| Nessun `nvidia-smi` + no GPU dedicata | `none` | CPU-only |

Mostra riepilogo es: `"Rilevato: 16 GB RAM, 8 core, GPU: NVIDIA RTX 3060 12GB [CUDA]"` oppure `"GPU: integrata AMD (non utilizzabile per LLM)"`.

---

## Step 2 — Intervista utente

Poni queste domande in un unico messaggio (mostra sempre tutte e 4):

1. **GPU** ← domanda PRIORITARIA:
   - Se `GPU_TYPE=nvidia`: "Rilevata **GPU NVIDIA [nome] con [X] GB VRAM**. Vuoi abilitare l'accelerazione GPU? (sì/no)"
   - Se `GPU_TYPE=amd-rocm`: "Rilevata GPU AMD [nome]. Usi Linux? ROCm è sperimentale — vuoi tentare accelerazione GPU? (sì/no)"
   - Se `GPU_TYPE=none`: "**Nessuna GPU dedicata rilevata** — il sistema girerà in modalità CPU-only. Se hai una GPU NVIDIA non rilevata, specifica ora modello e VRAM. (oppure: 'no gpu')"

2. **RAM per LLM**: "Quanta RAM vuoi dedicare all'LLM? (consigliato: X GB)"
   — Suggerisci: `detected_ram × 0.6` arrotondato, minimo 4 GB

3. **Preferenza**: "Preferisci velocità o qualità nelle risposte? (velocità/qualità)"

4. **VRAM disponibile** (solo se GPU confermata): "Quanti GB VRAM ha la GPU? [pre-compila da Step 1]"

Attendi risposta a tutte prima di continuare. Salva: `USE_GPU` (true/false), `GPU_VRAM_GB`.

---

## Step 3 — Seleziona i due modelli Ollama

Il sistema usa **due modelli separati**:
- **CHAT**: velocità, streaming RAG → caricato su richiesta utente
- **INGEST**: qualità, batch PDF→wiki → caricato solo durante ingest, si scarica dopo

### Path GPU (USE_GPU=true)

Applica in base a `GPU_VRAM_GB`:

| VRAM GPU | CHAT_MODEL | INGEST_MODEL | Quantizzazione | Risposta attesa |
|---|---|---|---|---|
| ≥ 24 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 1–3s |
| ≥ 12 GB | `qwen3:14b` | `qwen3:32b-a3b` | q5_K_M | 2–5s |
| ≥ 8 GB | `qwen3:8b` | `qwen3:14b` | q5_K_M | 3–8s |
| ≥ 4 GB | `qwen3:4b` | `qwen3:8b` | q4_K_M | 5–12s |

Tag quantizzato: aggiungere `-q5_K_M` al modello ingest, es. `ollama pull qwen3:14b-q5_K_M`.
Ollama auto-rileva CUDA — nessuna config aggiuntiva.

### Path CPU (USE_GPU=false)

Applica la PRIMA riga corrispondente in base a RAM dedicata:

| RAM | CHAT_MODEL | INGEST_MODEL | Risposta attesa |
|---|---|---|---|
| ≤ 4 GB | `qwen3:1.7b` | `qwen3:1.7b` | 20–40s |
| 4–6 GB | `qwen3:1.7b` | `qwen3:4b` | 30–60s |
| 6–10 GB | `qwen3:4b` | `qwen3:8b` | 60–120s |
| 10–14 GB | `qwen3:4b` | `qwen3:14b` | 90–150s |
| 14–20 GB | `qwen3:8b` | `qwen3:14b` | 120–190s |
| > 20 GB | `qwen3:14b` | `qwen3:30b-a3b` | 150–300s |

Salva `CHAT_TAG`, `INGEST_TAG`, `USE_GPU`. Mostra all'utente:
> "Chat: `<CHAT_TAG>` | Ingest: `<INGEST_TAG>` | Accelerazione: **GPU CUDA** / **CPU-only** — Motivo: <una riga>"

---

## Step 4 — Seleziona backend OCR

Presenta all'utente questa scelta:

> "Quale backend OCR vuoi usare?"
> - **tesseract** (default, consigliato) — leggero, veloce, buono per scan puliti [~50 MB]
> - **easyocr** — migliore su font non-standard e testo ruotato [~120 MB auto-download]
> - **got_ocr2** — ottima qualità, layout multi-colonna, tabelle, multilingua [~580 MB auto-download, richiede `transformers torch`]
> - **ollama** — massima qualità (vision LLM), gestisce tabelle/manoscritti [~5.5 GB]

Salva la scelta come `OCR_BACKEND`.
- Se GPU VRAM ≥ 8 GB → suggerisci `ollama`
- Se CPU 8+ GB RAM, documenti complessi → suggerisci `got_ocr2`
- Se CPU < 8 GB RAM → `tesseract` o `easyocr`

---

## Step 5 — Installa dipendenze di sistema

### Python ≥ 3.11
```powershell
python --version
# Se assente o < 3.11:
winget install Python.Python.3.11
```

### Tesseract OCR (sempre richiesto come base/fallback)
```powershell
tesseract --version
# Se assente:
winget install UB-Mannheim.TesseractOCR
# Aggiungi al PATH di sistema:
[System.Environment]::SetEnvironmentVariable("PATH",
  [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";C:\Program Files\Tesseract-OCR",
  "Machine")
```
Su Linux: `sudo apt install -y tesseract-ocr tesseract-ocr-ita`

### EasyOCR (solo se OCR_BACKEND=easyocr)
```bash
pip install easyocr
# Prima esecuzione scarica ~120 MB modelli automaticamente
```

### GOT-OCR2 (solo se OCR_BACKEND=got_ocr2)
```bash
pip install transformers torch torchvision
# Prima esecuzione scarica ~580 MB modello automaticamente (stepfun-ai/GOT-OCR-2.0-hf)
# GPU NVIDIA rilevata automaticamente da torch/transformers
```

### Ollama vision model (solo se OCR_BACKEND=ollama)
```bash
ollama pull minicpm-v    # ~5.5 GB — da eseguire dopo Step 6 (Ollama già avviato)
```

---

## Step 5b — Abilita accelerazione GPU (solo se USE_GPU=true)

> **Salta questo step se USE_GPU=false.** Non serve nessuna configurazione extra per CPU-only.

### NVIDIA (Windows / Linux)

```powershell
# 1. Verifica driver NVIDIA installati e versione CUDA
nvidia-smi
# Output atteso: tabella con GPU, VRAM, CUDA Version >= 11.8
# Se assente: installa driver NVIDIA dal sito ufficiale → https://www.nvidia.com/drivers

# 2. Ollama rileva CUDA automaticamente — nessun setup aggiuntivo
# Verifica dopo `ollama serve`:
ollama run qwen3:8b "rispondi con una parola: ok" 2>&1
# Nel log del server Ollama (finestra separata) deve comparire:
# "using CUDA device" oppure "GPU layers: XX"
```

Su Linux verifica anche:
```bash
# Deve rispondere senza errori
python3 -c "import torch; print('CUDA:', torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

### AMD su Windows

**ROCm non supportato su Windows per Ollama.** AMD iGPU o dGPU su Windows = CPU-only.
Imposta `USE_GPU=false` e usa path CPU.

### AMD su Linux (ROCm — sperimentale)

```bash
# Verifica ROCm installato
rocm-smi
# Ollama con ROCm: installare da https://ollama.com/download/linux
# oppure: HSA_OVERRIDE_GFX_VERSION=10.3.0 ollama serve
```

### Verifica GPU attiva in Ollama

```powershell
# Dopo `ollama serve` (in background), esegui una query e controlla i log del server:
# log deve contenere: "using CUDA" o "GPU layers: <n>" o "offloaded <n>/<n> layers to GPU"
# Se mostra "using CPU" → CUDA non trovato, controlla driver
```

---

## Step 6 — Installa Ollama  <!--renumbered: was Step 5-->

```powershell
ollama --version
# Se assente:
winget install Ollama.Ollama
Start-Sleep -Seconds 5
# Avvia daemon:
Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
Start-Sleep -Seconds 3
```

Su Linux/macOS:
```bash
which ollama || curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
sleep 3
```

Verifica:
```powershell
Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get
```
Atteso: JSON con chiave `models`. Se fallisce, attendi 5 secondi e riprova una volta.

---

## Step 7 — Scarica i modelli

```bash
ollama pull <CHAT_TAG>
ollama pull <INGEST_TAG>
# Con GPU e USE_GPU=true: usa quantizzazione q5_K_M per il modello ingest
# es: ollama pull qwen3:14b-q5_K_M
```

I due modelli non sono mai in memoria contemporaneamente (Ollama scarica dopo 5 min idle).
Informa l'utente del tempo stimato: modelli ~5 GB → 5-10 min, ~9 GB → 15-20 min.
Se `ollama pull` fallisce con 404: usa `qwen3:8b` (chat) e `qwen3:14b` (ingest) come fallback sicuri.

---

## Step 8 — Scrivi .env

Se `.env` esiste già, mostra il contenuto e chiedi conferma sovrascrittura.

`OCR_DEVICE`: usa `cuda` se `USE_GPU=true` + NVIDIA, altrimenti `cpu`.

```powershell
# USE_GPU=true → OCR_DEVICE=cuda, USE_GPU=false → OCR_DEVICE=cpu
$ocrDevice = if ($USE_GPU -eq $true) { "cuda" } else { "cpu" }

[System.IO.File]::WriteAllText(".env", @"
OLLAMA_URL=http://localhost:11434
CHAT_MODEL_NAME=<CHAT_TAG>
INGEST_MODEL_NAME=<INGEST_TAG>
OCR_BACKEND=<OCR_BACKEND>
OCR_DEVICE=$ocrDevice
RAW_DIR=raw
WIKI_DIR=wiki
"@, [System.Text.UTF8Encoding]::new($false))
```

---

## Step 9 — Installa dipendenze Python

```bash
pip install -r backend/requirements.txt
```

---

## Step 10 — Verifica installazione

```powershell
# Ollama risponde e ha il modello
Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get | ConvertTo-Json

# Test chat one-shot (misura tempo — GPU < 15s, CPU 30-190s)
$start = Get-Date
$body = '{"model":"<CHAT_TAG>","messages":[{"role":"user","content":"Rispondi con una parola: ok"}],"stream":false,"options":{"num_predict":3}}'
$r = Invoke-RestMethod -Uri "http://localhost:11434/v1/chat/completions" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 300
$ms = [int]((Get-Date) - $start).TotalMilliseconds
Write-Host "Risposta: $($r.choices[0].message.content) — Tempo: ${ms}ms"

# Verifica GPU (solo se USE_GPU=true):
# Nel log di Ollama deve comparire "GPU layers" o "offloaded X/X layers"
# Se tempo > 60s con GPU dichiarata → CUDA non attivo, controlla driver

# Tesseract
tesseract --version

# Config backend
python -c "from backend.config import settings; print('OK chat:', settings.chat_model_name, '| ingest:', settings.ingest_model_name, '| ocr_device:', settings.ocr_device)"
```

Interpreta il tempo di risposta:
- **< 15s**: GPU CUDA attiva ✓
- **15–60s**: GPU parziale o modello piccolo ✓
- **> 60s**: CPU-only (normale se nessuna GPU)
- **> 60s con GPU dichiarata**: CUDA non attivo — controlla `nvidia-smi` e driver

Se tutto OK:
> "Installazione completata. Avvia con: `uvicorn backend.main:app --reload`"

---

## Troubleshooting

| Problema | Soluzione |
|---|---|
| `ollama: not found` dopo winget | Chiudi e riapri il terminale (PATH aggiornato) |
| `ollama pull` 404 | Tag cambiato — esegui `ollama search qwen3` e scegli il più vicino |
| Tesseract non trovato a runtime | Aggiungi a `.env`: `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` |
| Porta 11434 occupata | Altra istanza Ollama attiva — salta Step 6, procedi con Step 7 |
| Modello troppo lento | Ri-esegui `/install`, scegli meno GB RAM → modello più piccolo |
| GPU NVIDIA presente ma Ollama usa CPU | Installa/aggiorna driver NVIDIA → esegui `nvidia-smi` — se non risponde, driver mancante |
| `nvidia-smi` OK ma Ollama usa CPU | Reinstalla Ollama (versione recente include CUDA built-in) |
| AMD GPU + Windows = CPU-only | ROCm non supportato su Windows. Usa Linux + ROCm oppure accetta CPU-only |
| EasyOCR lento anche con GPU | Aggiungi a `.env`: `OCR_DEVICE=cuda` — EasyOCR usa torch che supporta CUDA |

### Linux / Ubuntu — problemi specifici

| Problema | Soluzione |
|---|---|
| `ollama pull` fallisce con "no space left on device" su VM/LVM | LV sottodimensionato. Estendi: `sudo lvextend -l +100%FREE /dev/ubuntu-vg/ubuntu-lv && sudo resize2fs /dev/mapper/ubuntu--vg-ubuntu--lv` |
| `npm install -g` ETIMEDOUT su IPv6 | `NODE_OPTIONS='--dns-result-order=ipv4first' npm install -g <pacchetto>` |
| `npm install -g` permission denied su `/usr/local` | `npm config set prefix ~/.local` poi reinstalla — aggiungere `~/.local/bin` al PATH |
| `~/.local/bin` non nel PATH in sessioni SSH | Aggiungere `export PATH="$HOME/.local/bin:$PATH"` a `~/.profile` (non solo `~/.bashrc`) |
| `python3 -m venv` fallisce su Ubuntu | `sudo apt install python3.12-venv` |
| `pip` non trovato | `sudo apt install python3-pip` oppure usare `python3 -m pip` |
| Tesseract non installato su Linux | `sudo apt install tesseract-ocr tesseract-ocr-ita` |
| Porta 8000 non raggiungibile da rete | `sudo ufw allow 8000/tcp comment 'LLM Wiki' && sudo ufw reload` |

### Avvio automatico su Linux (systemd)

```ini
# /etc/systemd/system/llm-wiki.service
[Unit]
Description=LLM Wiki Backend
After=network.target ollama.service

[Service]
Type=simple
User=<utente>
WorkingDirectory=/home/<utente>/llm-wiki
ExecStart=/home/<utente>/llm-wiki/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now llm-wiki
```
