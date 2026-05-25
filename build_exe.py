"""
Build Windows EXEs with PyInstaller.

Usage:
    pip install pyinstaller
    python build_exe.py

Produces:
    dist/llm_wiki_setup.exe  — first-run installer (needs internet)
    dist/llm_wiki.exe        — daily launcher (offline)
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def run(args):
    print("Running:", " ".join(args))
    subprocess.check_call(args)


def build_launcher():
    """Build the main launcher EXE (offline use)."""
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "llm_wiki",
        "--icon", "NONE",
        "--add-data", f"frontend{';'}frontend",
        "--add-data", f"wiki{';'}wiki",
        "--add-data", f"instructions.md{';'}.",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "watchdog.observers.polling",
        "--collect-all", "glmocr",
        str(ROOT / "launcher.py"),
    ])


def build_setup():
    """Build the setup EXE (first-run, needs internet)."""
    run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "llm_wiki_setup",
        "--icon", "NONE",
        "--hidden-import", "tkinter",
        str(ROOT / "setup_installer.py"),
    ])


if __name__ == "__main__":
    build_launcher()
    build_setup()
    print("\nBuild complete. Check dist/ folder.")
