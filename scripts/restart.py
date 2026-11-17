"""Restart a Windows meet-notes instance only after verifying project ownership."""
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))
from config import DB_PATH
from scripts import run

# Collect only the port owner and its ancestors. Paths are checked below before
# stopping any process. An inaccessible/unknown process is never terminated.
PROCESS_QUERY = r"""
$ErrorActionPreference = 'Stop'
$meetNotesListeners = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
$meetNotesProcesses = @()
foreach ($meetNotesListener in $meetNotesListeners) {
  $meetNotesCurrent = [int]$meetNotesListener
  for ($meetNotesDepth = 0; $meetNotesDepth -lt 8 -and $meetNotesCurrent -gt 0; $meetNotesDepth++) {
    $meetNotesProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $meetNotesCurrent"
    if (-not $meetNotesProcess) { break }
    $meetNotesProcesses += [pscustomobject]@{
      pid = [int]$meetNotesProcess.ProcessId
      parent = [int]$meetNotesProcess.ParentProcessId
      executable = [string]$meetNotesProcess.ExecutablePath
      command = [string]$meetNotesProcess.CommandLine
    }
    $meetNotesCurrent = [int]$meetNotesProcess.ParentProcessId
  }
}
ConvertTo-Json -InputObject @($meetNotesProcesses) -Compress
"""


def project_process(process):
    command = process.get("command", "").replace("\\", "/").lower()
    executable = process.get("executable", "").replace("\\", "/").lower()
    root = str(ROOT).replace("\\", "/").lower()
    python_path = root + "/.venv-backend/scripts/python.exe"
    own_path = executable == python_path or python_path in command
    is_server = "-m uvicorn " in command or "scripts/run.py" in command
    return own_path and is_server


def restart_targets(processes):
    records = {int(item["pid"]): item for item in processes}
    ancestors = {int(item["parent"]) for item in processes}
    # Every listener must be identifiable, even if its ancestors are unrelated.
    listeners = [item for item in processes if int(item["pid"]) not in ancestors]
    if not listeners or any(not project_process(item) for item in listeners):
        raise RuntimeError("No se pudo identificar el servidor como parte de este proyecto. Detén su terminal con Ctrl+C y abre Iniciar-meet-notes.cmd.")
    targets = set()
    for item in listeners:
        seen = set()
        while int(item["parent"]) in records and int(item["pid"]) not in seen:
            seen.add(int(item["pid"]))
            parent = records[int(item["parent"])]
            if not project_process(parent):
                break
            item = parent
        targets.add(int(item["pid"]))
    return sorted(targets)


def check_idle():
    if not DB_PATH.is_file():
        return
    with closing(sqlite3.connect(DB_PATH.as_uri() + "?mode=ro", uri=True, timeout=2)) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, column in (("jobs", "status"), ("meetings", "analysis_status")):
            if table in tables and connection.execute(f"SELECT 1 FROM {table} WHERE {column}='procesando' LIMIT 1").fetchone():
                raise RuntimeError("Hay una reunión en procesamiento. Espera a que termine o cancélala desde la aplicación antes de reiniciar.")


def main():
    if os.name != "nt":
        raise RuntimeError("Este acceso de reinicio está preparado para Windows.")
    if run.responds(run.BACKEND_URL):
        check_idle()
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_QUERY],
                                capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError("Windows no permitió identificar la instancia abierta. Detén la terminal anterior de meet-notes con Ctrl+C y abre Iniciar-meet-notes.cmd.")
        targets = restart_targets(json.loads(result.stdout))
        check_idle()
        print("Reiniciando el servidor de este proyecto...", flush=True)
        for pid in targets:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], check=True,
                           capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
        # Give the previous launcher time to close its child services.
        time.sleep(2)
    run.main()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"No se pudo reiniciar meet-notes: {error}", file=sys.stderr)
        sys.exit(1)
