#Requires -Version 5.1
<#
.SYNOPSIS
    LLM Wiki — Windows Installer
.DESCRIPTION
    Interactive installer: hardware detection, model selection, dependency install,
    Ollama setup, model download, verification and usage guide.
.PARAMETER NonInteractive
    Skip all prompts. Requires other params to supply answers.
.PARAMETER UseGpu
    Enable GPU acceleration (requires NVIDIA GPU with CUDA).
.PARAMETER RamLlm
    GB of RAM to allocate to the LLM (default: 60% of system RAM).
.PARAMETER PreferSpeed
    Prefer speed over quality when selecting models.
.PARAMETER OcrBackend
    OCR backend: tesseract | easyocr | got_ocr2 | ollama (default: tesseract).
.PARAMETER ChatModel
    Override chat model tag (skips auto-selection).
.PARAMETER IngestModel
    Override ingest model tag (skips auto-selection).
.PARAMETER OverwriteEnv
    Overwrite existing .env without prompting.
#>
param(
    [switch]$NonInteractive,
    [switch]$UseGpu,
    [double]$RamLlm     = 0.0,
    [switch]$PreferSpeed,
    [string]$OcrBackend  = "",
    [string]$ChatModel   = "",
    [string]$IngestModel = "",
    [switch]$OverwriteEnv
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ── ANSI colors (Windows 10+ Terminal) ──────────────────────────────────────
$ESC = [char]27
function clr($code, $text) { "$ESC[${code}m$text$ESC[0m" }
function green($t)  { clr "32" $t }
function yellow($t) { clr "33" $t }
function cyan($t)   { clr "36" $t }
function red($t)    { clr "31" $t }
function bold($t)   { clr "1"  $t }
function dim($t)    { clr "2"  $t }

# ── Helpers ──────────────────────────────────────────────────────────────────
function Print-Banner {
    Write-Host ""
    Write-Host (cyan "  ██╗     ██╗     ███╗   ███╗    ██╗    ██╗██╗██╗  ██╗██╗")
    Write-Host (cyan "  ██║     ██║     ████╗ ████║    ██║    ██║██║██║ ██╔╝██║")
    Write-Host (cyan "  ██║     ██║     ██╔████╔██║    ██║ █╗ ██║██║█████╔╝ ██║")
    Write-Host (cyan "  ██║     ██║     ██║╚██╔╝██║    ██║███╗██║██║██╔═██╗ ██║")
    Write-Host (cyan "  ███████╗███████╗██║ ╚═╝ ██║    ╚███╔███╔╝██║██║  ██╗██║")
    Write-Host (cyan "  ╚══════╝╚══════╝╚═╝     ╚═╝     ╚══╝╚══╝ ╚═╝╚═╝  ╚═╝╚═╝")
    Write-Host ""
    Write-Host (bold "  Wiki personale offline con OCR automatico e chat AI")
    Write-Host (dim  "  Installer v1.0 — Windows")
    Write-Host ""
}

function Print-Step($n, $total, $label) {
    Write-Host ""
    Write-Host (cyan "  ┌─────────────────────────────────────────────────────┐")
    Write-Host (cyan "  │") " $(bold "STEP $n/$total") — $label" (cyan "")
    Write-Host (cyan "  └─────────────────────────────────────────────────────┘")
}

function Print-Ok($msg)   { Write-Host "  $(green "✓") $msg" }
function Print-Warn($msg) { Write-Host "  $(yellow "⚠") $msg" }
function Print-Err($msg)  { Write-Host "  $(red "✗") $msg" }
function Print-Info($msg) { Write-Host "  $(dim "·") $msg" }

function Ask($prompt, $default) {
    $hint = if ($default) { dim " [$default]" } else { "" }
    Write-Host -NoNewline "  $(cyan "?") $prompt$hint : "
    $ans = Read-Host
    if (-not $ans -and $default) { return $default }
    return $ans
}

function Ask-YesNo($prompt, $default = "s") {
    $hint = if ($default -eq "s") { dim " [S/n]" } else { dim " [s/N]" }
    Write-Host -NoNewline "  $(cyan "?") $prompt$hint : "
    $ans = (Read-Host).Trim().ToLower()
    if (-not $ans) { return ($default -eq "s") }
    return ($ans -eq "s" -or $ans -eq "si" -or $ans -eq "y" -or $ans -eq "yes")
}

function Spinner($job, $label) {
    $frames = @("⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏")
    $i = 0
    while (-not $job.AsyncWaitHandle.WaitOne(100)) {
        Write-Host -NoNewline "`r  $(cyan $frames[$i % $frames.Count]) $label   "
        $i++
    }
    Write-Host -NoNewline "`r"
}

function Run-WithSpinner($label, [scriptblock]$block) {
    $frames = @("⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏")
    $i = 0
    $job = Start-Job -ScriptBlock $block
    while ($job.State -eq "Running") {
        Write-Host -NoNewline "`r  $(cyan $frames[$i % $frames.Count]) $label   "
        Start-Sleep -Milliseconds 100
        $i++
    }
    Write-Host -NoNewline "`r                                                        `r"
    $result = Receive-Job $job -ErrorAction SilentlyContinue
    Remove-Job $job -Force
    return $result
}

function Check-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

# ── MAIN ─────────────────────────────────────────────────────────────────────
Print-Banner

Write-Host (bold "  Questo script installerà:") ""
Write-Host "  • Python ≥ 3.11 + dipendenze backend"
Write-Host "  • Tesseract OCR"
Write-Host "  • Ollama + modello LLM (qwen3)"
Write-Host "  • Configurazione .env automatica"
Write-Host ""

if ($NonInteractive) {
    Print-Info "Modalità non-interattiva — installazione avviata automaticamente."
} else {
    $proceed = Ask-YesNo "Vuoi procedere con l'installazione"
    if (-not $proceed) { Write-Host (yellow "  Installazione annullata."); exit 0 }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1 — Hardware detection
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 1 9 "Rilevamento hardware"

$RAM_GB = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 1)
$CPU = (Get-CimInstance Win32_Processor).Name.Trim()
$CPU_CORES = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors

$VRAM_GB = 0.0
$GPU_NAME = "Non rilevata"
$GPU_TYPE = "none"

# NVIDIA check
try {
    $nvOut = nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    if ($nvOut) {
        $parts = $nvOut -split ","
        $GPU_NAME = $parts[0].Trim()
        $VRAM_MB  = [int]($parts[1].Trim() -replace "[^0-9]","")
        $VRAM_GB  = [math]::Round($VRAM_MB / 1024, 1)
        if ($VRAM_GB -ge 4) { $GPU_TYPE = "nvidia" } else { $GPU_TYPE = "nvidia-low" }
    }
} catch {}

# AMD check (iGPU — not usable on Windows)
if ($GPU_TYPE -eq "none") {
    $gpuInfo = Get-CimInstance Win32_VideoController | Select-Object -First 1
    if ($gpuInfo) { $GPU_NAME = $gpuInfo.Name.Trim() }
}

Write-Host ""
Print-Info "CPU  : $CPU ($CPU_CORES thread)"
Print-Info "RAM  : $RAM_GB GB"

switch ($GPU_TYPE) {
    "nvidia"     { Print-Ok  "GPU  : $GPU_NAME — $VRAM_GB GB VRAM (CUDA disponibile)" }
    "nvidia-low" { Print-Warn "GPU  : $GPU_NAME — $VRAM_GB GB VRAM (VRAM bassa, CPU-only)" }
    default      { Print-Warn "GPU  : $GPU_NAME — CPU-only (ROCm non supportato su Windows)" }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 2 — User interview
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 2 9 "Configurazione"

$USE_GPU = $false
if ($GPU_TYPE -eq "nvidia") {
    if ($NonInteractive) {
        $USE_GPU = $UseGpu
        Print-Info "GPU: accelerazione = $USE_GPU"
    } else {
        $USE_GPU = Ask-YesNo "GPU NVIDIA rilevata ($GPU_NAME $VRAM_GB GB). Abilitare accelerazione GPU"
    }
} elseif ($GPU_TYPE -eq "nvidia-low") {
    Print-Warn "VRAM insufficiente per LLM — verrà usata la CPU."
} else {
    Print-Info "Nessuna GPU dedicata — modalità CPU-only."
}

$RAM_SUGGEST = [math]::Max(4, [math]::Round($RAM_GB * 0.6))
if ($NonInteractive -and $RamLlm -gt 0) {
    $RAM_LLM = $RamLlm
    Print-Info "RAM LLM: $RAM_LLM GB"
} else {
    $RAM_LLM_STR = Ask "RAM da dedicare all'LLM (GB)" "$RAM_SUGGEST"
    $RAM_LLM = [double]$RAM_LLM_STR
}

if ($NonInteractive) {
    $PREF = $PreferSpeed
    Print-Info "Preferenza velocità: $PREF"
} else {
    $PREF = Ask-YesNo "Preferisci velocità rispetto alla qualità delle risposte" "n"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 3 — Model selection
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 3 9 "Selezione modelli"

if ($ChatModel -ne "" -and $IngestModel -ne "") {
    $CHAT_TAG   = $ChatModel
    $INGEST_TAG = $IngestModel
    $ACCEL = if ($USE_GPU) { "GPU CUDA" } else { "CPU-only" }
    $ETA   = "N/D"
} elseif ($USE_GPU) {
    if    ($VRAM_GB -ge 24) { $CHAT_TAG = "qwen3:14b"; $INGEST_TAG = "qwen3:32b-a3b"; $ETA = "1–3s" }
    elseif($VRAM_GB -ge 12) { $CHAT_TAG = "qwen3:14b"; $INGEST_TAG = "qwen3:32b-a3b"; $ETA = "2–5s" }
    elseif($VRAM_GB -ge 8)  { $CHAT_TAG = "qwen3:8b";  $INGEST_TAG = "qwen3:14b";     $ETA = "3–8s" }
    else                    { $CHAT_TAG = "qwen3:4b";  $INGEST_TAG = "qwen3:8b";      $ETA = "5–12s" }
    $ACCEL = "GPU CUDA"
} else {
    if    ($RAM_LLM -le 4)  { $CHAT_TAG = "qwen3:1.7b"; $INGEST_TAG = "qwen3:1.7b"; $ETA = "20–40s" }
    elseif($RAM_LLM -le 6)  { $CHAT_TAG = "qwen3:1.7b"; $INGEST_TAG = "qwen3:4b";  $ETA = "30–60s" }
    elseif($RAM_LLM -le 10) { $CHAT_TAG = "qwen3:4b";   $INGEST_TAG = "qwen3:8b";  $ETA = "60–120s" }
    elseif($RAM_LLM -le 14) { $CHAT_TAG = "qwen3:4b";   $INGEST_TAG = "qwen3:14b"; $ETA = "90–150s" }
    elseif($RAM_LLM -le 20) { $CHAT_TAG = "qwen3:8b";   $INGEST_TAG = "qwen3:14b"; $ETA = "120–190s" }
    else                    { $CHAT_TAG = "qwen3:14b";  $INGEST_TAG = "qwen3:30b-a3b"; $ETA = "150–300s" }
    $ACCEL = "CPU-only"
}

if ($PREF) {
    # prefer speed: downgrade ingest to chat model if different
    if ($INGEST_TAG -ne $CHAT_TAG) { $INGEST_TAG = $CHAT_TAG }
}

Print-Ok  "Chat model  : $CHAT_TAG"
Print-Ok  "Ingest model: $INGEST_TAG"
Print-Info "Accelerazione: $ACCEL"
Print-Info "Risposta attesa: ~$ETA"

# OCR backend selection
Write-Host ""
Write-Host (bold "  Quale backend OCR vuoi usare?")
Write-Host "  1. $(green "tesseract") (default) — veloce, leggero, scan puliti — $(dim "~50 MB, già installato")"
Write-Host "  2. $(yellow "easyocr") — migliore con font non-standard — $(dim "~120 MB auto-download")"
Write-Host "  3. $(yellow "got_ocr2") — ottima qualità, layout complessi, tabelle — $(dim "~580 MB auto-download, richiede transformers+torch")"
Write-Host "  4. $(red "ollama") — massima qualità, lenta — $(dim "~5.5 GB, GPU consigliata")"
if ($USE_GPU) {
    Write-Host (cyan "  GPU rilevata: got_ocr2 e ollama useranno accelerazione CUDA automaticamente.")
}
if ($NonInteractive -and $OcrBackend -ne "") {
    $OCR_BACKEND = $OcrBackend
    Print-Info "OCR backend: $OCR_BACKEND"
} else {
    $ocrChoice = ""
    while ($ocrChoice -notmatch "^[1-4]$") {
        $ocrChoice = Read-Host "  Scelta [1-4]"
    }
    $OCR_BACKEND = switch ($ocrChoice) {
        "1" { "tesseract" }
        "2" { "easyocr" }
        "3" { "got_ocr2" }
        "4" { "ollama" }
    }
}
Print-Ok "OCR backend selezionato: $OCR_BACKEND"

# ═══════════════════════════════════════════════════════════════════════════
# STEP 4 — Python check
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 4 9 "Python ≥ 3.11"

$pyOk = $false
if (Check-Command python) {
    $pyVer = python --version 2>&1
    if ($pyVer -match "3\.(\d+)" -and [int]$Matches[1] -ge 11) {
        Print-Ok "Python $pyVer già installato"
        $pyOk = $true
    } else {
        Print-Warn "Python trovato ma versione insufficiente: $pyVer"
    }
}

if (-not $pyOk) {
    Print-Info "Installazione Python 3.11 via winget..."
    winget install Python.Python.3.11 --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
        Print-Ok "Python 3.11 installato. Riavvia il terminale e riesegui lo script se i comandi seguenti falliscono."
    } else {
        Print-Err "Installazione Python fallita. Installa manualmente da https://python.org"
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 5 — Tesseract OCR
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 5 9 "Tesseract OCR"

if (Check-Command tesseract) {
    $tessVer = tesseract --version 2>&1 | Select-Object -First 1
    Print-Ok "Tesseract già installato: $tessVer"
} else {
    Print-Info "Installazione Tesseract via winget..."
    winget install UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -eq 0) {
        $tessPath = "C:\Program Files\Tesseract-OCR"
        $currentPath = [System.Environment]::GetEnvironmentVariable("PATH", "Machine")
        if ($currentPath -notlike "*Tesseract*") {
            [System.Environment]::SetEnvironmentVariable("PATH", "$currentPath;$tessPath", "Machine")
            $env:PATH = "$env:PATH;$tessPath"
            Print-Ok "Tesseract installato e aggiunto al PATH"
        } else {
            Print-Ok "Tesseract installato"
        }
    } else {
        Print-Warn "Installazione Tesseract fallita — scarica da https://github.com/UB-Mannheim/tesseract/wiki"
    }
}

# Install extra OCR backend if selected
if ($OCR_BACKEND -eq "easyocr") {
    Print-Info "Installazione EasyOCR (~120 MB download al primo utilizzo)..."
    pip install easyocr --quiet
    if ($LASTEXITCODE -eq 0) { Print-Ok "EasyOCR installato" }
    else { Print-Warn "EasyOCR installazione fallita — usa: pip install easyocr" }
}
if ($OCR_BACKEND -eq "got_ocr2") {
    Print-Info "Installazione dipendenze GOT-OCR2 (transformers, torch, torchvision)..."
    Print-Info "Nota: modello ~580 MB scaricato automaticamente al primo utilizzo."
    pip install transformers torch torchvision --quiet
    if ($LASTEXITCODE -eq 0) { Print-Ok "GOT-OCR2 dipendenze installate" }
    else { Print-Warn "Installazione dipendenze fallita — usa: pip install transformers torch torchvision" }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 6 — Ollama
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 6 9 "Ollama"

$ollamaRunning = $false
try {
    $resp = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    $ollamaRunning = $true
    Print-Ok "Ollama già in esecuzione"
} catch {}

if (-not $ollamaRunning) {
    if (-not (Check-Command ollama)) {
        Print-Info "Installazione Ollama via winget..."
        winget install Ollama.Ollama --silent --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -ne 0) {
            Print-Err "Installazione Ollama fallita. Scarica da https://ollama.com/download"
            exit 1
        }
        Print-Ok "Ollama installato"
        Start-Sleep -Seconds 3
    }

    Print-Info "Avvio Ollama daemon..."
    Start-Process "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4

    $retries = 0
    while ($retries -lt 5) {
        try {
            Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop | Out-Null
            $ollamaRunning = $true
            break
        } catch { Start-Sleep -Seconds 2; $retries++ }
    }

    if ($ollamaRunning) { Print-Ok "Ollama avviato su http://localhost:11434" }
    else { Print-Err "Ollama non risponde. Controlla l'installazione."; exit 1 }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 7 — Download modelli
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 7 9 "Download modelli Ollama"

$EMBED_TAG = "nomic-embed-text"
$models = @($CHAT_TAG)
if ($INGEST_TAG -ne $CHAT_TAG) { $models += $INGEST_TAG }
$models += $EMBED_TAG  # semantic cache embedding model (~274 MB)

# Check which models already installed
$installed = (Invoke-RestMethod -Uri "http://localhost:11434/api/tags").models.name

foreach ($model in $models) {
    if ($installed -contains $model) {
        Print-Ok "Modello già presente: $model"
        continue
    }
    Write-Host ""
    $size = if ($model -eq $EMBED_TAG) { "~274 MB" } else { "5–20 minuti" }
    Print-Info "Download $model ($size)..."
    Write-Host ""
    ollama pull $model
    if ($LASTEXITCODE -eq 0) {
        Print-Ok "Modello $model scaricato"
    } else {
        Print-Warn "Download $model fallito — provo con fallback qwen3:8b"
        ollama pull "qwen3:8b"
    }
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 8 — .env
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 8 9 "Configurazione .env"

$OCR_DEVICE = if ($USE_GPU) { "cuda" } else { "cpu" }
$envPath = Join-Path $PSScriptRoot ".env"

if (Test-Path $envPath) {
    Print-Warn ".env già esistente:"
    Get-Content $envPath | ForEach-Object { Write-Host "    $_" }
    if ($NonInteractive) {
        if ($OverwriteEnv) { $write = $true; Print-Info "Sovrascrittura .env abilitata." }
        else { Print-Info "Mantenuto .env esistente (usa -OverwriteEnv per sovrascrivere)." }
    } else {
        $overwrite = Ask-YesNo "Sovrascrivere"
        if (-not $overwrite) { Print-Info "Mantenuto .env esistente" }
        else { $write = $true }
    }
} else { $write = $true }

if ($write) {
    $envContent = @"
OLLAMA_URL=http://localhost:11434
CHAT_MODEL_NAME=$CHAT_TAG
INGEST_MODEL_NAME=$INGEST_TAG
OCR_DEVICE=$OCR_DEVICE
OCR_BACKEND=$OCR_BACKEND
RAW_DIR=raw
WIKI_DIR=wiki
"@
    [System.IO.File]::WriteAllText($envPath, $envContent, [System.Text.UTF8Encoding]::new($false))
    Print-Ok ".env scritto"
    Print-Info "CHAT_MODEL_NAME=$CHAT_TAG"
    Print-Info "INGEST_MODEL_NAME=$INGEST_TAG"
    Print-Info "OCR_DEVICE=$OCR_DEVICE"
}

# ═══════════════════════════════════════════════════════════════════════════
# STEP 9 — Python dependencies
# ═══════════════════════════════════════════════════════════════════════════
Print-Step 9 9 "Dipendenze Python"

$reqPath = Join-Path $PSScriptRoot "backend\requirements.txt"
Print-Info "pip install -r backend/requirements.txt ..."
pip install -r $reqPath --quiet
if ($LASTEXITCODE -eq 0) { Print-Ok "Dipendenze installate" }
else { Print-Err "pip install fallito — controlla backend/requirements.txt" }

# ═══════════════════════════════════════════════════════════════════════════
# VERIFICA FINALE
# ═══════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host (cyan "  ╔═════════════════════════════════════════════════════╗")
Write-Host (cyan "  ║") (bold "            VERIFICA INSTALLAZIONE                   ") (cyan "║")
Write-Host (cyan "  ╚═════════════════════════════════════════════════════╝")

$allOk = $true

# Ollama
try {
    Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 5 -ErrorAction Stop | Out-Null
    Print-Ok "Ollama risponde"
} catch { Print-Err "Ollama non risponde"; $allOk = $false }

# Test LLM
try {
    Print-Info "Test risposta LLM (attendere)..."
    $body = "{`"model`":`"$CHAT_TAG`",`"messages`":[{`"role`":`"user`",`"content`":`"Rispondi con: ok`"}],`"stream`":false,`"think`":false,`"options`":{`"num_predict`":3}}"
    $start = Get-Date
    $r = Invoke-RestMethod -Uri "http://localhost:11434/api/chat" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 180
    $ms = [int]((Get-Date) - $start).TotalMilliseconds
    Print-Ok "LLM risponde in ${ms}ms: $($r.message.content.Trim())"
} catch { Print-Warn "Test LLM fallito (modello potrebbe non essere in RAM)"; }

# Tesseract
if (Check-Command tesseract) { Print-Ok "Tesseract OK" }
else { Print-Warn "Tesseract non in PATH — aggiungi C:\Program Files\Tesseract-OCR manualmente" }

# Python config
try {
    $cfg = python -c "from backend.config import settings; print(f'chat={settings.chat_model_name} ingest={settings.ingest_model_name} ocr={settings.ocr_device}')" 2>&1
    Print-Ok "Config backend: $cfg"
} catch { Print-Warn "Config backend non verificabile" }

# ═══════════════════════════════════════════════════════════════════════════
# GUIDA USO FINALE
# ═══════════════════════════════════════════════════════════════════════════
Write-Host ""
Write-Host (cyan "  ╔═════════════════════════════════════════════════════════════╗")
Write-Host (cyan "  ║") (bold "   🎉  INSTALLAZIONE COMPLETATA — COME USARE LLM WIKI       ") (cyan "║")
Write-Host (cyan "  ╚═════════════════════════════════════════════════════════════╝")
Write-Host ""
Write-Host (bold "  AVVIO")
Write-Host "  ┌────────────────────────────────────────────────────────────┐"
Write-Host "  │  $(cyan "ollama serve")                  # avvia il motore AI        │"
Write-Host "  │  $(cyan "uvicorn backend.main:app --reload")  # avvia il backend    │"
Write-Host "  │  Apri browser: $(green "http://localhost:8000")                       │"
Write-Host "  └────────────────────────────────────────────────────────────┘"
Write-Host ""
Write-Host (bold "  COME USARE IL SISTEMA")
Write-Host ""
Write-Host "  1. $(green "Carica documenti") — Trascina PDF, immagini o DOCX nel"
Write-Host "     pannello sinistro dell'interfaccia web."
Write-Host "     Il sistema esegue OCR automatico e indicizza il contenuto."
Write-Host ""
Write-Host "  2. $(green "Fai domande") — Scrivi una domanda nella chat."
Write-Host "     L'AI risponde basandosi SOLO sui documenti caricati,"
Write-Host "     citando il file sorgente per ogni informazione."
Write-Host ""
Write-Host "  3. $(green "Visualizza log") — Clicca sul pannello 'Log' in basso"
Write-Host "     per seguire il progresso dell'elaborazione in tempo reale."
Write-Host ""
Write-Host (bold "  MODELLI CONFIGURATI")
Write-Host "  • Chat    : $(cyan $CHAT_TAG) — risponde alle domande"
Write-Host "  • Ingest  : $(cyan $INGEST_TAG) — elabora i documenti"
Write-Host "  • Motore  : $ACCEL"
Write-Host "  • TTFT    : ~$ETA"
Write-Host ""
Write-Host (bold "  FORMATI SUPPORTATI")
Write-Host "  PDF  •  PNG/JPG/TIFF (OCR)  •  DOCX  •  TXT  •  Markdown"
Write-Host ""
Write-Host (dim "  Documentazione: CLAUDE.md | Problemi: README.md#troubleshooting")
Write-Host ""
