import os


def read_inside(base, name):
    """The safe way: resolve the path and refuse anything outside the folder."""
    path = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([os.path.realpath(base), path]) != os.path.realpath(base):
        raise ValueError("outside the folder")
    with open(path) as handle:
        return handle.read()
