"""Local live capture sessions and their HTTP controls."""
import json
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import database
from config import ROOT
from live_audio import AudioCapture, CaptureError, SAMPLE_RATE, devices, sample_count
from live_transcription import LiveTranscriber, final_transcription
from schemas import ResultadoTranscripcion

logger = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/api/en-vivo", tags=["Captura en vivo"])
WORK_ROOT = ROOT / "backend/data/capturas-en-vivo"


class StartSession(BaseModel):
    userName: str = Field(min_length=1, max_length=80)
    title: str = Field(default="Reunión en vivo", max_length=120)
    system_device_id: int | None = Field(default=None, ge=0)
    microphone_device_id: int | None = Field(default=None, ge=0)


def workspace(session_id):
    try:
        if str(UUID(session_id)) != session_id:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(422, "Identificador de sesión inválido.") from exc
    return WORK_ROOT / session_id


def clean_workspace(session_id):
    target = workspace(session_id).resolve()
    if target.parent != WORK_ROOT.resolve():
        raise ValueError("Ruta de captura inválida.")
    if target.exists():
        shutil.rmtree(target)


def get_session(session_id):
    path = workspace(session_id)
    with database.connection() as conn:
        row = conn.execute("SELECT * FROM live_sessions WHERE id=?", (session_id,)).fetchone()
        if not row:
            raise database.NotFoundError("No se encontró la sesión en vivo.")
        marks = conn.execute("SELECT id,second,created_at FROM live_marks WHERE session_id=? ORDER BY second", (session_id,)).fetchall()
    result = dict(row)
    if result["status"] == "capturando":
        result["duration"] = max(result["duration"],
            max(sample_count(path, "sistema"), sample_count(path, "microfono")) / SAMPLE_RATE)
    result["segmentos"] = json.loads(result.pop("segments"))
    result["marcas"] = [dict(mark) for mark in marks]
    return result


def update_session(session_id, **fields):
    fields["updated_at"] = database.now()
    with database.connection() as conn:
        conn.execute("UPDATE live_sessions SET " + ",".join(key + "=?" for key in fields) + " WHERE id=?",
                     (*fields.values(), session_id))


class SessionManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.active = None

    def start(self, data):
        with self.lock:
            if self.active:
                raise database.ConflictError("Ya hay una captura en vivo. Finalízala antes de iniciar otra.")
            if not data.userName.strip():
                raise HTTPException(422, "Escribe el nombre con el que te mencionan en la reunión.")
            session_id = str(uuid4())
            with database.connection() as conn:
                conn.execute("""INSERT INTO live_sessions (id,title,user_name,status,created_at,updated_at)
                    VALUES (?,?,?,?,?,?)""", (session_id, data.title.strip() or "Reunión en vivo",
                    data.userName.strip(), "capturando", database.now(), database.now()))
            def capture_error(error):
                update_session(session_id, status="error", error=str(error))
            capture = AudioCapture(workspace(session_id), data.system_device_id,
                                   data.microphone_device_id, capture_error)
            try:
                capture.start()
                transcriber = LiveTranscriber(workspace(session_id),
                    lambda segments: update_session(session_id, segments=json.dumps(segments, ensure_ascii=False)),
                    lambda error: update_session(session_id, error="Vista previa: " + error))
                transcriber.start()
            except Exception as exc:
                capture.stop()
                update_session(session_id, status="error", error=str(exc))
                raise HTTPException(503, f"No se pudo iniciar la captura: {exc}") from exc
            self.active = (session_id, capture, transcriber)
            return get_session(session_id)

    def pause(self, session_id):
        with self.lock:
            state = get_session(session_id)
            if state["status"] == "pausada":
                return state
            if state["status"] != "capturando" or not self.active or self.active[0] != session_id:
                raise database.ConflictError("Esta sesión no está capturando audio.")
            duration = self.active[1].stop()
            update_session(session_id, status="pausada", duration=duration)
            return get_session(session_id)

    def resume(self, session_id):
        with self.lock:
            state = get_session(session_id)
            if state["status"] == "capturando":
                return state
            if state["status"] != "pausada" or not self.active or self.active[0] != session_id:
                raise database.ConflictError("Esta sesión no está pausada.")
            try:
                self.active[1].start()
            except Exception as exc:
                update_session(session_id, status="error", error=str(exc))
                raise HTTPException(503, f"No se pudo reanudar la captura: {exc}") from exc
            update_session(session_id, status="capturando")
            return get_session(session_id)

    def mark(self, session_id):
        with self.lock:
            state = get_session(session_id)
            if state["status"] not in ("capturando", "pausada"):
                raise database.ConflictError("La sesión ya no admite marcas.")
            with database.connection() as conn:
                conn.execute("INSERT INTO live_marks (id,session_id,second,created_at) VALUES (?,?,?,?)",
                    (str(uuid4()), session_id, round(state["duration"], 2), database.now()))
            return get_session(session_id)

    def finish(self, session_id):
        with self.lock:
            state = get_session(session_id)
            if state["status"] in ("finalizando", "analizando", "lista"):
                return state
            if state["status"] not in ("capturando", "pausada", "interrumpida", "error"):
                raise database.ConflictError("No se puede finalizar esta sesión.")
            active = self.active if self.active and self.active[0] == session_id else None
            update_session(session_id, status="finalizando", error="")
            threading.Thread(target=self._finalize, args=(session_id, active), daemon=True).start()
            return get_session(session_id)

    def _finalize(self, session_id, active):
        try:
            if active:
                duration = active[1].stop()
                update_session(session_id, duration=duration)
                active[2].stop()
            state = get_session(session_id)
            if state["meeting_id"]:
                # A restart during Qwen inference can recover from the saved text.
                meeting = database.get_meeting(state["meeting_id"])
            else:
                transcription = ResultadoTranscripcion.model_validate(
                    final_transcription(workspace(session_id))).model_dump()
                meeting = database.create_meeting({"request_id": session_id, "title": state["title"],
                    "userName": state["user_name"], "fileName": "Captura en vivo",
                    "transcription": transcription})
                update_session(session_id, meeting_id=meeting["id"],
                    duration=transcription["duracion_segundos"],
                    segments=json.dumps(transcription["segmentos"], ensure_ascii=False))
                try:
                    clean_workspace(session_id)
                except OSError:
                    logger.warning("No se pudo borrar el audio temporal de %s.", session_id)
            update_session(session_id, status="analizando", meeting_id=meeting["id"],
                error="")
            with self.lock:
                if self.active and self.active[0] == session_id:
                    self.active = None
            if database.claim_analysis(meeting["id"]):
                from meetings import run_analysis
                run_analysis(meeting["id"])
            updated = database.get_meeting(meeting["id"])
            update_session(session_id, status="lista", error=updated["analysis_error"])
        except Exception as exc:
            logger.exception("No se pudo finalizar una captura en vivo.")
            update_session(session_id, status="error", error=str(exc))
        finally:
            with self.lock:
                if self.active and self.active[0] == session_id:
                    self.active = None

    def shutdown(self):
        with self.lock:
            if self.active:
                session_id, capture, transcriber = self.active
                update_session(session_id, status="interrumpida",
                    error="La aplicación se cerró. Puedes finalizar el audio guardado.")
                capture.stop()
                transcriber.stop()
                self.active = None


manager = SessionManager()
_window_lock = threading.Lock()
_window_process = None


def open_floating_window():
    global _window_process
    if os.name != "nt":
        raise HTTPException(503, "La ventana flotante está preparada para Windows.")
    if importlib.util.find_spec("PySide6") is None:
        raise HTTPException(503, "Falta PySide6. Instala las dependencias de backend/requirements.txt.")
    with _window_lock:
        if _window_process is not None and _window_process.poll() is None:
            return {"abierta": True, "ya_estaba_abierta": True}
        try:
            _window_process = subprocess.Popen(
                [sys.executable, str(ROOT / "scripts/floating_window.py")],
                cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        except OSError as exc:
            raise HTTPException(503, "No se pudo abrir la ventana flotante.") from exc
        return {"abierta": True, "ya_estaba_abierta": False}


@router.get("/dispositivos")
def list_devices():
    try:
        return devices()
    except (CaptureError, OSError) as exc:
        raise HTTPException(503, str(exc)) from exc


@router.post("/ventana")
def launch_floating_window():
    return open_floating_window()


@router.post("/sesiones", status_code=201)
def start_session(data: StartSession):
    return manager.start(data)


@router.get("/sesiones")
def list_sessions():
    with database.connection() as conn:
        ids = [row[0] for row in conn.execute(
            "SELECT id FROM live_sessions ORDER BY created_at DESC LIMIT 50")]
    return {"items": [get_session(session_id) for session_id in ids]}


@router.get("/sesiones/{session_id}")
def read_session(session_id: str):
    return get_session(session_id)


@router.post("/sesiones/{session_id}/pausar")
def pause_session(session_id: str):
    return manager.pause(session_id)


@router.post("/sesiones/{session_id}/reanudar")
def resume_session(session_id: str):
    return manager.resume(session_id)


@router.post("/sesiones/{session_id}/marcar")
def mark_session(session_id: str):
    return manager.mark(session_id)


@router.post("/sesiones/{session_id}/finalizar", status_code=202)
def finish_session(session_id: str):
    return manager.finish(session_id)
