from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
import database
from audio_formats import ALLOWED_EXTENSIONS, FORMAT_ERROR, MAX_AUDIO_BYTES
from jobs_service import WORK_ROOT, cancel_worker, clean_workspace, public_job, start_worker

router = APIRouter(prefix='/api/trabajos', tags=['Procesamiento'])


def valid_id(job_id):
    try:
        if str(UUID(job_id)) != job_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=422, detail='Identificador de procesamiento inválido.')


@router.post('', status_code=202)
async def create_job(request_id: str = Form(...), userName: str = Form(...), title: str = Form(''), audio: UploadFile = File(...)):
    valid_id(request_id)
    if not userName.strip() or len(userName) > 80 or len(title) > 120:
        await audio.close()
        raise HTTPException(status_code=422, detail='Revisa el nombre y el título de la reunión.')
    extension = Path(audio.filename or '').suffix.lower()
    workspace = WORK_ROOT / request_id
    created = False
    try:
        try:
            return public_job(database.get_job(request_id))
        except database.NotFoundError:
            pass
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=415, detail=FORMAT_ERROR)
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        try:
            workspace.mkdir(exist_ok=False)
            created = True
        except FileExistsError:
            raise HTTPException(status_code=409, detail='Esta carga ya está en curso. Espera a que termine.')
        path = workspace / ('audio' + extension)
        size = 0
        with path.open('wb') as target:
            while data := await audio.read(1024*1024):
                size += len(data)
                if size > MAX_AUDIO_BYTES:
                    raise HTTPException(status_code=413, detail='El audio supera el límite de 100 MB.')
                target.write(data)
        if not size:
            raise HTTPException(status_code=400, detail='El archivo está vacío.')
        job = database.create_job(request_id, title.strip() or 'Reunión sin título', userName.strip(),
                                  (audio.filename or 'audio')[:255], str(path))
        if job['status'] != 'procesando':
            clean_workspace(request_id)
        else:
            try:
                start_worker(request_id)
            except OSError:
                database.update_job(request_id,'error',status='error',error='No se pudo iniciar el procesamiento.')
                clean_workspace(request_id)
                raise HTTPException(status_code=503, detail='No se pudo iniciar el procesamiento. Vuelve a intentarlo.')
        return public_job(database.get_job(request_id))
    except BaseException:
        if created:
            try:
                database.get_job(request_id)
            except database.NotFoundError:
                clean_workspace(request_id)
        raise
    finally:
        await audio.close()


@router.get('/{job_id}')
def get_job(job_id: str):
    valid_id(job_id)
    return public_job(database.get_job(job_id))


@router.post('/{job_id}/cancelar')
def cancel_job(job_id: str):
    valid_id(job_id)
    return cancel_worker(job_id)
