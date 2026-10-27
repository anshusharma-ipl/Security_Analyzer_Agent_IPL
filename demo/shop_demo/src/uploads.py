import os


def save_upload(base, filename, data):
    target = os.path.join(base, filename)
    with open(target, "wb") as handle:
        handle.write(data)
    return target
