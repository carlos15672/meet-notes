"""Download official portable llama.cpp and official Qwen GGUF weights."""
import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RELEASE = "b12359"
ASSET = f"llama-{RELEASE}-bin-win-cpu-x64.zip"
MODEL_URL = "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_HASH = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL = ROOT / "backend/modelos/qwen2.5-1.5b-instruct-q4_k_m.gguf"
ENGINE = ROOT / "backend/vendor/llama"


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(4 * 1024 * 1024):
            value.update(block)
    return value.hexdigest()


def download(url, destination, expected_hash=None):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and (not expected_hash or digest(destination) == expected_hash):
        print(f"Disponible: {destination.name}", flush=True)
        return
    partial = destination.with_suffix(destination.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": "Reunion-Notas-Local/1.0"})
    print(f"Descargando {destination.name}...", flush=True)
    with urllib.request.urlopen(request, timeout=90) as response, partial.open("wb") as output:
        total = int(response.headers.get("Content-Length", 0))
        received, last = 0, -1
        while block := response.read(4 * 1024 * 1024):
            output.write(block)
            received += len(block)
            percent = int(received * 100 / total) if total else received // (50 * 1024 * 1024)
            if percent != last:
                print(f"  {received // (1024 * 1024)} MB" + (f" / {total // (1024 * 1024)} MB" if total else ""), flush=True)
                last = percent
    if expected_hash and digest(partial) != expected_hash:
        raise RuntimeError("La descarga no coincide con la huella SHA256 oficial. Vuelve a intentarlo.")
    partial.replace(destination)


def main():
    engine_ready = any(ENGINE.rglob("llama-completion.exe")) or any(ENGINE.rglob("llama-cli.exe"))
    if not engine_ready:
        archive = ROOT / "backend/vendor" / ASSET
        api_url = f"https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{RELEASE}"
        request = urllib.request.Request(api_url, headers={"User-Agent": "Reunion-Notas-Local/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            release = json.load(response)
        asset = next(item for item in release["assets"] if item["name"] == ASSET)
        official_hash = (asset.get("digest") or "").removeprefix("sha256:") or None
        download(asset["browser_download_url"], archive, official_hash)
        ENGINE.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as zipped:
            root = ENGINE.resolve()
            for entry in zipped.infolist():
                target = (root / entry.filename).resolve()
                if not target.is_relative_to(root):
                    raise RuntimeError("El archivo del motor contiene una ruta inválida.")
            zipped.extractall(ENGINE)
    download(MODEL_URL, MODEL, MODEL_HASH)
    sys.path.insert(0, str(ROOT / "backend"))
    from analysis_service import analyze_transcript
    print("Comprobando una inferencia real...", flush=True)
    sample = "Revisamos el avance del proyecto. Carlos preparará la presentación para el viernes. Ana revisará el diseño. Acordamos volver a reunirnos el lunes."
    result = analyze_transcript({"texto": sample, "userName": "Carlos", "segmentos": []})
    if not result["resumen"]["temas"] or not result["pendientes"]:
        raise RuntimeError("El motor inició, pero no superó la prueba de resumen y asignación. Revisa la salida antes de usarlo.")
    print("IA LOCAL LISTA: resumen y pendiente de Carlos comprobados.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"No se pudo preparar la IA local: {error}", file=sys.stderr)
        sys.exit(1)
