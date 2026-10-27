"""One-step launcher: installs jsonschema if missing, starts the console and opens the browser. Double-click start.bat (Windows) or run start.sh."""
import importlib.util, subprocess, sys, threading, time, webbrowser, urllib.request

PORT = 8765
if importlib.util.find_spec("jsonschema") is None:
    print("Installing jsonschema (one time)...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "jsonschema>=4"])

child = subprocess.Popen([sys.executable, "ui/server.py"])


def open_when_ready():
    """Open the page only when the console that answers is the one started here. If the server refused to start (for example
    the port is taken by an older console), do not open that other console's page: it may be running old code."""
    for _ in range(60):
        if child.poll() is not None:
            return
        try:
            text = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/healthz", timeout=1).read().decode("utf-8", "replace")
            if f"pid: {child.pid}" in text:
                webbrowser.open(f"http://127.0.0.1:{PORT}/")
                return
        except Exception:
            pass
        time.sleep(0.5)


threading.Thread(target=open_when_ready, daemon=True).start()
print(f"Console at http://127.0.0.1:{PORT}  (close this window to stop it)")
try:
    code = child.wait()
except KeyboardInterrupt:
    code = child.wait()
if code:
    print(f"The console stopped with exit code {code}. See the message above; if the port is in use, close the other console first.")
sys.exit(code)
