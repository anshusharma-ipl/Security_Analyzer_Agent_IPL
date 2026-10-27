import os


def archive_name(name):
    """Pretend to archive a folder by name (it only prints)."""
    return os.system(f"echo archiving {name}")
