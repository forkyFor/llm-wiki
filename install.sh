#!/usr/bin/env bash
# LLM Wiki — Linux/macOS Installer
# Interactive installer with hardware detection, model selection, full setup and usage guide.
#
# Non-interactive usage:
#   ./install.sh --non-interactive [--use-gpu] [--ram-llm=X] [--prefer-speed]
#                [--ocr-backend=tesseract|easyocr|got_ocr2|ollama]
#                [--chat-model=TAG] [--ingest-model=TAG] [--overwrite-env]
set -euo pipefail

# ── Argument parsing ──────────────────────────────────────────────────────────
NONINTERACTIVE=false
USE_GPU_PARAM=""
RAM_LLM_PARAM=""
PREFER_SPEED_PARAM=false
OCR_BACKEND_PARAM=""
CHAT_MODEL_PARAM=""
INGEST_MODEL_PARAM=""
OVERWRITE_ENV=false

for arg in "$@"; do
    case "$arg" in
        --non-interactive)    NONINTERACTIVE=true ;;
        --use-gpu)            USE_GPU_PARAM=true ;;
        --no-gpu)             USE_GPU_PARAM=false ;;
        --ram-llm=*)          RAM_LLM_PARAM="${arg#*=}" ;;
        --prefer-speed)       PREFER_SPEED_PARAM=true ;;
        --ocr-backend=*)      OCR_BACKEND_PARAM="${arg#*=}" ;;
        --chat-model=*)       CHAT_MODEL_PARAM="${arg#*=}" ;;
        --ingest-model=*)     INGEST_MODEL_PARAM="${arg#*=}" ;;
        --overwrite-env)      OVERWRITE_ENV=true ;;
        *) echo "Opzione sconosciuta: $arg" >&2; exit 1 ;;
    esac
done

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

ok()   { echo -e "  ${GREEN}✓${RESET} $*"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $*"; }
err()  { echo -e "  ${RED}✗${RESET} $*"; }
info() { echo -e "  ${DIM}·${RESET} $*"; }
bold() { echo -e "${BOLD}$*${RESET}"; }

ask() {
    local prompt="$1" default="${2:-}"
    local hint=""
    [[ -n "$default" ]] && hint=" ${DIM}[$default]${RESET}"
    echo -ne "  ${CYAN}?${RESET} ${prompt}${hint} : "
    read -r ans
    echo "${ans:-$default}"
}

ask_yn() {
    local prompt="$1" default="${2:-s}"
    local hint
    [[ "$default" == "s" ]] && hint=" ${DIM}[S/n]${RESET}" || hint=" ${DIM}[s/N]${RESET}"
    echo -ne "  ${CYAN}?${RESET} ${prompt}${hint} : "
    read -r ans
    ans="${ans:-$default}"
    [[ "${ans,,}" =~ ^(s|si|y|yes)$ ]]
}

print_step() {
    local n="$1" total="$2" label="$3"
    echo ""
    echo -e "  ${CYAN}┌─────────────────────────────────────────────────────┐${RESET}"
    echo -e "  ${CYAN}│${RESET} ${BOLD}STEP $n/$total${RESET} — $label"
    echo -e "  ${CYAN}└─────────────────────────────────────────────────────┘${RESET}"
}

spinner() {
    local pid=$1 label="$2"
    local frames=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        printf "\r  ${CYAN}%s${RESET} %s   " "${frames[$((i % ${#frames[@]}))]}" "$label"
        sleep 0.1; ((i++))
    done
    printf "\r%60s\r" ""
}

cmd_exists() { command -v "$1" &>/dev/null; }

OS="linux"
[[ "$(uname)" == "Darwin" ]] && OS="macos"

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}  ██╗     ██╗     ███╗   ███╗    ██╗    ██╗██╗██╗  ██╗██╗${RESET}"
echo -e "${CYAN}  ██║     ██║     ████╗ ████║    ██║    ██║██║██║ ██╔╝██║${RESET}"
echo -e "${CYAN}  ██║     ██║     ██╔████╔██║    ██║ █╗ ██║██║█████╔╝ ██║${RESET}"
echo -e "${CYAN}  ██║     ██║     ██║╚██╔╝██║    ██║███╗██║██║██╔═██╗ ██║${RESET}"
echo -e "${CYAN}  ███████╗███████╗██║ ╚═╝ ██║    ╚███╔███╔╝██║██║  ██╗██║${RESET}"
echo -e "${CYAN}  ╚══════╝╚══════╝╚═╝     ╚═╝     ╚══╝╚══╝ ╚═╝╚═╝  ╚═╝╚═╝${RESET}"
echo ""
echo -e "${BOLD}  Wiki personale offline con OCR automatico e chat AI${RESET}"
echo -e "${DIM}  Installer v1.0 — Linux/macOS${RESET}"
echo ""

