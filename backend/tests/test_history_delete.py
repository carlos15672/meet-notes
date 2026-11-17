import copy
import json
import sqlite3
import unittest
from uuid import uuid4

import test_workflow as workflow
from test_workflow import ANALYSIS, TASK
import database
from main import app


class HistoryDeleteTests(unittest.TestCase):
    setUp=workflow.WorkflowTests.setUp
    tearDown=workflow.WorkflowTests.tearDown
    request=workflow.WorkflowTests.request
    create=workflow.WorkflowTests.create
    complete=workflow.WorkflowTests.complete

    def with_contents(self):
        meeting=self.create()
        analysis=copy.deepcopy(ANALYSIS)
        analysis['por_confirmar']=[{**TASK,'motivo':'Revisar responsable','opciones':[]}]
        database.finish_analysis(meeting['id'],analysis)
        meeting=database.get_meeting(meeting['id'])
        task=meeting['pendientes'][0]
        database.update_task(meeting['id'],task['id'],{'version':0,'nota':'Nota personal','estado':'en_curso'})
        return database.get_meeting(meeting['id'])

    def test_deletes_only_selected_meeting_tasks_proposals_notes_and_job_metadata(self):
        target=self.with_contents(); other=self.create('other')
        job_id=str(uuid4()); database.create_job(job_id,'Título','Carlos','audio.wav','/temporary/audio.wav')
        database.update_job(job_id,'listo',status='listo',meeting_id=target['id'])
        status,result=self.request('DELETE',f"/api/reuniones/{target['id']}")
        self.assertEqual(status,200);self.assertTrue(result['eliminada'])
        self.assertEqual(self.request('GET',f"/api/reuniones/{target['id']}")[0],404)
        self.assertEqual(self.request('GET',f"/api/reuniones/{other['id']}")[0],200)
        self.assertEqual(database.list_meetings()['total'],1)
        with database.connection() as conn:
            for table in ('tasks','proposals'):
                self.assertEqual(conn.execute(f'SELECT count(*) FROM {table} WHERE meeting_id=?',(target['id'],)).fetchone()[0],0)
            self.assertEqual(conn.execute('PRAGMA foreign_key_check').fetchall(),[])
        job=database.get_job(job_id)
        self.assertIsNone(job['meeting_id']);self.assertEqual(job['status'],'listo')
        self.assertEqual([job[k] for k in ('title','user_name','file_name','input_path')],['','','',''])

    def test_missing_or_malicious_id_does_not_delete_other_meetings(self):
        target=self.create()
        self.assertEqual(self.request('DELETE',"/api/reuniones/not-found")[0],404)
        with self.assertRaises(database.NotFoundError):database.delete_meeting("' OR 1=1 --")
        self.assertEqual(database.list_meetings()['items'][0]['id'],target['id'])

    def test_active_analysis_must_be_cancelled_first(self):
        target=self.create();database.claim_analysis(target['id'])
        status,result=self.request('DELETE',f"/api/reuniones/{target['id']}")
        self.assertEqual(status,409);self.assertIn('Cancela',result['detail'])
        self.assertEqual(database.get_meeting(target['id'])['analysis_status'],'procesando')
        database.cancel_analysis(target['id'])
        self.assertEqual(self.request('DELETE',f"/api/reuniones/{target['id']}")[0],200)

    def test_active_job_is_protected_even_if_meeting_analysis_is_complete(self):
        target=self.with_contents();job_id=str(uuid4());database.create_job(job_id)
        database.update_job(job_id,'analizando',meeting_id=target['id'])
        self.assertEqual(self.request('DELETE',f"/api/reuniones/{target['id']}")[0],409)
        self.assertEqual(database.get_meeting(target['id'])['pendientes'][0]['nota'],'Nota personal')

    def test_late_autosave_cannot_recreate_deleted_tasks(self):
        target=self.with_contents();task=target['pendientes'][0]
        self.request('DELETE',f"/api/reuniones/{target['id']}")
        self.assertEqual(self.request('PATCH',f"/api/reuniones/{target['id']}/pendientes/{task['id']}",{'version':task['version'],'nota':'Tarde'})[0],404)
        self.assertEqual(database.list_meetings()['total'],0)

    def test_failed_delete_rolls_back_all_related_data(self):
        target=self.with_contents()
        with database.connection() as conn:
            conn.execute("CREATE TRIGGER reject_delete BEFORE DELETE ON meetings BEGIN SELECT RAISE(ABORT,'forced failure'); END")
        self.assertEqual(self.request('DELETE',f"/api/reuniones/{target['id']}")[0],503)
        restored=database.get_meeting(target['id'])
        self.assertEqual(restored['pendientes'][0]['nota'],'Nota personal')
        self.assertEqual(len(restored['por_confirmar']),1)

    def test_history_count_and_last_page_after_deletion(self):
        for number in range(21):self.create('page-'+str(number))
        last=database.list_meetings(offset=20)['items'][0]
        self.request('DELETE',f"/api/reuniones/{last['id']}")
        result=database.list_meetings(offset=20)
        self.assertEqual(result['total'],20);self.assertEqual(result['items'],[])
        self.assertEqual(len(database.list_meetings()['items']),20)

    def test_browser_cors_preflight_allows_delete(self):
        messages=[]
        async def receive():return {'type':'http.request','body':b'','more_body':False}
        async def send(message):messages.append(message)
        scope={'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':'OPTIONS','scheme':'http',
               'path':'/api/reuniones/example','raw_path':b'/api/reuniones/example','query_string':b'',
               'headers':[(b'origin',b'http://localhost:5173'),(b'access-control-request-method',b'DELETE')]}
        coroutine=app(scope,receive,send)
        try:
            with self.assertRaises(StopIteration):coroutine.send(None)
        finally:coroutine.close()
        response=next(m for m in messages if m['type']=='http.response.start')
        self.assertEqual(response['status'],200)
        self.assertIn(b'DELETE',dict(response['headers'])[b'access-control-allow-methods'])

    def test_audio_job_is_protected_before_meeting_link_is_attached(self):
        job_id=str(uuid4());database.create_job(job_id)
        target=self.create(key=job_id)
        self.assertEqual(self.request('DELETE',f"/api/reuniones/{target['id']}")[0],409)
        self.assertEqual(database.get_meeting(target['id'])['id'],target['id'])
