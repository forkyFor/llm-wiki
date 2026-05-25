"""Scarica il modello Ollama configurato. Eseguire una volta con internet."""
import os
import subprocess
import sys

DEFAULT_TAG = os.environ.get("MODEL_NAME", "qwen3:14b")


def pull_model(tag: str) -> None:
    print(f"Pulling: {tag}")
    result = subprocess.run(["ollama", "pull", tag])
    if result.returncode != 0:
        sys.exit(1)
    print(f"Modello {tag} pronto.")


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TAG
    pull_model(tag)
    print("Avvia con: uvicorn backend.main:app --reload")
