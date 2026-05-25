"""
llm_wiki.exe entry point — starts Ollama + FastAPI, opens browser.
Bundled by PyInstaller.
"""
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def ensure_ollama_running():
    """Start Ollama daemon if not already responding."""
    import httpx
    try:
        r = httpx.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            print("Ollama already running.")
            return
    except Exception:
        pass
    print("Starting Ollama daemon...")
    subprocess.Popen(
        ["ollama", "serve"],
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    for _ in range(30):
        time.sleep(1)
        try:
            r = httpx.get("http://localhost:11434/api/tags", timeout=2)
            if r.status_code == 200:
                print("Ollama ready.")
                return
        except Exception:
            pass
    print("Warning: Ollama did not respond in 30s.")


def open_browser():
    time.sleep(2)
    webbrowser.open("http://localhost:8000")


if __name__ == "__main__":
    base = _base_dir()
    os.chdir(base)
    ensure_ollama_running()
    threading.Thread(target=open_browser, daemon=True).start()
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, log_level="info")
