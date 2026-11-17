import logging
import os
from pathlib import Path
from threading import Lock

import av
from faster_whisper import WhisperModel
from faster_whisper.audio import decode_audio

logger = logging.getLogger("uvicorn.error")

_model = None
_model_label = None
_processing_lock = Lock()
MODEL_NAME = "small"
MAX_DURATION_SECONDS = 45 * 60


def seleccionar_modelo():
    """Reutiliza los pesos del traductor existente sin cargar su traduccion.

    El flujo a 16 kHz, beam_size=5, VAD y sin contexto previo se adapta de
    Traductor-Final-main/Traductor-Final-main/traductor/transcripcion.py.
    WHISPER_MODEL_PATH permite elegir otros pesos locales de CTranslate2.
    """
    explicit = os.environ.get("WHISPER_MODEL_PATH")
    if explicit:
        path = Path(explicit)
        if not (path / "model.bin").is_file():
            raise ModelUnavailableError("No se encontro el modelo local configurado.")
        return str(path), path.name

    model_name = os.environ.get("WHISPER_MODEL")
    if model_name:
        return model_name, model_name

    cache = (Path.home() / ".cache" / "huggingface" / "hub" /
             "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo")
    ref = cache / "refs" / "main"
    if ref.is_file():
        revision = ref.read_text(encoding="utf-8").strip()
        candidate = (cache / "snapshots" / revision).resolve()
        snapshots = (cache / "snapshots").resolve()
        required = ("model.bin", "config.json", "tokenizer.json")
        if candidate.parent == snapshots and all((candidate / name).is_file() for name in required):
            return str(candidate), "large-v3-turbo"
    return MODEL_NAME, MODEL_NAME


class InvalidAudioError(ValueError):
    pass


class ModelUnavailableError(RuntimeError):
    pass


class TranscriptionBusyError(RuntimeError):
    pass


def transcribir_audio(path: Path) -> dict:
    global _model, _model_label

    if not _processing_lock.acquire(blocking=False):
        raise TranscriptionBusyError(
            "Ya se esta procesando un audio. Espera a que termine."
        )

    try:
        try:
            with av.open(str(path), mode="r", metadata_errors="ignore") as container:
                if not container.streams.audio:
                    raise InvalidAudioError(
                        "El archivo no contiene una pista de audio. Elige una grabación con sonido."
                    )
            samples = decode_audio(str(path), sampling_rate=16000)
        except InvalidAudioError:
            raise
        except Exception as exc:
            raise InvalidAudioError(
                "No se pudo leer el audio. Prueba otra grabacion."
            ) from exc

        duration = len(samples) / 16000

        if duration <= 0:
            raise InvalidAudioError("El archivo no contiene audio.")

        if duration > MAX_DURATION_SECONDS:
            raise InvalidAudioError(
                "El audio supera el limite de 45 minutos."
            )

        if _model is None:
            model_source, model_label = seleccionar_modelo()
            logger.info(
                "Preparando Whisper %s en CPU. Se reutilizan pesos locales cuando existen.",
                model_label,
            )
            try:
                _model = WhisperModel(
                    model_source,
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=4,
                    download_root=str(
                        Path(__file__).resolve().parent / "modelos"
                    ),
                )
                _model_label = model_label
            except Exception as exc:
                raise ModelUnavailableError(
                    "No se pudo cargar Whisper. Revisa la terminal del backend."
                ) from exc

        logger.info("Transcribiendo audio en CPU.")

        generated_segments, info = _model.transcribe(
            samples,
            language="es",
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
        )

        segments = [
            {
                "inicio": round(segment.start, 2),
                "fin": round(segment.end, 2),
                "texto": segment.text.strip(),
            }
            for segment in generated_segments
            if segment.text.strip()
        ]

        text = " ".join(segment["texto"] for segment in segments)

        if not text:
            raise InvalidAudioError(
                "No se reconocio voz. Prueba un audio con habla clara."
            )

        logger.info("Transcripcion completada.")

        return {
            "texto": text,
            "idioma": info.language,
            "duracion_segundos": round(duration, 2),
            "segmentos": segments,
            "modelo": _model_label,
        }

    finally:
        _processing_lock.release()
