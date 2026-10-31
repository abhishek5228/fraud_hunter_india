"""Snapshot the feature store so a restart does not forget what it learned (atomic write; plain pickle of our own file)."""
import os
import pickle
import tempfile


def save(store, path):
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        pickle.dump(store, f, protocol=pickle.HIGHEST_PROTOCOL)
    os.replace(tmp, path)


def load(path, newer_than=0.0):
    """Return the saved store, or None if there is none, it is older than the trained artifacts, or it cannot be read."""
    try:
        if os.path.getmtime(path) <= newer_than:
            return None
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None
