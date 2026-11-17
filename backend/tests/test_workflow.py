import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import database
from analysis_service import chunks, ground_tasks, merge_summary, explicit_agreements
from main import app

TEXT = "Revisamos el proyecto. Carlos preparará la presentación para el viernes. Ana revisará el diseño. Carlos enviará el informe."
TRANSCRIPTION = {"texto": TEXT, "idioma": "es", "duracion_segundos": 60,
                 "segmentos": [{"inicio": 0, "fin": 60, "texto": TEXT}], "modelo": "whisper-test"}
TASK = {"descripcion": "Preparar la presentación", "responsable": "Carlos", "fecha_limite": "el viernes",
        "evidencia": "Carlos preparará la presentación para el viernes.", "inicio": 0, "fin": 60}
ANALYSIS = {"resumen": {"temas": ["Avance del proyecto"], "acuerdos": [], "conclusiones": []},
            "pendientes": [TASK], "advertencias": [], "modelo": "test-double"}


async def asgi_request(method, url, data=None, raw=None, content_type="application/json"):
    parsed = urlsplit(url)
    body = raw if raw is not None else json.dumps(data).encode("utf-8") if data is not None else b""
    messages, received = [], False
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": parsed.path, "raw_path": parsed.path.encode(),
             "query_string": parsed.query.encode(), "root_path": "", "server": ("testserver", 80),
             "client": ("127.0.0.1", 1000), "headers": [(b"content-type", content_type.encode())]}
    async def receive():
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}
    async def send(message):
        messages.append(message)
    await app(scope, receive, send)
    status = next(message["status"] for message in messages if message["type"] == "http.response.start")
    content = b"".join(message.get("body", b"") for message in messages if message["type"] == "http.response.body")
    return status, json.loads(content)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = database.DB_PATH
        database.DB_PATH = Path(self.temp.name) / "test.sqlite3"
        database.initialize()

    def tearDown(self):
        database.DB_PATH = self.old_path
        self.temp.cleanup()

    def request(self, method, url, data=None, **kwargs):
        # The sandbox denies the socket pair used by Windows' event loop.
        # Drive the real ASGI app in memory and replace only thread dispatch.
        async def inline(target, /, *args, **kwargs):
            return target(*args, **kwargs)
        with ExitStack() as stack:
            for module in ("fastapi.routing", "fastapi.dependencies.utils", "starlette.routing", "starlette.background", "starlette.datastructures"):
                stack.enter_context(patch(module + ".run_in_threadpool", inline, create=True))
            coroutine = asgi_request(method, url, data, **kwargs)
            try:
                coroutine.send(None)
            except StopIteration as result:
                return result.value
            finally:
                coroutine.close()
        raise AssertionError("El transporte de prueba encontró una espera no prevista.")

    def create(self, key="operation-1", title="Planeación semanal"):
        status, body = self.request("POST", "/api/reuniones", {"request_id": key, "title": title,
            "userName": "Carlos", "fileName": "reunion.wav", "transcription": TRANSCRIPTION})
        self.assertEqual(status, 201)
        return body

    def complete(self):
        meeting = self.create()
        with patch("meetings.availability", return_value={"disponible": True}), patch("meetings.analyze_transcript", return_value=copy.deepcopy(ANALYSIS)):
            status, _ = self.request("POST", f"/api/reuniones/{meeting['id']}/analizar")
        self.assertEqual(status, 202)
        return database.get_meeting(meeting["id"])

    def test_create_and_duplicate_retry_do_not_duplicate_history(self):
        first, second = self.create(), self.create()
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(database.list_meetings()["total"], 1)

    def test_notes_and_status_survive_new_database_connections(self):
        meeting = self.complete()
        task = meeting["pendientes"][0]
        status, result = self.request("PATCH", f"/api/reuniones/{meeting['id']}/pendientes/{task['id']}",
            {"version": 0, "nota": "Incluir gráficos y revisión de José.", "estado": "en_curso"})
        self.assertEqual(status, 200)
        self.assertEqual(result["version"], 1)
        database.initialize()
        status, restored = self.request("GET", f"/api/reuniones/{meeting['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(restored["pendientes"][0]["nota"], "Incluir gráficos y revisión de José.")
        self.assertEqual(restored["pendientes"][0]["estado"], "en_curso")
        self.assertEqual(restored["resumen"], ANALYSIS["resumen"])

    def test_stale_note_cannot_overwrite_a_newer_note(self):
        meeting = self.complete()
        task_id = meeting["pendientes"][0]["id"]
        url = f"/api/reuniones/{meeting['id']}/pendientes/{task_id}"
        self.assertEqual(self.request("PATCH", url, {"version": 0, "nota": "Primera nota"})[0], 200)
        self.assertEqual(self.request("PATCH", url, {"version": 0, "nota": "Nota desactualizada"})[0], 409)
        self.assertEqual(database.get_meeting(meeting["id"])["pendientes"][0]["nota"], "Primera nota")

    def test_clearing_note_persists_and_does_not_change_status(self):
        meeting = self.complete()
        task = meeting["pendientes"][0]
        url = f"/api/reuniones/{meeting['id']}/pendientes/{task['id']}"
        self.request("PATCH", url, {"version": 0, "nota": "Borrador", "estado": "completado"})
        status, task = self.request("PATCH", url, {"version": 1, "nota": ""})
        self.assertEqual(status, 200)
        self.assertEqual(task["nota"], "")
        self.assertEqual(task["estado"], "completado")

    def test_task_is_scoped_to_its_meeting(self):
        meeting = self.complete()
        other = self.create("operation-2")
        url = f"/api/reuniones/{other['id']}/pendientes/{meeting['pendientes'][0]['id']}"
        self.assertEqual(self.request("PATCH", url, {"version": 0, "nota": "Otro"})[0], 404)

    def test_missing_model_retains_saved_transcript(self):
        meeting = self.create()
        with patch("meetings.availability", return_value={"disponible": False}):
            status, _ = self.request("POST", f"/api/reuniones/{meeting['id']}/analizar")
        self.assertEqual(status, 503)
        restored = database.get_meeting(meeting["id"])
        self.assertEqual(restored["texto"], TEXT)
        self.assertEqual(restored["analysis_status"], "error")

    def test_inference_failure_can_be_retried_without_audio(self):
        meeting = self.create()
        with patch("meetings.availability", return_value={"disponible": True}), patch("meetings.analyze_transcript", side_effect=RuntimeError("test failure")):
            self.request("POST", f"/api/reuniones/{meeting['id']}/analizar")
        self.assertEqual(database.get_meeting(meeting["id"])["analysis_status"], "error")
        with patch("meetings.availability", return_value={"disponible": True}), patch("meetings.analyze_transcript", return_value=copy.deepcopy(ANALYSIS)):
            self.request("POST", f"/api/reuniones/{meeting['id']}/analizar")
        self.assertEqual(database.get_meeting(meeting["id"])["analysis_status"], "listo")

    def test_repeated_analysis_preserves_notes_and_task_ids(self):
        meeting = self.complete()
        task = meeting["pendientes"][0]
        database.update_task(meeting["id"], task["id"], {"version": 0, "nota": "Conservar"})
        with patch("meetings.analyze_transcript") as infer:
            self.request("POST", f"/api/reuniones/{meeting['id']}/analizar")
            infer.assert_not_called()
        restored = database.get_meeting(meeting["id"])
        self.assertEqual(restored["pendientes"][0]["id"], task["id"])
        self.assertEqual(restored["pendientes"][0]["nota"], "Conservar")

    def test_restart_marks_only_interrupted_analysis_for_retry(self):
        complete = self.complete()
        pending = self.create("operation-2")
        database.claim_analysis(pending["id"])
        database.recover_interrupted()
        self.assertEqual(database.get_meeting(pending["id"])["analysis_status"], "error")
        self.assertEqual(database.get_meeting(complete["id"])["analysis_status"], "listo")

    def test_search_is_literal_and_pagination_is_bounded(self):
        self.create(title="Reporte 100%")
        self.create("operation-2", title="Otra reunión")
        self.assertEqual(self.request("GET", "/api/reuniones?q=100%25")[1]["total"], 1)
        self.assertEqual(self.request("GET", "/api/reuniones?q=%27%20OR%201%3D1--")[1]["total"], 0)
        self.assertEqual(self.request("GET", "/api/reuniones?limit=1000")[0], 422)
        self.assertEqual(len(self.request("GET", "/api/reuniones?limit=1&offset=1")[1]["items"]), 1)

    def test_invalid_name_and_status_are_rejected(self):
        data = {"request_id": "invalid", "title": "", "userName": " ", "fileName": "x.wav", "transcription": TRANSCRIPTION}
        self.assertEqual(self.request("POST", "/api/reuniones", data)[0], 422)
        meeting = self.complete()
        task = meeting["pendientes"][0]
        self.assertEqual(self.request("PATCH", f"/api/reuniones/{meeting['id']}/pendientes/{task['id']}", {"version": 0, "estado": "inventado"})[0], 422)


class GroundingTests(unittest.TestCase):
    def test_explicit_votes_and_decisions_are_retained_without_promoting_conditions(self):
        result = explicit_agreements("Si se aprueba, firmaremos. No se aprueba la propuesta. Está a su consideración el acuerdo mediante el cual se aprueba el convenio. Acordamos revisar el lunes. Se aprueba por unanimidad el convenio.")
        self.assertEqual([item["texto"] for item in result["acuerdos"]],
                         ["Acordamos revisar el lunes.", "Se aprueba por unanimidad el convenio."])

    def test_summary_requires_literal_evidence_and_explicit_decisions(self):
        source = "Se propone publicar datos. Se aprueba por unanimidad el convenio. Existe la posibilidad de reelegir legisladores."
        summary = {"temas": [], "acuerdos": [], "conclusiones": []}
        evidence = copy.deepcopy(summary)
        response = {"temas": [{"texto": "Tema inventado", "evidencia": "Una frase ausente."}],
                    "acuerdos": [{"texto": "Publicar datos", "evidencia": "Se propone publicar datos."},
                                 {"texto": "Firmar hoy", "evidencia": "Se aprueba por unanimidad el convenio."}],
                    "conclusiones": [{"texto": "Reelegir legisladores", "evidencia": "Existe la posibilidad de reelegir legisladores."}]}
        merge_summary(summary, evidence, response, source)
        self.assertEqual(summary, {"temas": [], "acuerdos": ["Se aprueba por unanimidad el convenio."], "conclusiones": []})

    def test_summary_merges_repeated_subjects_and_bounds_overall_length(self):
        source = "Convenios de Parlamento Abierto. Parlamento Abierto. " + " ".join("Tema %s." % i for i in range(12))
        points = [{"texto": "Convenios de Parlamento Abierto", "evidencia": "Convenios de Parlamento Abierto."},
                  {"texto": "Parlamento Abierto", "evidencia": "Parlamento Abierto."}]
        points += [{"texto": "Tema %s" % i, "evidencia": "Tema %s." % i} for i in range(12)]
        summary = {"temas": [], "acuerdos": [], "conclusiones": []}
        evidence = copy.deepcopy(summary)
        merge_summary(summary, evidence, {"temas": points, "acuerdos": [], "conclusiones": []}, source)
        self.assertEqual(len(summary["temas"]), 6)
        self.assertNotIn("Parlamento Abierto", summary["temas"])

    def ground(self, candidates, text=TEXT):
        return ground_tasks(candidates, text, TRANSCRIPTION["segmentos"], "Carlos")

    def test_only_named_owner_and_literal_source_are_accepted(self):
        candidates = [copy.deepcopy(TASK), {**TASK, "responsable": "Ana"},
                      {**TASK, "evidencia": "Carlos comprará una computadora."},
                      {**TASK, "evidencia": "Ana revisará el diseño."}]
        tasks, rejected = self.ground(candidates)
        self.assertEqual(len(tasks), 1)
        self.assertEqual(rejected, 3)
        self.assertEqual(tasks[0]["inicio"], 0)

    def test_name_substring_is_not_an_assignment(self):
        task = {**TASK, "evidencia": "Carlosina preparará el informe."}
        self.assertEqual(self.ground([task], text=task["evidencia"])[0], [])

    def test_ungrounded_date_is_removed(self):
        tasks, _ = self.ground([{**TASK, "fecha_limite": "2026-11-20"}])
        self.assertIsNone(tasks[0]["fecha_limite"])

    def test_duplicate_overlapping_chunks_do_not_duplicate_tasks(self):
        self.assertEqual(len(self.ground([TASK, TASK])[0]), 1)

    def test_different_actions_can_share_one_source_quote(self):
        quote = "Carlos preparará la presentación y enviará el informe."
        first = {**TASK, "evidencia": quote}
        second = {**TASK, "descripcion": "Enviar el informe", "evidencia": quote}
        tasks, _ = self.ground([first, second], text=quote)
        self.assertEqual(len(tasks), 2)

    def test_personal_interest_is_not_an_assigned_task(self):
        quote = "Carlos comenta que quiere aprender más sobre bases de datos."
        candidate = {**TASK, "descripcion": "Aprender sobre bases de datos", "evidencia": quote}
        tasks, rejected = self.ground([candidate], text=quote)
        self.assertEqual(tasks, [])
        self.assertEqual(rejected, 1)

    def test_long_meeting_is_chunked_without_losing_the_last_assignment(self):
        text = ("Revisamos el avance. " * 700) + "Carlos enviará el informe el jueves."
        parts = list(chunks(text))
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(part) <= 6000 for part in parts))
        self.assertIn("Carlos enviará el informe el jueves.", parts[-1])

    def test_unpunctuated_long_transcript_is_bounded(self):
        text = "palabra " * 2000
        self.assertTrue(all(len(part) <= 6000 for part in chunks(text)))


if __name__ == "__main__":
    unittest.main()
