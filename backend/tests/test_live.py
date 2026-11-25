import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
import live_sessions
from live_audio import SAMPLE_RATE, mixed_samples, read_track
from live_sessions import SessionManager, StartSession
from live_transcription import LiveTranscriber
import test_workflow as workflow

TRANSCRIPTION = workflow.TRANSCRIPTION


class FakeCapture:
    def __init__(self, directory, *_args):
        self.directory = Path(directory)

    def start(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        for track in ("sistema", "microfono"):
            with (self.directory / (track + ".pcm")).open("ab") as output:
                output.write(b"\0\0" * SAMPLE_RATE)

    def stop(self):
        return (self.directory / "sistema.pcm").stat().st_size / 2 / SAMPLE_RATE


class FakeTranscriber:
    def __init__(self, *_args):
        pass

    def start(self):
        pass

    def stop(self):
        pass


class LiveSessionTests(unittest.TestCase):
    request = workflow.WorkflowTests.request
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = database.DB_PATH
        self.old_root = live_sessions.WORK_ROOT
        database.DB_PATH = Path(self.temp.name) / "db.sqlite3"
        live_sessions.WORK_ROOT = Path(self.temp.name) / "audio"
        database.initialize()
        self.manager = SessionManager()

    def tearDown(self):
        database.DB_PATH = self.old_db
        live_sessions.WORK_ROOT = self.old_root
        self.temp.cleanup()

    def wait_for(self, session_id, status):
        for _ in range(100):
            state = live_sessions.get_session(session_id)
            if state["status"] == status:
                return state
            time.sleep(.01)
        self.fail(f"La sesión no llegó a {status}: {state}")

    def test_capture_pause_resume_mark_and_finish_reuses_meeting_storage(self):
        with patch("live_sessions.AudioCapture", FakeCapture), patch("live_sessions.LiveTranscriber", FakeTranscriber), \
             patch("live_sessions.final_transcription", return_value=TRANSCRIPTION), \
             patch("database.claim_analysis", return_value=False):
            session = self.manager.start(StartSession(userName="Juan", title="Diseño"))
            sid = session["id"]
            self.assertEqual(session["status"], "capturando")
            self.assertEqual(self.manager.mark(sid)["marcas"][0]["second"], 1)
            self.assertEqual(self.manager.pause(sid)["status"], "pausada")
            self.assertEqual(self.manager.resume(sid)["duration"], 2)
            self.assertEqual(self.manager.finish(sid)["status"], "finalizando")
            ready = self.wait_for(sid, "lista")
        meeting = database.get_meeting(ready["meeting_id"])
        self.assertEqual(meeting["userName"], "Juan")
        self.assertEqual(meeting["texto"], TRANSCRIPTION["texto"])
        self.assertEqual(ready["marcas"][0]["second"], 1)
        self.assertFalse(live_sessions.workspace(sid).exists())

    def test_interrupted_session_keeps_audio_and_can_finalize(self):
        with patch("live_sessions.AudioCapture", FakeCapture), patch("live_sessions.LiveTranscriber", FakeTranscriber), \
             patch("live_sessions.final_transcription", return_value=TRANSCRIPTION), \
             patch("database.claim_analysis", return_value=False):
            sid = self.manager.start(StartSession(userName="Juan"))["id"]
            self.manager.shutdown()
            database.recover_live_sessions()
            self.assertEqual(live_sessions.get_session(sid)["status"], "interrumpida")
            self.assertTrue((live_sessions.workspace(sid) / "microfono.pcm").exists())
            self.manager.finish(sid)
            self.wait_for(sid, "lista")

    def test_restart_during_analysis_reuses_saved_text_without_audio(self):
        sid = str(uuid4())
        with database.connection() as conn:
            conn.execute("""INSERT INTO live_sessions (id,title,user_name,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?)""", (sid, "Diseño", "Juan", "analizando", database.now(), database.now()))
        meeting = database.create_meeting({"request_id": sid, "title": "Diseño", "userName": "Juan",
            "fileName": "Captura en vivo", "transcription": TRANSCRIPTION})
        live_sessions.update_session(sid, meeting_id=meeting["id"])
        database.recover_live_sessions()
        with patch("live_sessions.final_transcription", side_effect=AssertionError("No debe leer audio")), \
             patch("database.claim_analysis", return_value=False):
            self.manager.finish(sid)
            result = self.wait_for(sid, "lista")
        self.assertEqual(result["meeting_id"], meeting["id"])

    def test_mixed_audio_keeps_both_tracks_and_pads_shorter_input(self):
        directory = Path(self.temp.name)
        np.array([1000, 2000], dtype="<i2").tofile(directory / "sistema.pcm")
        np.array([3000], dtype="<i2").tofile(directory / "microfono.pcm")
        result = mixed_samples(directory, 0, 2)
        self.assertAlmostEqual(result[0], 4000 / 32768)
        self.assertAlmostEqual(result[1], 2000 / 32768)
        self.assertEqual(len(read_track(directory, "microfono", 0, 2)), 2)

    def test_http_routes_expose_live_session_controls(self):
        with patch("live_sessions.manager", self.manager), patch("live_sessions.AudioCapture", FakeCapture), \
             patch("live_sessions.LiveTranscriber", FakeTranscriber), \
             patch("live_sessions.final_transcription", return_value=TRANSCRIPTION), \
             patch("database.claim_analysis", return_value=False):
            status, session = self.request("POST", "/api/en-vivo/sesiones", {"userName": "Juan"})
            self.assertEqual(status, 201)
            url = "/api/en-vivo/sesiones/" + session["id"]
            self.assertEqual(self.request("POST", url + "/pausar")[1]["status"], "pausada")
            self.assertEqual(self.request("POST", url + "/reanudar")[1]["status"], "capturando")
            self.assertEqual(self.request("POST", url + "/marcar")[1]["marcas"][0]["second"], 2)
            self.assertEqual(self.request("POST", url + "/finalizar")[0], 202)
            self.wait_for(session["id"], "lista")
            self.assertEqual(self.request("GET", url)[1]["meeting_id"], live_sessions.get_session(session["id"])["meeting_id"])
            self.assertEqual(self.request("GET", "/api/en-vivo/sesiones")[1]["items"][0]["id"], session["id"])

    def test_floating_window_launch_reuses_running_process(self):
        with patch.object(live_sessions, "_window_process", None), \
             patch("live_sessions.subprocess.Popen") as launch:
            launch.return_value.poll.return_value = None
            status, first = self.request("POST", "/api/en-vivo/ventana")
            self.assertEqual(status, 200)
            self.assertEqual(first, {"abierta": True, "ya_estaba_abierta": False})
            status, second = self.request("POST", "/api/en-vivo/ventana")
            self.assertEqual(status, 200)
            self.assertTrue(second["ya_estaba_abierta"])
            launch.assert_called_once()

    def test_incremental_preview_keeps_boundary_speech_once(self):
        directory = Path(self.temp.name)
        silence = np.zeros(24 * SAMPLE_RATE, dtype="<i2")
        for track in ("sistema", "microfono"):
            silence.tofile(directory / (track + ".pcm"))
        previews = []
        ready = threading.Event()
        def updated(segments):
            previews.append(segments)
            if len(previews) == 2:
                ready.set()
        first = ([{"inicio": 1, "fin": 2, "texto": "Inicio"},
                  {"inicio": 10, "fin": 11.5, "texto": "Límite"}], "es", "test")
        second = ([{"inicio": 1, "fin": 2, "texto": "Límite"},
                   {"inicio": 9, "fin": 10, "texto": "Final"}], "es", "test")
        with patch("live_transcription.transcribe_samples", side_effect=[first, second]):
            transcriber = LiveTranscriber(directory, updated)
            transcriber.start()
            self.assertTrue(ready.wait(5))
            transcriber.stop()
        self.assertEqual([item["texto"] for item in previews[-1]], ["Inicio", "Límite", "Final"])
        self.assertEqual([item["inicio"] for item in previews[-1]], [1, 10.5, 18.5])
