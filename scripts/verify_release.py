"""Offline release check: real audio -> Whisper -> Qwen -> SQLite -> notes -> cancellation.

Uses a synthetic, labelled recording and a temporary database, never the user's meetings.
The in-memory ASGI transport replaces only thread dispatch for this restricted executor.
"""
import json
import sys
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'backend'),str(ROOT/'backend/tests')]
import database
import jobs_service
from test_workflow import WorkflowTests


def main():
    (ROOT/'backups/pendientes-app').mkdir(parents=True,exist_ok=True)
    report = {'audio':'samples/reunion-controlada.wav','tipo_audio':'voz sintética, Microsoft Zira','motor_voz':'Whisper real','motor_texto':'Qwen local real'}
    original = database.DB_PATH
    with tempfile.TemporaryDirectory(prefix='meet-notes-validacion-') as temp:
        database.DB_PATH = Path(temp)/'validacion.sqlite3'
        database.initialize()
        transport = WorkflowTests(methodName='runTest')
        job_id = str(uuid4())
        boundary = 'MeetNotesValidationBoundary'
        fields = {'request_id':job_id,'userName':'Carlos','title':'Reunión de prueba automática'}
        body = b''
        for name,value in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="reunion-controlada.wav"\r\nContent-Type: audio/wav\r\n\r\n'.encode()
        body += (ROOT/'samples/reunion-controlada.wav').read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
        status,job = transport.request('POST','/api/trabajos',raw=body,content_type='multipart/form-data; boundary='+boundary)
        assert status==202,(status,job)
        started=time.monotonic(); previous=None
        while True:
            status,job=transport.request('GET',f'/api/trabajos/{job_id}')
            if job['stage']!=previous: print('ETAPA:',job['stage'],flush=True);previous=job['stage']
            if job['status']!='procesando': break
            if time.monotonic()-started>240: jobs_service.cancel_worker(job_id);raise AssertionError('Tiempo de prueba excedido')
            time.sleep(.4)
        assert job['status']=='listo',job
        status,meeting=transport.request('GET','/api/reuniones/'+job['meeting_id'])
        report.update({'duracion_real':meeting['duracion_segundos'],'transcripcion_real':meeting['texto'],
                       'resumen_general':meeting['resumen_general'],'pendientes':meeting['pendientes'],'por_confirmar':meeting['por_confirmar']})
        print(json.dumps(report,ensure_ascii=True),flush=True)
        assert meeting['resumen_general']
        assert meeting['pendientes'],'No se identificaron tareas de Carlos en el audio'
        assert all(t['responsable']=='Carlos' for t in meeting['pendientes'])
        task=meeting['pendientes'][0]
        route=f"/api/reuniones/{meeting['id']}/pendientes/{task['id']}"
        status,saved=transport.request('PATCH',route,{'version':task['version'],'nota':'Nota guardada en la prueba integral.','estado':'en_curso'})
        assert status==200,saved
        database.initialize()
        restored=database.get_meeting(meeting['id'])
        assert restored['pendientes'][0]['nota']=='Nota guardada en la prueba integral.'
        assert restored['pendientes'][0]['estado']=='en_curso'
        report['nota_y_estado_recuperados']=True
        if meeting['por_confirmar']:
            proposal=meeting['por_confirmar'][0]
            status,confirmed=transport.request('PATCH',f"/api/reuniones/{meeting['id']}/propuestas/{proposal['id']}",{'version':proposal['version'],'decision':'confirmar'})
            assert status==200,confirmed
            assert len(confirmed['por_confirmar'])==len(meeting['por_confirmar'])-1
            report['confirmacion_manual_api']=True
        cancel_id=str(uuid4())
        database.create_job(cancel_id,'Cancelación real','Carlos','audio.wav',str(ROOT/'samples/reunion-controlada.wav'))
        jobs_service.start_worker(cancel_id)
        process=jobs_service._workers[cancel_id]
        status,cancelled=transport.request('POST',f'/api/trabajos/{cancel_id}/cancelar')
        assert status==200 and cancelled['status']=='cancelado'
        assert process.poll() is not None
        report['cancelacion_proceso_real']=True
        while jobs_service._workers: time.sleep(.05)
        report['segundos']=round(time.monotonic()-started,2)
        (ROOT/'backups/pendientes-app/validacion-integral.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        database.DB_PATH=original
    print('VALIDACIÓN INTEGRAL REAL CORRECTA',flush=True)


if __name__=='__main__': main()
