"""Cancellation for subprocesses owned by this application."""
import os
import signal
import subprocess
import time


class ProcessingCancelled(RuntimeError):
    pass


def check_cancelled(check=None):
    if check and check():
        raise ProcessingCancelled('Procesamiento cancelado.')


def stop_owned_process(process, tree=False):
    if process.poll() is not None:
        return
    if tree and os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                       creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
    elif tree and os.name != 'nt':
        os.killpg(process.pid, signal.SIGTERM)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_cancellable(args, cancelled=None, timeout=600, **kwargs):
    check_cancelled(cancelled)
    with subprocess.Popen(args, **kwargs) as process:
        deadline = time.monotonic() + timeout
        try:
            while True:
                check_cancelled(cancelled)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(args, timeout)
                try:
                    stdout, stderr = process.communicate(timeout=min(.25, remaining))
                    return subprocess.CompletedProcess(args, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            stop_owned_process(process)
            process.communicate()
            raise
