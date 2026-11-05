"""Start the web server and open a browser once its homepage is ready."""
import os
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8000"


def open_when_ready():
    # Bypass system proxies for the local readiness check.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for _ in range(120):
        try:
            with opener.open(URL, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(URL)
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.5)
    print(f"Browser did not open automatically. Visit {URL} after startup.")


def start_local_ollama():
    import model_settings

    settings = model_settings.current()
    if settings.provider != "ollama":
        return
    if settings.ollama_url not in (
        "http://127.0.0.1:11434", "http://localhost:11434"
    ):
        return
    executable = shutil.which("ollama")
    if not executable:
        print("Ollama not found. Install it for local models, or configure an online model in the webpage.")
        return
    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=1):
            return
    except OSError:
        pass
    # Ollama stays available after the webpage closes, like the desktop service.
    try:
        subprocess.Popen(
            [executable, "serve"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        print("Starting Ollama in the background. Models must already be downloaded.")
    except OSError as exc:
        print(f"Could not start Ollama: {exc}. Configure the model in the webpage.")


def main():
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    try:
        with socket.socket() as probe:
            probe.bind(("0.0.0.0", 8000))
    except OSError:
        print("Port 8000 is unavailable. Close the existing server and try again.")
        return 1
    start_local_ollama()
    threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        runpy.run_path(str(ROOT / "web_app.py"), run_name="__main__")
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
