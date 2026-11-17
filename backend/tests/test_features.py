import copy
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import test_workflow as workflow
from test_workflow import TASK, ANALYSIS, TRANSCRIPTION
import database
from analysis_service import classify_tasks, overview
from process_control import ProcessingCancelled, run_cancellable
from task_matching import deduplicate
from jobs_service import cancel_worker, _workers


class FeaturesTests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp
    tearDown = workflow.WorkflowTests.tearDown
    request = workflow.WorkflowTests.request
    create = workflow.WorkflowTests.create
    complete = workflow.WorkflowTests.complete
    def test_general_overview_uses_source_and_removes_repetition(self):
        summary = {'temas':['Proyecto'], 'acuerdos':['Acordamos usar SQLite.'], 'conclusiones':[]}
        result = overview(summary, {'temas':['Revisamos el proyecto.'], 'acuerdos':[], 'conclusiones':[]}, ['Revisamos el proyecto.'])
        self.assertEqual(result, 'Revisamos el proyecto. Acordamos usar SQLite.')

    def test_equivalent_tasks_merge_with_all_quotes(self):
        first = {**TASK, 'descripcion':'Enviar el informe', 'evidencia':'Carlos enviará el informe.'}
        second = {**TASK, 'descripcion':'Remitir el informe', 'evidencia':'Carlos remitirá el informe.'}
        result = deduplicate([first,second])
        self.assertEqual(len(result),1)
        self.assertEqual(len(result[0]['evidencias']),2)

    def test_different_action_object_and_date_are_not_merged(self):
        first = {**TASK, 'descripcion':'Enviar el informe'}
        for change in ({'descripcion':'Revisar el informe'}, {'descripcion':'Enviar el presupuesto'}, {'fecha_limite':'el lunes'}):
            self.assertEqual(len(deduplicate([first,{**first,**change}])),2)

    def classify(self, text, candidates, doubtful=(), name='Carlos'):
        return classify_tasks(candidates, doubtful, {'texto':text,'userName':name,'segmentos':[]})

    def test_same_first_names_require_a_person_choice(self):
        text = 'Participan Carlos Pérez y Carlos López. Carlos preparará la presentación para el viernes.'
        tasks, proposals, _ = self.classify(text,[{**TASK,'evidencia':'Carlos preparará la presentación para el viernes.'}])
        self.assertEqual(tasks,[])
        self.assertEqual(proposals[0]['opciones'],['Carlos López','Carlos Pérez'])

    def test_unknown_owner_becomes_review_not_personal_task(self):
        tasks, proposals, _ = self.classify('Alguien debería revisar los colores.',[])
        self.assertEqual(tasks,[])
        self.assertEqual(len(proposals),1)
        self.assertIsNone(proposals[0]['responsable'])

    def test_conditional_request_is_not_a_confirmed_assignment(self):
        text = 'Carlos, ¿puedes preparar la presentación?'
        tasks, proposals, _ = self.classify(text,[{**TASK,'evidencia':text}])
        self.assertEqual(tasks,[])
        self.assertEqual(len(proposals),1)

    def test_full_name_does_not_claim_someone_elses_task(self):
        text = 'Carlos López preparará la presentación.'
        tasks, proposals, _ = self.classify(text,[{**TASK,'responsable':'Carlos Pérez','evidencia':text}],name='Carlos Pérez')
        self.assertEqual(tasks,[])
        self.assertEqual(proposals,[])

    def test_fabricated_quote_and_personal_wish_never_become_proposals(self):
        text = 'Carlos quiere aprender italiano.'
        data = [{**TASK,'evidencia':text,'motivo':'duda'}, {**TASK,'evidencia':'Carlos hará otra cosa.','motivo':'duda'}]
        tasks, proposals, _ = self.classify(text,[],data)
        self.assertEqual(tasks,[])
        self.assertEqual(proposals,[])

    def reviewed_meeting(self, options=()):
        meeting = self.create()
        result = copy.deepcopy(ANALYSIS)
        result['por_confirmar'] = [{**TASK,'motivo':'Responsable por confirmar','opciones':list(options)}]
        database.finish_analysis(meeting['id'],result)
        return database.get_meeting(meeting['id'])

    def test_confirming_duplicate_preserves_note_and_state(self):
        meeting = self.reviewed_meeting()
        task = meeting['pendientes'][0]
        database.update_task(meeting['id'],task['id'],{'version':0,'nota':'Conservar','estado':'en_curso'})
        proposal = meeting['por_confirmar'][0]
        status, result = self.request('PATCH',f"/api/reuniones/{meeting['id']}/propuestas/{proposal['id']}",{'version':0,'decision':'confirmar'})
        self.assertEqual(status,200)
        self.assertEqual(len(result['pendientes']),1)
        self.assertEqual(result['pendientes'][0]['nota'],'Conservar')
        self.assertEqual(result['pendientes'][0]['estado'],'en_curso')
        self.assertEqual(result['por_confirmar'],[])
        self.assertEqual(result['pendientes'][0]['origen'],'usuario')

    def test_homonym_confirmation_requires_an_allowed_full_name(self):
        meeting = self.reviewed_meeting(['Carlos Pérez','Carlos López'])
        proposal = meeting['por_confirmar'][0]
        url = f"/api/reuniones/{meeting['id']}/propuestas/{proposal['id']}"
        self.assertEqual(self.request('PATCH',url,{'version':0,'decision':'confirmar'})[0],409)
        self.assertEqual(self.request('PATCH',url,{'version':0,'decision':'confirmar','responsable':'Carlos Pérez'})[0],200)
        self.assertEqual(self.request('PATCH',url,{'version':0,'decision':'confirmar','responsable':'Carlos Pérez'})[0],409)

    def test_discard_does_not_create_a_task(self):
        meeting = self.reviewed_meeting(); proposal = meeting['por_confirmar'][0]
        result = database.resolve_proposal(meeting['id'],proposal['id'],{'version':0,'decision':'descartar'})
        self.assertEqual(len(result['pendientes']),1)
        self.assertEqual(result['por_confirmar'],[])

    def test_cancelled_analysis_cannot_write_after_retry(self):
        meeting = self.create(); database.claim_analysis(meeting['id']); token = database.get_meeting(meeting['id'])['analysis_token']
        self.assertEqual(self.request('POST',f"/api/reuniones/{meeting['id']}/cancelar")[1]['analysis_status'],'cancelado')
        database.claim_analysis(meeting['id']); current = database.get_meeting(meeting['id'])['analysis_token']
        database.finish_analysis(meeting['id'],ANALYSIS,token)
        database.fail_analysis(meeting['id'],'fallo antiguo',token)
        self.assertEqual(database.get_meeting(meeting['id'])['analysis_token'],current)
        self.assertEqual(database.get_meeting(meeting['id'])['pendientes'],[])
        database.finish_analysis(meeting['id'],ANALYSIS,current)
        self.assertEqual(database.get_meeting(meeting['id'])['analysis_status'],'listo')

    def test_cancel_before_upload_creates_a_tombstone_and_never_starts(self):
        job_id = str(uuid4())
        status, result = self.request('POST',f'/api/trabajos/{job_id}/cancelar')
        self.assertEqual(status,200)
        self.assertEqual(result['status'],'cancelado')
        self.assertEqual(database.create_job(job_id)['status'],'cancelado')

    def test_job_start_is_idempotent_and_only_one_audio_runs(self):
        job_id = str(uuid4()); database.create_job(job_id)
        self.assertEqual(database.create_job(job_id)['id'],job_id)
        with self.assertRaises(database.ConflictError): database.create_job(str(uuid4()))

    def test_cancellation_terminates_an_actual_owned_process(self):
        job_id = str(uuid4()); database.create_job(job_id)
        process = subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0,
                                  start_new_session=os.name!='nt')
        _workers[job_id] = process
        try:
            self.assertEqual(cancel_worker(job_id)['status'],'cancelado')
            self.assertIsNotNone(process.poll())
        finally:
            _workers.pop(job_id,None)
            if process.poll() is None: process.kill(); process.wait()

    def test_cancellable_inference_never_runs_after_cancel(self):
        with self.assertRaises(ProcessingCancelled):
            run_cancellable([sys.executable,'-c','raise SystemExit(99)'],cancelled=lambda:True)


    def test_name_mention_without_commitment_is_not_confirmed(self):
        text = 'Carlos comentó sobre el informe.'
        tasks, proposals, _ = self.classify(text,[{**TASK,'descripcion':'Enviar el informe','evidencia':text}])
        self.assertEqual(tasks,[])
        self.assertEqual(proposals,[])

    def test_upload_job_validation_idempotency_and_cancellation(self):
        import jobs
        import jobs_service
        upload_root = Path(self.temp.name)/'uploads'
        def upload(job_id, content=b'fake-audio', filename='audio.wav'):
            boundary='FeatureTestBoundary'
            fields={'request_id':job_id,'userName':'Carlos','title':'Prueba'}
            body=b''
            for key,value in fields.items():
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode()
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{filename}"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+content+f'\r\n--{boundary}--\r\n'.encode()
            return self.request('POST','/api/trabajos',raw=body,content_type='multipart/form-data; boundary='+boundary)
        with patch.object(jobs,'WORK_ROOT',upload_root),patch.object(jobs_service,'WORK_ROOT',upload_root),patch.object(jobs,'start_worker') as start:
            self.assertEqual(upload(str(uuid4()),filename='audio.exe')[0],415)
            self.assertEqual(upload(str(uuid4()),content=b'')[0],400)
            job_id=str(uuid4())
            self.assertEqual(upload(job_id)[0],202)
            self.assertEqual(upload(job_id)[0],202)
            self.assertEqual(start.call_count,1)
            self.assertEqual(self.request('POST',f'/api/trabajos/{job_id}/cancelar')[1]['status'],'cancelado')
            jobs_service.clean_workspace(job_id)
            cancelled=str(uuid4())
            self.request('POST',f'/api/trabajos/{cancelled}/cancelar')
            self.assertEqual(upload(cancelled)[1]['status'],'cancelado')
            self.assertEqual(start.call_count,1)


    def test_negative_assignment_is_not_a_task_or_a_proposal(self):
        text = 'Carlos no enviará el informe.'
        tasks, proposals, _ = self.classify(text,[{**TASK,'descripcion':'Enviar el informe','evidencia':text}])
        self.assertEqual(tasks,[])
        self.assertEqual(proposals,[])

    def test_date_article_does_not_duplicate_the_same_task(self):
        first = {**TASK,'descripcion':'Enviar el informe','fecha_limite':'el viernes'}
        second = {**TASK,'descripcion':'Remitir el informe','fecha_limite':'viernes'}
        self.assertEqual(len(deduplicate([first,second])),1)

    def test_legacy_database_migrates_without_losing_notes(self):
        import sqlite3
        database.DB_PATH = Path(self.temp.name)/'legacy.sqlite3'
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.executescript("""
                CREATE TABLE meetings (id TEXT PRIMARY KEY,request_id TEXT UNIQUE,title TEXT,user_name TEXT,file_name TEXT,
                    transcription TEXT,analysis TEXT,analysis_status TEXT,analysis_error TEXT,progress INTEGER,created_at TEXT,updated_at TEXT);
                CREATE TABLE tasks (id TEXT PRIMARY KEY,meeting_id TEXT,descripcion TEXT,responsable TEXT,fecha_limite TEXT,
                    evidencia TEXT,inicio REAL,fin REAL,nota TEXT,estado TEXT,version INTEGER,updated_at TEXT);
            """)
            conn.execute("INSERT INTO meetings VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",('old','old','Anterior','Carlos','audio.wav',json.dumps(TRANSCRIPTION),json.dumps(ANALYSIS),'listo','',100,'2026','2026'))
            conn.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",('task-old','old','Presentación','Carlos',None,'Cita',0,1,'Nota anterior','en_curso',4,'2026'))
        conn.close()
        database.initialize()
        restored=database.get_meeting('old')
        self.assertEqual(restored['pendientes'][0]['nota'],'Nota anterior')
        self.assertEqual(restored['pendientes'][0]['estado'],'en_curso')
        self.assertEqual(restored['pendientes'][0]['version'],4)
        self.assertEqual(restored['por_confirmar'],[])

    def test_database_failure_is_reported_without_leaking_details(self):
        import sqlite3
        with patch.object(database,'connection',side_effect=sqlite3.OperationalError('secret internal path')):
            status,body=self.request('GET','/api/reuniones')
        self.assertEqual(status,503)
        self.assertNotIn('secret internal path',json.dumps(body))