echo -e "${BOLD}  Questo script installerà:${RESET}"
echo "  • Python ≥ 3.11 + dipendenze backend"
echo "  • Tesseract OCR"
echo "  • Ollama + modello LLM (qwen3)"
echo "  • Configurazione .env automatica"
echo ""

if [[ "$NONINTERACTIVE" == true ]]; then
    info "Modalità non-interattiva — installazione avviata automaticamente."
else
    ask_yn "Vuoi procedere con l'installazione" || { echo -e "${YELLOW}  Installazione annullata.${RESET}"; exit 0; }
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Hardware detection
# ═══════════════════════════════════════════════════════════════════════════
print_step 1 9 "Rilevamento hardware"

# RAM
if [[ "$OS" == "macos" ]]; then
    RAM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo 8589934592)
    RAM_GB=$(awk "BEGIN {printf \"%.1f\", $RAM_BYTES/1073741824}")
else
    RAM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    RAM_GB=$(awk "BEGIN {printf \"%.1f\", $RAM_KB/1048576}")
fi

CPU=$(grep "model name" /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | xargs || sysctl -n machdep.cpu.brand_string 2>/dev/null || echo "CPU")
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo "?")

VRAM_GB=0
GPU_NAME="Non rilevata"
GPU_TYPE="none"

if cmd_exists nvidia-smi; then
    NVOUT=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || true)
    if [[ -n "$NVOUT" ]]; then
        GPU_NAME=$(echo "$NVOUT" | cut -d, -f1 | xargs)
        VRAM_MIB=$(echo "$NVOUT" | cut -d, -f2 | grep -o '[0-9]*' | head -1)
        VRAM_GB=$(awk "BEGIN {printf \"%.1f\", $VRAM_MIB/1024}")
        VRAM_INT=${VRAM_MIB:-0}
        if [[ "$VRAM_INT" -ge 4096 ]]; then GPU_TYPE="nvidia"; else GPU_TYPE="nvidia-low"; fi
    fi
elif [[ "$OS" == "linux" ]] && cmd_exists rocm-smi; then
    GPU_TYPE="amd-rocm"
    GPU_NAME=$(rocm-smi --showproductname 2>/dev/null | grep -i "card" | head -1 | awk '{print $NF}' || echo "AMD GPU")
    VRAM_GB=8  # approximate
fi

echo ""
info "CPU  : $CPU ($CPU_CORES thread)"
info "RAM  : ${RAM_GB} GB"

case "$GPU_TYPE" in
    nvidia)     ok  "GPU  : $GPU_NAME — ${VRAM_GB} GB VRAM (CUDA disponibile)" ;;
    nvidia-low) warn "GPU  : $GPU_NAME — ${VRAM_GB} GB VRAM (VRAM bassa, CPU-only)" ;;
    amd-rocm)   warn "GPU  : $GPU_NAME — ROCm (sperimentale)" ;;
    *)          warn "GPU  : $GPU_NAME — CPU-only" ;;
esac

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — User interview
# ═══════════════════════════════════════════════════════════════════════════
print_step 2 9 "Configurazione"

USE_GPU=false
if [[ "$GPU_TYPE" == "nvidia" ]]; then
    if [[ "$NONINTERACTIVE" == true ]]; then
        [[ "$USE_GPU_PARAM" == "true" ]] && USE_GPU=true || true
        info "GPU: accelerazione = $USE_GPU"
    else
        ask_yn "GPU NVIDIA rilevata ($GPU_NAME ${VRAM_GB}GB). Abilitare accelerazione GPU" && USE_GPU=true || true
    fi
