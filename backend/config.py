"""Configuration for a single-user, local installation."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env_file = ROOT / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

DB_PATH = Path(os.environ.get("REUNION_NOTAS_DB", ROOT / "backend/data/reuniones.sqlite3"))
MODEL_PATH = Path(os.environ.get("TEXT_MODEL_PATH", ROOT / "backend/modelos/qwen2.5-1.5b-instruct-q4_k_m.gguf"))
ENGINE_DIR = ROOT / "backend/vendor/llama"


def engine_path():
    explicit = os.environ.get("LLAMA_CPP_EXECUTABLE")
    if explicit:
        return Path(explicit)
    for name in ("llama-completion.exe", "llama-cli.exe"):
        matches = list(ENGINE_DIR.rglob(name)) if ENGINE_DIR.exists() else []
        if matches:
            return matches[0]
    return ENGINE_DIR / "llama-completion.exe"
