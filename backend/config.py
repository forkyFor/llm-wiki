import platform
import subprocess  # nosec B404
from pathlib import Path
from pydantic_settings import BaseSettings


def _nvidia_vram_gb() -> float:
    """First NVIDIA GPU VRAM in GB, 0 if none/error."""
    try:
        r = subprocess.run(  # nosec B603 B607
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return int(r.stdout.strip().splitlines()[0].strip()) / 1024  # MiB → GB
    except Exception:
        return 0.0


def _ram_gb() -> float:
    """Total physical RAM in GB."""
    try:
        if platform.system() == "Windows":
            r = subprocess.run(  # nosec B603 B607
                ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"],
                capture_output=True, text=True, timeout=5,
            )
            for line in r.stdout.splitlines():
                if "TotalPhysicalMemory=" in line:
                    return int(line.split("=")[1].strip()) / (1024 ** 3)
        else:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        return int(line.split()[1]) / (1024 ** 2)  # kB → GB
    except Exception:  # nosec B110
        pass
    return 8.0  # safe fallback


def _auto_select(vram_gb: float, ram_gb: float) -> tuple[str, str, str]:
    """
    Returns (chat_model, ingest_model, ocr_device).
    GPU path (NVIDIA CUDA) takes priority. Falls back to RAM-based CPU path.
    """
    if vram_gb >= 12:
        return "qwen3:14b", "qwen3:32b-a3b", "cuda"
    if vram_gb >= 8:
        return "qwen3:8b", "qwen3:14b", "cuda"
    if vram_gb >= 4:
        return "qwen3:4b", "qwen3:8b", "cuda"

    # CPU-only — select by RAM
    if ram_gb <= 4:
        return "qwen3:1.7b", "qwen3:1.7b", "cpu"
    if ram_gb <= 6:
        return "qwen3:1.7b", "qwen3:4b", "cpu"
    if ram_gb <= 10:
        return "qwen3:4b", "qwen3:8b", "cpu"
    if ram_gb <= 14:
        return "qwen3:4b", "qwen3:14b", "cpu"
    if ram_gb <= 20:
        return "qwen3:8b", "qwen3:14b", "cpu"
    return "qwen3:14b", "qwen3:30b-a3b", "cpu"


# Detect once at import — adds ~200ms to startup, acceptable.
DETECTED_VRAM_GB: float = _nvidia_vram_gb()
DETECTED_RAM_GB: float = _ram_gb()
_AUTO_CHAT, _AUTO_INGEST, _AUTO_OCR_DEVICE = _auto_select(DETECTED_VRAM_GB, DETECTED_RAM_GB)


class Settings(BaseSettings):
    raw_dir: Path = Path("raw")
    wiki_dir: Path = Path("wiki")

    # Auto-detected defaults — overridden by .env or env vars
    ocr_device: str = _AUTO_OCR_DEVICE
    ocr_backend: str = "tesseract"
    ocr_model_name: str = "minicpm-v"
    ollama_url: str = "http://localhost:11434"
    chat_model_name: str = _AUTO_CHAT
    ingest_model_name: str = _AUTO_INGEST

    # Semantic cache
    embed_model_name: str = "nomic-embed-text"
    cache_similarity_threshold: float = 0.85
    cache_max_entries: int = 500

    host: str = "127.0.0.1"
    port: int = 8000

    # Auth
    data_dir: Path = Path("data")
    jwt_secret: str = ""
    jwt_expire_hours: int = 24
    jwt_secure_cookie: bool = False
    admin_username: str = ""
    admin_password: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


def hardware_summary() -> str:
    """Human-readable hardware detection result — call after logging is configured."""
    if DETECTED_VRAM_GB >= 4:
        hw = f"GPU CUDA {DETECTED_VRAM_GB:.1f}GB"
    else:
        hw = f"CPU-only RAM={DETECTED_RAM_GB:.1f}GB"
    src = "(auto)" if settings.chat_model_name == _AUTO_CHAT else "(.env)"
    return (
        f"{hw} | chat={settings.chat_model_name} "
        f"ingest={settings.ingest_model_name} "
        f"embed={settings.embed_model_name} "
        f"ocr_device={settings.ocr_device} {src}"
    )
