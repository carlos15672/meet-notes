"""Pruebas de las funciones de ruta y Whisper sin red ni respuestas simuladas.

El ejecutor de pruebas sustituye solo el despacho al hilo por ejecución directa.
La decodificación, Whisper, validaciones, excepciones y limpieza son reales.
El transporte HTTP se verifica aparte en el navegador.
"""
import io
import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException, UploadFile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import main


async def inline_worker(function, *args):
    return function(*args)


def finish(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coroutine.close()
    raise AssertionError("La prueba requiere una operacion asincrona no prevista.")


def upload(filename, data):
    stream = tempfile.SpooledTemporaryFile(max_size=1024 * 1024)
    stream.write(data)
    stream.seek(0)
    audio = UploadFile(filename=filename, file=stream, size=len(data))
    try:
        with patch.object(main, "run_in_threadpool", inline_worker):
            body = finish(main.transcribir(audio))
        main.ResultadoTranscripcion.model_validate(body)
        return 200, body
    except HTTPException as error:
        return error.status_code, {"detail": error.detail}
    finally:
        stream.close()


class TranscriptionTests(unittest.TestCase):
    def test_salud(self):
        self.assertEqual(main.comprobar_servidor()["estado"], "ok")

    def test_extension_invalida(self):
        self.assertEqual(upload("archivo.exe", b"contenido")[0], 415)

    def test_archivo_vacio(self):
        self.assertEqual(upload("audio.wav", b"")[0], 400)

    def test_audio_corrupto(self):
        self.assertEqual(upload("audio.wav", b"esto no es un audio")[0], 422)

    def test_limite_de_tamano(self):
        with patch.object(main, "MAX_AUDIO_BYTES", 4):
            self.assertEqual(upload("audio.wav", b"12345")[0], 413)

    def test_transcripcion_real_y_limpieza(self):
        fixture = ROOT / "samples" / "es_ganamos.wav"
        created = []
        real_directory = tempfile.TemporaryDirectory

        def directory(**kwargs):
            result = real_directory(**kwargs)
            created.append(Path(result.name))
            return result

        with patch.object(main, "TemporaryDirectory", directory):
            status, body = upload("es_ganamos.wav", fixture.read_bytes())
        self.assertEqual(status, 200, body)
        self.assertIn("ganamos", body["texto"].lower())
        self.assertIn("partido", body["texto"].lower())
        self.assertGreater(len(body["segmentos"]), 0)
        self.assertGreater(body["duracion_segundos"], 0)
        for segment in body["segmentos"]:
            self.assertLessEqual(segment["inicio"], segment["fin"])
        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))
        print("\nTRANSCRIPCION REAL:", json.dumps(body, ensure_ascii=True), flush=True)

    def test_silencio_sin_transcripcion_inventada(self):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(16000)
            audio.writeframes(b"\x00\x00" * 32000)
        status, body = upload("silencio.wav", buffer.getvalue())
        self.assertEqual(status, 422, body)
        self.assertNotIn("texto", body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
