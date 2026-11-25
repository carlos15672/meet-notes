import logging
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import database
from analysis_service import availability
from audio_formats import ALLOWED_EXTENSIONS, FORMAT_ERROR, MAX_AUDIO_BYTES
from meetings import router as meetings_router
from jobs import router as jobs_router
from live_sessions import router as live_router, manager as live_manager
from jobs_service import recover_workspaces
from schemas import ResultadoTranscripcion
from runtime_revision import source_revision

from whisper_service import (
    InvalidAudioError,
    ModelUnavailableError,
    TranscriptionBusyError,
    transcribir_audio,
)

logger = logging.getLogger("uvicorn.error")
RUNNING_REVISION = source_revision()


@asynccontextmanager
async def lifespan(app):
    database.initialize()
    database.recover_interrupted()
    database.recover_jobs()
    database.recover_live_sessions()
    recover_workspaces()
    yield
    live_manager.shutdown()


app = FastAPI(
    title="meet-notes",
    description="Procesamiento de grabaciones de reuniones.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

app.include_router(meetings_router)
app.include_router(jobs_router)
app.include_router(live_router)


@app.exception_handler(database.NotFoundError)
async def not_found(request, error):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(database.ConflictError)
async def conflict(request, error):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(sqlite3.Error)
async def database_error(request, error):
    logger.exception("No se pudo acceder a SQLite.")
    return JSONResponse(status_code=503, content={"detail": "No se pudo acceder al guardado. Comprueba el espacio disponible y vuelve a intentarlo."})


@app.get("/api/estado")
def estado():
    return {"estado": "ok", "ia": availability(), "persistencia": "sqlite", "revision": RUNNING_REVISION,
            "revision_transcripciones": True}


@app.get("/")
def inicio():
    return {
        "mensaje": "Backend de meet-notes activo",
        "documentacion": "/docs",
    }


@app.get("/api/salud")
def comprobar_servidor():
    return {
        "estado": "ok",
        "servicio": "meet-notes",
    }


@app.post(
    "/api/transcribir",
    response_model=ResultadoTranscripcion,
    summary="Transcribir una grabacion en espanol",
)
async def transcribir(audio: UploadFile = File(...)):
    try:
        extension = Path(audio.filename or "").suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=415,
                detail=FORMAT_ERROR,
            )

        with TemporaryDirectory(prefix="reunion-notas-") as directory:
            path = Path(directory) / ("grabacion" + extension)
            total = 0

            with path.open("wb") as destination:
                while chunk := await audio.read(1024 * 1024):
                    total += len(chunk)

                    if total > MAX_AUDIO_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail="El archivo supera el limite de 100 MB.",
                        )

                    destination.write(chunk)

            if total == 0:
                raise HTTPException(
                    status_code=400,
                    detail="El archivo esta vacio.",
                )

            try:
                # Ejecuta el trabajo fuera del bucle de peticiones.
                return await run_in_threadpool(transcribir_audio, path)

            except InvalidAudioError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=str(exc),
                ) from exc

            except TranscriptionBusyError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=str(exc),
                ) from exc

            except ModelUnavailableError as exc:
                logger.exception("Fallo al cargar Whisper.")
                raise HTTPException(
                    status_code=503,
                    detail=str(exc),
                ) from exc

            except Exception as exc:
                logger.exception("Fallo al transcribir el audio.")
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "No se pudo completar la transcripcion. "
                        "Revisa la terminal del backend."
                    ),
                ) from exc

    finally:
        await audio.close()
