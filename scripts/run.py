"""Start both local services, reusing healthy services already running."""
import os
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
from analysis_service import availability
from process_control import stop_owned_process
from runtime_revision import source_revision

# Local services must never be routed through the system's HTTP proxy.
LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
BACKEND_URL = "http://127.0.0.1:8000/api/estado"
FRONTEND_URL = "http://127.0.0.1:5173/"


def responds(url):
    try:
        with LOCAL_HTTP.open(url, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def ensure_current_backend():
    try:
        with LOCAL_HTTP.open(BACKEND_URL, timeout=2) as response:
            revision = json.load(response).get("revision")
    except (OSError, ValueError, AttributeError) as error:
        raise RuntimeError("No se pudo comprobar la versión del servidor. Vuelve a iniciar meet-notes.") from error
    if revision != source_revision():
        raise RuntimeError("El servidor abierto usa una versión anterior. Abre Reiniciar-meet-notes.cmd para cargar los cambios.")


def port_busy(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind(("127.0.0.1", port))
            return False
        except OSError as error:
            if error.errno in (48, 98, 10048) or getattr(error, "winerror", None) == 10048:
                return True
            raise RuntimeError(f"No se pudo comprobar el puerto {port}. No se iniciaron copias adicionales.") from error


def main():
    backend_ready, frontend_ready = responds(BACKEND_URL), responds(FRONTEND_URL)
    if backend_ready:
        ensure_current_backend()
    if backend_ready and frontend_ready:
        print("meet-notes ya está abierta. Usando los servicios existentes.", flush=True)
        webbrowser.open(FRONTEND_URL)
        return
    backend_busy = backend_ready or port_busy(8000)
    frontend_busy = frontend_ready or port_busy(5173)
    node = shutil.which("node")
    if not frontend_busy and (not node or not (ROOT / "node_modules/vite/bin/vite.js").is_file()):
        raise RuntimeError("Faltan Node.js o las dependencias del frontend. Consulta README.md.")
    if not backend_busy and not availability()["disponible"]:
        print("Preparando la IA local por primera vez. La descarga requiere internet y aproximadamente 1.2 GB.", flush=True)
        subprocess.run([sys.executable, "-u", str(ROOT / "scripts/setup_ai.py")], cwd=ROOT, check=True)
    children = []
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        if not backend_busy:
            children.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--app-dir", "backend",
                "--host", "127.0.0.1", "--port", "8000"], cwd=ROOT, creationflags=flags, start_new_session=os.name != "nt"))
        if not frontend_busy:
            children.append(subprocess.Popen([node, "node_modules/vite/bin/vite.js", "--host", "127.0.0.1",
                "--port", "5173", "--strictPort"], cwd=ROOT, creationflags=flags, start_new_session=os.name != "nt"))
        if backend_busy or frontend_busy:
            print("Hay servicios abiertos. Comprobando que estén listos, sin iniciar copias.", flush=True)
        deadline = time.monotonic() + 40
        while not (responds(BACKEND_URL) and responds(FRONTEND_URL)):
            if any(process.poll() is not None for process in children):
                raise RuntimeError("No se pudieron iniciar los servicios. Cierra las terminales anteriores de Vite y Python y vuelve a abrir Iniciar-meet-notes.cmd.")
            if time.monotonic() > deadline:
                raise RuntimeError("No se pudo conectar con los servicios de los puertos 8000 y 5173. Si la página tampoco abre, cierra las ventanas anteriores de meet-notes con Ctrl+C y vuelve a iniciar la aplicación. No se cerraron procesos ajenos.")
            time.sleep(0.5)
        ensure_current_backend()
        if not children:
            print("meet-notes ya está abierta. Usando los servicios existentes.", flush=True)
            webbrowser.open(FRONTEND_URL)
            return
        print("\nmeet-notes listo: http://127.0.0.1:5173/\nMantén esta ventana abierta. Ctrl+C para detener los servicios iniciados aquí.", flush=True)
        webbrowser.open("http://127.0.0.1:5173/")
        while all(process.poll() is None for process in children):
            time.sleep(1)
        if children:
            raise RuntimeError("Uno de los servicios terminó. Revisa los mensajes anteriores.")
    except KeyboardInterrupt:
        print("\nCerrando los servicios de esta sesión…", flush=True)
    finally:
        for process in children:
            if process.poll() is None:
                stop_owned_process(process, tree=True)
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"No se pudo iniciar meet-notes: {error}", file=sys.stderr)
        sys.exit(1)
