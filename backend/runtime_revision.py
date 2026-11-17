"""Identify the backend source loaded by a running server."""
import hashlib
from pathlib import Path


def source_revision(directory=None):
    root = Path(directory) if directory else Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.glob("*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
