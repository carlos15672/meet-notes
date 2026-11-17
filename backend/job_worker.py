"""Worker entry point: real Whisper and local LLM, without HTTP transport."""
import logging
import sys
from pathlib import Path

import database
from analysis_service import AnalysisUnavailableError, analyze_transcript
from process_control import ProcessingCancelled, check_cancelled
from whisper_service import transcribir_audio


def process_job(job_id):
    token = None
    meeting_id = None
    cancelled = lambda: database.get_job(job_id)['status'] != 'procesando'
    try:
        check_cancelled(cancelled)
        job = database.get_job(job_id)
        database.update_job(job_id, 'transcribiendo')
        transcription = transcribir_audio(Path(job['input_path']))
        check_cancelled(cancelled)
        meeting = database.create_meeting({'request_id': job_id, 'title': job['title'], 'userName': job['user_name'],
                                           'fileName': job['file_name'], 'transcription': transcription})
        meeting_id = meeting['id']
        database.update_job(job_id, 'analizando', meeting_id=meeting_id)
        check_cancelled(cancelled)
        if database.claim_analysis(meeting_id):
            meeting = database.get_meeting(meeting_id)
            token = meeting['analysis_token']
            should_cancel = lambda: cancelled() or database.analysis_cancelled(meeting_id, token)
            result = analyze_transcript(meeting, lambda n: database.analysis_progress(meeting_id,n,token), cancelled=should_cancel)
            check_cancelled(should_cancel)
            database.finish_analysis(meeting_id, result, token)
        database.update_job(job_id, 'listo', status='listo', meeting_id=meeting_id)
    except ProcessingCancelled:
        if meeting_id:
            database.cancel_analysis(meeting_id, token)
        database.cancel_job(job_id)
    except Exception as error:
        message = str(error) if isinstance(error, (AnalysisUnavailableError, ValueError)) else 'No se pudo completar el procesamiento. Puedes reintentarlo.'
        if meeting_id:
            database.fail_analysis(meeting_id, message, token)
        database.update_job(job_id, 'error', status='error', meeting_id=meeting_id, error=message)
        logging.exception('Falló un trabajo de meet-notes.')


if __name__ == '__main__':
    process_job(sys.argv[1])
