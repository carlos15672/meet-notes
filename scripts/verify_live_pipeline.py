"""Exercise live-session finalization with the real local Whisper and Qwen models."""
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
from faster_whisper.audio import decode_audio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import database
import live_sessions


def main():
    original_db, original_root = database.DB_PATH, live_sessions.WORK_ROOT
    with tempfile.TemporaryDirectory(prefix="meet-live-", dir=ROOT) as temporary:
        try:
            directory = Path(temporary)
            database.DB_PATH = directory / "test.sqlite3"
            live_sessions.WORK_ROOT = directory / "audio"
            database.initialize()
            session_id = str(uuid4())
            audio_dir = live_sessions.workspace(session_id)
            audio_dir.mkdir(parents=True)
            samples = decode_audio(str(ROOT / "samples/reunion-controlada.wav"), sampling_rate=16000)
            (np.clip(samples * 32767, -32768, 32767).astype("<i2")).tofile(audio_dir / "sistema.pcm")
            np.zeros(len(samples), dtype="<i2").tofile(audio_dir / "microfono.pcm")
            with database.connection() as conn:
                conn.execute("""INSERT INTO live_sessions (id,title,user_name,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?)""", (session_id, "Verificación en vivo", "Carlos", "interrumpida",
                    database.now(), database.now()))
            live_sessions.manager.finish(session_id)
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                state = live_sessions.get_session(session_id)
                if state["status"] in ("lista", "error"):
                    break
                time.sleep(1)
            else:
                raise RuntimeError("La sesión no terminó dentro de cuatro minutos.")
            if state["status"] != "lista":
                raise RuntimeError(state["error"])
            meeting = database.get_meeting(state["meeting_id"])
            if meeting["analysis_status"] != "listo":
                raise RuntimeError(meeting["analysis_error"])
            if audio_dir.exists():
                raise RuntimeError("El audio temporal no se eliminó.")
            print("CAPTURA EN VIVO LISTA:", len(meeting["segmentos"]), "segmentos;",
                  len(meeting["pendientes"]), "pendientes; análisis", meeting["analysis_status"])
        finally:
            database.DB_PATH, live_sessions.WORK_ROOT = original_db, original_root


if __name__ == "__main__":
    main()