elif [[ "$GPU_TYPE" == "amd-rocm" ]]; then
    if [[ "$NONINTERACTIVE" == true ]]; then
        [[ "$USE_GPU_PARAM" == "true" ]] && USE_GPU=true || true
        info "GPU: accelerazione = $USE_GPU"
    else
        ask_yn "GPU AMD rilevata con ROCm. Tentare accelerazione GPU (sperimentale)" && USE_GPU=true || true
    fi
elif [[ "$GPU_TYPE" == "nvidia-low" ]]; then
    warn "VRAM insufficiente per LLM — verrà usata la CPU."
else
    info "Nessuna GPU dedicata — modalità CPU-only."
fi

RAM_SUGGEST=$(awk "BEGIN {r=int($RAM_GB*0.6); print (r<4?4:r)}")
if [[ "$NONINTERACTIVE" == true && -n "$RAM_LLM_PARAM" ]]; then
    RAM_LLM="$RAM_LLM_PARAM"
    info "RAM LLM: $RAM_LLM GB"
else
    RAM_LLM=$(ask "RAM da dedicare all'LLM (GB)" "$RAM_SUGGEST")
    RAM_LLM=${RAM_LLM:-$RAM_SUGGEST}
fi

PREF_SPEED=false
if [[ "$NONINTERACTIVE" == true ]]; then
    [[ "$PREFER_SPEED_PARAM" == true ]] && PREF_SPEED=true || true
    info "Preferenza velocità: $PREF_SPEED"
else
    ask_yn "Preferisci velocità rispetto alla qualità delle risposte" "n" && PREF_SPEED=true || true
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Model selection
# ═══════════════════════════════════════════════════════════════════════════
print_step 3 9 "Selezione modelli"

if [[ -n "$CHAT_MODEL_PARAM" && -n "$INGEST_MODEL_PARAM" ]]; then
    CHAT_TAG="$CHAT_MODEL_PARAM"
    INGEST_TAG="$INGEST_MODEL_PARAM"
    ACCEL=$( [[ "$USE_GPU" == true ]] && echo "GPU CUDA" || echo "CPU-only" )
    ETA="N/D"
elif [[ "$USE_GPU" == true ]]; then
    V=$(awk "BEGIN {print int($VRAM_GB)}")
    if   [[ $V -ge 24 ]]; then CHAT_TAG="qwen3:14b"; INGEST_TAG="qwen3:32b-a3b"; ETA="1–3s"
    elif [[ $V -ge 12 ]]; then CHAT_TAG="qwen3:14b"; INGEST_TAG="qwen3:32b-a3b"; ETA="2–5s"
    elif [[ $V -ge 8  ]]; then CHAT_TAG="qwen3:8b";  INGEST_TAG="qwen3:14b";     ETA="3–8s"
    else                       CHAT_TAG="qwen3:4b";  INGEST_TAG="qwen3:8b";      ETA="5–12s"
    fi
    ACCEL="GPU CUDA"
else
    R=$(awk "BEGIN {print int($RAM_LLM)}")
    if   [[ $R -le 4  ]]; then CHAT_TAG="qwen3:1.7b"; INGEST_TAG="qwen3:1.7b";    ETA="20–40s"
    elif [[ $R -le 6  ]]; then CHAT_TAG="qwen3:1.7b"; INGEST_TAG="qwen3:4b";     ETA="30–60s"
    elif [[ $R -le 10 ]]; then CHAT_TAG="qwen3:4b";   INGEST_TAG="qwen3:8b";     ETA="60–120s"
    elif [[ $R -le 14 ]]; then CHAT_TAG="qwen3:4b";   INGEST_TAG="qwen3:14b";    ETA="90–150s"
    elif [[ $R -le 20 ]]; then CHAT_TAG="qwen3:8b";   INGEST_TAG="qwen3:14b";    ETA="120–190s"
    else                       CHAT_TAG="qwen3:14b";  INGEST_TAG="qwen3:30b-a3b"; ETA="150–300s"
    fi
    ACCEL="CPU-only"
