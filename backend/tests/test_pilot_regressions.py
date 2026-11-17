import copy
import unittest
from unittest.mock import patch

import test_workflow as workflow
from test_workflow import TASK, TRANSCRIPTION
import database
from analysis_service import analyze_transcript, classify_tasks, overview
from assignment_rules import assignment, explicit_tasks, upcoming_meetings


PILOT = ("Estamos organizando la entrega del proyecto. Carlos prepara las diapositivas y las enviará el viernes. "
         "Ana revisará el documento antes del jueves. Carlos también debe agregar las capturas de la aplicación a las diapositivas. "
         "Todavía falta decidir quién realizará las pruebas con usuarios. Acordamos entregar el documento en PDF. "
         "La próxima reunión será el martes.")


class AssignmentRegressionTests(unittest.TestCase):
    def classify(self, text, candidates, user="Carlos"):
        return classify_tasks(candidates, [], {"texto":text,"segmentos":[],"userName":user})

    def test_adverb_before_obligation_is_a_direct_assignment(self):
        for adverb in ("también", "además", "finalmente", "también, ahora"):
            quote = f"Carlos {adverb} debe agregar las capturas."
            tasks, proposals, _ = self.classify(quote,[{**TASK,"descripcion":"Agregar capturas","evidencia":quote}])
            self.assertEqual(len(tasks),1,quote);self.assertEqual(proposals,[])

    def test_present_with_coordinated_future_keeps_the_complete_assignment(self):
        tasks=explicit_tasks(PILOT,"carlos")
        self.assertEqual(len(tasks),2)
        self.assertIn("enviarlas",tasks[0]["descripcion"])
        self.assertEqual(tasks[0]["fecha_limite"],"el viernes")
        self.assertIsNone(tasks[1]["fecha_limite"])
        self.assertIn("capturas",tasks[1]["descripcion"])
        self.assertTrue(all(task["evidencia"] in PILOT for task in tasks))
        revised=explicit_tasks(PILOT.replace("Carlos prepara las", "Carlos preparará las"),"carlos")
        self.assertEqual(revised[0]["descripcion"],tasks[0]["descripcion"])

    def test_negative_conditional_question_desire_completed_and_other_owner_are_not_recovered(self):
        for quote in ("Carlos también no debe enviar el informe.", "Carlos ya envió el informe.",
                      "Carlos podría enviar el informe.", "¿Carlos enviará el informe?", "Si se aprueba, Carlos enviará el informe.",
                      "Carlos quiere enviar el informe.", "Carlos prepara el informe.", "Carlos estará ausente el viernes.",
                      "Ana revisará el informe.", "No hemos decidido que Carlos enviará el informe."):
            self.assertEqual(explicit_tasks(quote,"Carlos"),[],quote)

    def test_separate_future_actions_remain_separate_model_tasks(self):
        quote="Carlos preparará la presentación y enviará el informe."
        candidates=[{**TASK,"evidencia":quote},{**TASK,"descripcion":"Enviar el informe","evidencia":quote}]
        tasks, proposals, _ = self.classify(quote,candidates)
        self.assertEqual(len(tasks),2);self.assertEqual(proposals,[])
        self.assertEqual(explicit_tasks(quote,"Carlos"),[])

    def test_lowercase_user_name_does_not_hide_homonyms(self):
        text="Participan Carlos Pérez y Carlos López. Carlos preparará la presentación."
        tasks,proposals,_=self.classify(text,[{**TASK,"responsable":"carlos","evidencia":"Carlos preparará la presentación."}],user="carlos")
        self.assertEqual(tasks,[])
        self.assertEqual(proposals[0]["opciones"],["Carlos López","Carlos Pérez"])

    def test_next_meeting_is_kept_without_promoting_a_suggestion(self):
        self.assertEqual(upcoming_meetings(PILOT),["La próxima reunión será el martes."])
        for text in ("Quizás la próxima reunión será el martes.","¿La próxima reunión será el martes?",
                     "Si aprobamos, la próxima reunión será el martes.","La próxima reunión no será el martes."):
            self.assertEqual(upcoming_meetings(text),[],text)

    def test_real_quote_cannot_support_an_unrelated_proposed_task(self):
        quote="Carlos también debe agregar las capturas de la aplicación."
        proposal={"descripcion":"Decidir quién realizará las pruebas con usuarios","responsable":None,
                  "fecha_limite":None,"evidencia":quote,"motivo":"Pendiente"}
        tasks,proposals,_=classify_tasks([], [proposal], {"texto":quote,"segmentos":[],"userName":"Carlos"})
        self.assertEqual(tasks,[]);self.assertEqual(proposals,[])

    def test_real_quote_does_not_justify_an_invented_action(self):
        quote="Carlos debe agregar capturas."
        tasks,proposals,_=self.classify(quote,[{**TASK,"descripcion":"Borrar capturas","evidencia":quote}])
        self.assertEqual(tasks,[]);self.assertEqual(proposals,[])

    def test_missing_model_assignments_are_recovered_without_inventing_a_responsible_person(self):
        response={"resumen":{"temas":[],"acuerdos":[],"conclusiones":[]},"pendientes":[],"por_confirmar":[],"sintesis":None}
        with patch("analysis_service.availability",return_value={"disponible":True}),patch("analysis_service.infer",return_value=response):
            result=analyze_transcript({"texto":PILOT,"segmentos":[],"userName":"carlos"})
        self.assertEqual(len(result["pendientes"]),2)
        self.assertTrue(all(task["responsable"]=="carlos" for task in result["pendientes"]))
        self.assertIn("La próxima reunión será el martes.",result["resumen_general"])
        self.assertEqual(result["por_confirmar"],[])
        self.assertTrue(all(task["inicio"] is None for task in result["pendientes"]))


class ReviewPersistenceTests(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    request=workflow.WorkflowTests.request
    create=workflow.WorkflowTests.create
    complete=workflow.WorkflowTests.complete

    def test_review_creates_a_linked_version_preserving_original_notes_and_transcript(self):
        original=self.complete();task=original["pendientes"][0]
        database.update_task(original["id"],task["id"],{"version":0,"nota":"Nota anterior","estado":"en_curso"})
        transcription={**copy.deepcopy(TRANSCRIPTION),"texto":PILOT,"segmentos":[],"revision_manual":True,"reunion_origen":original["id"]}
        data={"request_id":"review-1","title":"Prueba revisada","userName":"Carlos","fileName":"audio.mp4","transcription":transcription}
        status,reviewed=self.request("POST","/api/reuniones",data)
        self.assertEqual(status,201);self.assertNotEqual(reviewed["id"],original["id"])
        self.assertTrue(reviewed["revision_manual"]);self.assertEqual(reviewed["reunion_origen"],original["id"])
        self.assertEqual(reviewed["segmentos"],[])
        self.assertEqual(self.request("POST","/api/reuniones",data)[1]["id"],reviewed["id"])
        previous=database.get_meeting(original["id"])
        self.assertEqual(previous["texto"],original["texto"])
        self.assertEqual(previous["pendientes"][0]["nota"],"Nota anterior")
        self.assertEqual(previous["pendientes"][0]["estado"],"en_curso")

    def test_upcoming_meeting_survives_storage(self):
        meeting=self.create()
        analysis={"resumen":{"temas":[],"acuerdos":[],"conclusiones":[]},"pendientes":[],"proximas_reuniones":["La próxima reunión será el martes."]}
        database.finish_analysis(meeting["id"],analysis)
        self.assertEqual(database.get_meeting(meeting["id"])["proximas_reuniones"],analysis["proximas_reuniones"])
