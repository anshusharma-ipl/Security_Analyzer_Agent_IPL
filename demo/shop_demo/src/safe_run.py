import subprocess
import sys


def run_python(arg):
    """The safe way: the command is a list, so there is no shell to inject into."""
    return subprocess.run([sys.executable, "-c", "pass", arg], capture_output=True).returncode