fi

[[ "$PREF_SPEED" == true ]] && INGEST_TAG="$CHAT_TAG"

ok  "Chat model  : $CHAT_TAG"
ok  "Ingest model: $INGEST_TAG"
info "Accelerazione: $ACCEL | Risposta attesa: ~$ETA"

# OCR backend selection
echo ""
bold "  Quale backend OCR vuoi usare?"
echo "  1) tesseract  (default) — veloce, leggero, scan puliti [~50 MB]"
echo "  2) easyocr    — migliore con font non-standard [~120 MB auto-download]"
echo "  3) got_ocr2   — ottima qualità, layout complessi, tabelle [~580 MB, richiede transformers+torch]"
echo "  4) ollama     — massima qualità, lenta [~5.5 GB, GPU consigliata]"
[[ "$USE_GPU" == true ]] && info "GPU rilevata: got_ocr2 e ollama useranno CUDA automaticamente."
if [[ "$NONINTERACTIVE" == true && -n "$OCR_BACKEND_PARAM" ]]; then
    OCR_BACKEND="$OCR_BACKEND_PARAM"
    info "OCR backend: $OCR_BACKEND"
else
    OCR_CHOICE=""
    while [[ "$OCR_CHOICE" != [1-4] ]]; do
        read -rp "  Scelta [1-4]: " OCR_CHOICE
    done
    case "$OCR_CHOICE" in
        1) OCR_BACKEND="tesseract" ;;
        2) OCR_BACKEND="easyocr" ;;
        3) OCR_BACKEND="got_ocr2" ;;
        4) OCR_BACKEND="ollama" ;;
    esac
fi
ok "OCR backend selezionato: $OCR_BACKEND"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Python
# ═══════════════════════════════════════════════════════════════════════════
print_step 4 9 "Python ≥ 3.11"

PY_CMD=""
for cmd in python3.12 python3.11 python3 python; do
    if cmd_exists "$cmd"; then
        ver=$("$cmd" --version 2>&1 | grep -oP '3\.\K\d+' | head -1)
        if [[ "${ver:-0}" -ge 11 ]]; then PY_CMD="$cmd"; break; fi
    fi
done

if [[ -n "$PY_CMD" ]]; then
    ok "Python trovato: $($PY_CMD --version)"
else
    warn "Python 3.11+ non trovato. Installazione..."
    if [[ "$OS" == "macos" ]]; then
        if cmd_exists brew; then brew install python@3.11
        else err "Installa Homebrew (https://brew.sh) poi riesegui"; exit 1; fi
    else
        sudo apt-get update -qq && sudo apt-get install -y python3.11 python3.11-venv python3-pip
    fi
    PY_CMD="python3.11"
    ok "Python installato: $($PY_CMD --version)"
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Tesseract
# ═══════════════════════════════════════════════════════════════════════════
print_step 5 9 "Tesseract OCR"

if cmd_exists tesseract; then
    ok "Tesseract già installato: $(tesseract --version 2>&1 | head -1)"
else
    info "Installazione Tesseract..."
    if [[ "$OS" == "macos" ]]; then
        brew install tesseract tesseract-lang
    else
        sudo apt-get install -y tesseract-ocr tesseract-ocr-ita tesseract-ocr-eng
    fi
    ok "Tesseract installato: $(tesseract --version 2>&1 | head -1)"
fi

# Install extra OCR backend if selected
if [[ "$OCR_BACKEND" == "easyocr" ]]; then
    info "Installazione EasyOCR (~120 MB download al primo utilizzo)..."
    pip install easyocr --quiet && ok "EasyOCR installato" || warn "EasyOCR fallito — usa: pip install easyocr"
fi
if [[ "$OCR_BACKEND" == "got_ocr2" ]]; then
    info "Installazione dipendenze GOT-OCR2 (transformers, torch, torchvision)..."
    info "Modello ~580 MB scaricato automaticamente al primo utilizzo."
    pip install transformers torch torchvision --quiet && ok "GOT-OCR2 dipendenze installate" || warn "Fallito — usa: pip install transformers torch torchvision"
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Ollama
# ═══════════════════════════════════════════════════════════════════════════
print_step 6 9 "Ollama"

