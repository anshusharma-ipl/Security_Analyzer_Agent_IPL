import subprocess


def check_host(host):
    result = subprocess.run(f"echo checking {host}", shell=True, capture_output=True, text=True)
    return result.stdout.strip()
