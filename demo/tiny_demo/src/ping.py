import subprocess


def check_host(host):
    result = subprocess.run(f"ping -c 1 {host}", shell=True, capture_output=True, text=True)
    return result.returncode == 0