OLLAMA_RUNNING=false
if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    OLLAMA_RUNNING=true
    ok "Ollama già in esecuzione"
fi

if [[ "$OLLAMA_RUNNING" == false ]]; then
    if ! cmd_exists ollama; then
        info "Installazione Ollama..."
        curl -fsSL https://ollama.com/install.sh | sh
        ok "Ollama installato"
    fi

    info "Avvio Ollama daemon..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    sleep 4

    for i in {1..5}; do
        if curl -sf http://localhost:11434/api/tags &>/dev/null; then
            OLLAMA_RUNNING=true; break
        fi
        sleep 2
    done

    if [[ "$OLLAMA_RUNNING" == true ]]; then ok "Ollama avviato su http://localhost:11434"
    else err "Ollama non risponde. Verifica l'installazione."; exit 1; fi
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7 — Download modelli
# ═══════════════════════════════════════════════════════════════════════════
print_step 7 9 "Download modelli Ollama"

EMBED_TAG="nomic-embed-text"
INSTALLED_MODELS=$(curl -sf http://localhost:11434/api/tags | grep -o '"name":"[^"]*"' | cut -d'"' -f4 || true)

for model in "$CHAT_TAG" "$INGEST_TAG" "$EMBED_TAG"; do
    if echo "$INSTALLED_MODELS" | grep -qF "$model"; then
        ok "Modello già presente: $model"
        continue
    fi
    echo ""
    size=$( [[ "$model" == "$EMBED_TAG" ]] && echo "~274 MB" || echo "5–20 minuti" )
    info "Download $model ($size)..."
    echo ""
    if ollama pull "$model"; then
        ok "Modello $model scaricato"
    else
        warn "Download $model fallito — provo fallback qwen3:8b"
        ollama pull "qwen3:8b" && CHAT_TAG="qwen3:8b"
    fi
done

# ═══════════════════════════════════════════════════════════════════════════
# STEP 8 — .env
# ═══════════════════════════════════════════════════════════════════════════
print_step 8 9 "Configurazione .env"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_PATH="$SCRIPT_DIR/.env"
OCR_DEVICE=$( [[ "$USE_GPU" == true ]] && echo "cuda" || echo "cpu" )
WRITE_ENV=false

if [[ -f "$ENV_PATH" ]]; then
    warn ".env già esistente:"
    sed 's/^/    /' "$ENV_PATH"
    if [[ "$NONINTERACTIVE" == true ]]; then
        if [[ "$OVERWRITE_ENV" == true ]]; then
            WRITE_ENV=true; info "Sovrascrittura .env abilitata."
        else
            info "Mantenuto .env esistente (usa --overwrite-env per sovrascrivere)."
        fi
    else
        ask_yn "Sovrascrivere" && WRITE_ENV=true || info "Mantenuto .env esistente"
    fi
else
    WRITE_ENV=true
fi

if [[ "$WRITE_ENV" == true ]]; then
    cat > "$ENV_PATH" <<EOF
OLLAMA_URL=http://localhost:11434
CHAT_MODEL_NAME=$CHAT_TAG
INGEST_MODEL_NAME=$INGEST_TAG
OCR_DEVICE=$OCR_DEVICE
OCR_BACKEND=$OCR_BACKEND
RAW_DIR=raw
WIKI_DIR=wiki
EOF
    ok ".env scritto"
    info "CHAT_MODEL_NAME=$CHAT_TAG"
    info "INGEST_MODEL_NAME=$INGEST_TAG"
    info "OCR_DEVICE=$OCR_DEVICE"
fi

# ═══════════════════════════════════════════════════════════════════════════
# STEP 9 — Python dependencies
# ═══════════════════════════════════════════════════════════════════════════
print_step 9 9 "Dipendenze Python"

info "pip install -r backend/requirements.txt ..."
$PY_CMD -m pip install -r "$SCRIPT_DIR/backend/requirements.txt" --quiet
ok "Dipendenze installate"

# ═══════════════════════════════════════════════════════════════════════════
# VERIFICA FINALE
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}  ╔═════════════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}  ║${RESET}${BOLD}            VERIFICA INSTALLAZIONE                   ${RESET}${CYAN}║${RESET}"
echo -e "${CYAN}  ╚═════════════════════════════════════════════════════╝${RESET}"

