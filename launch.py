"""One-step launcher: installs jsonschema if missing, starts the console and opens the browser. Double-click start.bat (Windows) or run start.sh."""
import importlib.util, subprocess, sys, threading, time, webbrowser, urllib.request

PORT = 8765
if importlib.util.find_spec("jsonschema") is None:
    print("Installing jsonschema (one time)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "jsonschema>=4"])


def open_when_ready():
    for _ in range(60):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=1)
            webbrowser.open(f"http://127.0.0.1:{PORT}/")
            return
        except Exception:
            time.sleep(0.5)


threading.Thread(target=open_when_ready, daemon=True).start()
print(f"Console at http://127.0.0.1:{PORT}  (close this window to stop it)")
subprocess.call([sys.executable, "ui/server.py"])
