"""One owned worker process per audio job; uploaded files are temporary."""
import atexit
import os
import shutil
import subprocess
import sys
import threading
import time
from uuid import UUID
from pathlib import Path

import database
from config import ROOT
from process_control import stop_owned_process

WORK_ROOT = ROOT / 'backend/data/trabajos-temporales'
_workers = {}
_lock = threading.Lock()


def clean_workspace(job_id):
    target = (WORK_ROOT / job_id).resolve()
    if target.parent != WORK_ROOT.resolve() or target.name != job_id:
        raise ValueError('Ruta temporal inválida.')
    if target.is_dir():
        shutil.rmtree(target)


def start_worker(job_id):
    with _lock:
        if job_id in _workers or database.get_job(job_id)['status'] != 'procesando':
            return
        env = {**os.environ, 'REUNION_NOTAS_DB': str(database.DB_PATH.resolve())}
        process = subprocess.Popen([sys.executable, str(ROOT / 'backend/job_worker.py'), job_id],
            cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            start_new_session=os.name != 'nt')
        _workers[job_id] = process
    def monitor():
        code = process.wait()
        try:
            job = database.get_job(job_id)
            if job['status'] == 'procesando':
                database.update_job(job_id, 'error', status='error', error='El procesamiento se interrumpió. Puedes volver a intentarlo.')
        finally:
            try:
                clean_workspace(job_id)
            finally:
                with _lock:
                    if _workers.get(job_id) is process:
                        del _workers[job_id]
    threading.Thread(target=monitor, daemon=True).start()


def cancel_worker(job_id):
    database.cancel_job(job_id)
    with _lock:
        process = _workers.get(job_id)
    if process:
        stop_owned_process(process, tree=True)
    return public_job(database.get_job(job_id))


def public_job(job):
    return {k: job[k] for k in ('id','status','stage','error','meeting_id','created_at','updated_at')}


@atexit.register
def shutdown():
    with _lock:
        processes = list(_workers.values())
    for process in processes:
        try:
            stop_owned_process(process, tree=True)
        except OSError:
            pass


def recover_workspaces():
    with database.connection() as conn:
        ids = [row[0] for row in conn.execute("SELECT id FROM jobs WHERE status!='procesando'")]
    pending = []
    for job_id in ids:
        try:
            if str(UUID(job_id)) != job_id:
                continue
            clean_workspace(job_id)
        except (OSError, ValueError):
            pending.append(job_id)
    if pending:
        def retry():
            for _ in range(30):
                time.sleep(1)
                for job_id in list(pending):
                    try:
                        clean_workspace(job_id)
                        pending.remove(job_id)
                    except (OSError, ValueError):
                        pass
                if not pending:
                    return
        threading.Thread(target=retry, daemon=True).start()