# Ollama
if curl -sf http://localhost:11434/api/tags &>/dev/null; then
    ok "Ollama risponde"
else
    err "Ollama non risponde"
fi

# LLM test
info "Test risposta LLM (attendere)..."
LLM_RESP=$(curl -sf -X POST http://localhost:11434/api/chat \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$CHAT_TAG\",\"messages\":[{\"role\":\"user\",\"content\":\"Rispondi con: ok\"}],\"stream\":false,\"think\":false,\"options\":{\"num_predict\":3}}" \
    --max-time 180 2>/dev/null | grep -o '"content":"[^"]*"' | cut -d'"' -f4 || true)
[[ -n "$LLM_RESP" ]] && ok "LLM risponde: $LLM_RESP" || warn "Test LLM non completato (modello non ancora caricato)"

# Tesseract
cmd_exists tesseract && ok "Tesseract OK" || warn "Tesseract non in PATH"

# Config
CFG=$($PY_CMD -c "from backend.config import settings; print(f'chat={settings.chat_model_name} ingest={settings.ingest_model_name} ocr={settings.ocr_device}')" 2>/dev/null || true)
[[ -n "$CFG" ]] && ok "Config backend: $CFG" || warn "Config backend non verificabile"

# ═══════════════════════════════════════════════════════════════════════════
# GUIDA USO FINALE
# ═══════════════════════════════════════════════════════════════════════════
echo ""
echo -e "${CYAN}  ╔═════════════════════════════════════════════════════════════╗${RESET}"
echo -e "${CYAN}  ║${RESET}${BOLD}   🎉  INSTALLAZIONE COMPLETATA — COME USARE LLM WIKI       ${RESET}${CYAN}║${RESET}"
echo -e "${CYAN}  ╚═════════════════════════════════════════════════════════════╝${RESET}"
echo ""
echo -e "${BOLD}  AVVIO${RESET}"
echo "  ┌────────────────────────────────────────────────────────────┐"
echo -e "  │  ${CYAN}ollama serve${RESET}                   # avvia il motore AI        │"
echo -e "  │  ${CYAN}uvicorn backend.main:app --reload${RESET}  # avvia il backend    │"
echo -e "  │  Apri browser: ${GREEN}http://localhost:8000${RESET}                       │"
echo "  └────────────────────────────────────────────────────────────┘"
echo ""
echo -e "${BOLD}  COME USARE IL SISTEMA${RESET}"
echo ""
echo -e "  1. ${GREEN}Carica documenti${RESET} — Trascina PDF, immagini o DOCX nel"
echo "     pannello sinistro dell'interfaccia web."
echo "     Il sistema esegue OCR automatico e indicizza il contenuto."
echo ""
echo -e "  2. ${GREEN}Fai domande${RESET} — Scrivi una domanda nella chat."
echo "     L'AI risponde basandosi SOLO sui documenti caricati,"
echo "     citando il file sorgente per ogni informazione."
echo ""
echo -e "  3. ${GREEN}Visualizza log${RESET} — Clicca sul pannello 'Log' in basso"
echo "     per seguire il progresso dell'elaborazione in tempo reale."
echo ""
echo -e "${BOLD}  MODELLI CONFIGURATI${RESET}"
echo -e "  • Chat    : ${CYAN}$CHAT_TAG${RESET} — risponde alle domande"
echo -e "  • Ingest  : ${CYAN}$INGEST_TAG${RESET} — elabora i documenti"
echo "  • Motore  : $ACCEL"
echo "  • TTFT    : ~$ETA"
echo ""
echo -e "${BOLD}  FORMATI SUPPORTATI${RESET}"
echo "  PDF  •  PNG/JPG/TIFF (OCR)  •  DOCX  •  TXT  •  Markdown"
echo ""
echo -e "${DIM}  Documentazione: CLAUDE.md | Problemi: README.md#troubleshooting${RESET}"
echo ""
