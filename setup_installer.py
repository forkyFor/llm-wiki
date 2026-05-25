"""
llm_wiki_setup.exe — first-run installer for Windows.
Installs Ollama and pulls the configured Qwen3 model.
Shows progress in a tkinter window.
"""
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

DEFAULT_MODEL_TAG = "qwen3:14b"


class InstallerUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("LLM Wiki — Setup")
        self.root.geometry("600x420")
        self.root.resizable(False, False)
        self.root.configure(bg="#0f1117")

        tk.Label(self.root, text="LLM Wiki Setup", font=("Segoe UI", 16, "bold"),
                 bg="#0f1117", fg="#6c8ef5").pack(pady=(20, 4))
        tk.Label(self.root, text="Installa Ollama e scarica il modello Qwen3", font=("Segoe UI", 10),
                 bg="#0f1117", fg="#8b90a8").pack(pady=(0, 16))

        self.log = scrolledtext.ScrolledText(
            self.root, height=14, state="disabled", bg="#1a1d27",
            fg="#e1e4f0", font=("Consolas", 9), relief="flat"
        )
        self.log.pack(padx=20, fill="both", expand=True)

        self.status = tk.Label(self.root, text="Inizializzazione...", font=("Segoe UI", 9),
                               bg="#0f1117", fg="#f0a84e")
        self.status.pack(pady=8)

        self.close_btn = tk.Button(
            self.root, text="Chiudi", state="disabled",
            command=self.root.destroy,
            bg="#6c8ef5", fg="white", font=("Segoe UI", 10),
            relief="flat", padx=20
        )
        self.close_btn.pack(pady=(0, 16))

    def log_line(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, text: str, color: str = "#f0a84e"):
        self.status.configure(text=text, fg=color)

    def done(self, success: bool):
        if success:
            self.set_status("Setup completato. Pronto per l'uso.", "#4eca8b")
        else:
            self.set_status("Errore durante il setup. Controlla il log.", "#e05c5c")
        self.close_btn.configure(state="normal")

    def run(self):
        threading.Thread(target=self._install, daemon=True).start()
        self.root.mainloop()

    def _install(self):
        try:
            self._step_deps()
            self._step_ollama()
            self._step_pull_model()
            self.root.after(0, lambda: self.done(True))
        except Exception as e:
            self.root.after(0, lambda: self.log_line(f"ERRORE: {e}"))
            self.root.after(0, lambda: self.done(False))

    def _log(self, txt):
        self.root.after(0, lambda: self.log_line(txt))

    def _status(self, txt):
        self.root.after(0, lambda: self.set_status(txt))

    def _step_deps(self):
        self._status("Installazione dipendenze Python...")
        subprocess.check_call([sys.executable, "-m", "pip", "install",
                               "-r", "backend/requirements.txt", "-q"])
        self._log("Dipendenze installate.")

    def _step_ollama(self):
        import shutil
        import urllib.request
        self._status("Verifica Ollama...")
        if shutil.which("ollama"):
            self._log("Ollama già installato.")
            return
        installer_path = Path(__file__).parent / "OllamaSetup.exe"
        self._log("Download Ollama installer...")
        urllib.request.urlretrieve("https://ollama.com/download/OllamaSetup.exe", str(installer_path))
        subprocess.check_call([str(installer_path), "/S"])
        installer_path.unlink(missing_ok=True)
        self._log("Ollama installato.")

    def _step_pull_model(self):
        model_tag = os.environ.get("MODEL_NAME", DEFAULT_MODEL_TAG)
        self._status(f"Download modello {model_tag}...")
        self._log(f"ollama pull {model_tag}...")
        result = subprocess.run(["ollama", "pull", model_tag])
        if result.returncode != 0:
            raise RuntimeError(f"ollama pull {model_tag} fallito")
        self._log(f"Modello {model_tag} pronto.")


if __name__ == "__main__":
    InstallerUI().run()
