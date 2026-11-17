import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import database
from analysis_service import AnalysisUnavailableError, analyze_transcript, availability
from schemas import CrearReunion, EditarPendiente, ResolverPropuesta
from process_control import ProcessingCancelled

router = APIRouter(prefix="/api/reuniones", tags=["Reuniones y pendientes"])
logger = logging.getLogger("uvicorn.error")


def run_analysis(meeting_id):
    token = None
    try:
        meeting = database.get_meeting(meeting_id)
        token = meeting["analysis_token"]
        result = analyze_transcript(meeting, lambda value: database.analysis_progress(meeting_id, value, token),
                                    cancelled=lambda: database.analysis_cancelled(meeting_id, token))
        database.finish_analysis(meeting_id, result, token)
    except ProcessingCancelled:
        pass
    except AnalysisUnavailableError as error:
        database.fail_analysis(meeting_id, str(error), token)
    except Exception:
        logger.exception("No se pudo completar el análisis de una reunión.")
        database.fail_analysis(meeting_id, "No se pudo completar el análisis. La transcripción está guardada; puedes reintentarlo.", token)


@router.post("", status_code=201)
def create_meeting(data: CrearReunion):
    return database.create_meeting(data.model_dump())


@router.get("")
def list_meetings(q: str = Query(default="", max_length=120), offset: int = Query(default=0, ge=0),
                  limit: int = Query(default=20, ge=1, le=50)):
    return database.list_meetings(q.strip(), offset, limit)


@router.get("/{meeting_id}")
def get_meeting(meeting_id: str):
    return database.get_meeting(meeting_id)


@router.delete("/{meeting_id}")
def delete_meeting(meeting_id: str):
    return database.delete_meeting(meeting_id)


@router.post("/{meeting_id}/analizar", status_code=202)
def analyze_meeting(meeting_id: str, background_tasks: BackgroundTasks):
    meeting = database.get_meeting(meeting_id)
    if meeting["analysis_status"] in ("procesando", "listo"):
        return meeting
    if not availability()["disponible"]:
        message = "Falta preparar la IA local. Ejecuta Instalar-IA.cmd y después pulsa Reintentar análisis. Tu transcripción ya está guardada."
        database.fail_analysis(meeting_id, message)
        raise HTTPException(status_code=503, detail=message)
    if database.claim_analysis(meeting_id):
        background_tasks.add_task(run_analysis, meeting_id)
    return database.get_meeting(meeting_id)


@router.patch("/{meeting_id}/pendientes/{task_id}")
def update_task(meeting_id: str, task_id: str, data: EditarPendiente):
    return database.update_task(meeting_id, task_id, data.model_dump(exclude_none=True))


@router.post("/{meeting_id}/cancelar")
def cancel_analysis(meeting_id: str):
    return database.cancel_analysis(meeting_id)


@router.patch("/{meeting_id}/propuestas/{proposal_id}")
def resolve_proposal(meeting_id: str, proposal_id: str, data: ResolverPropuesta):
    return database.resolve_proposal(meeting_id, proposal_id, data.model_dump())
