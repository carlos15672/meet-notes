"""SQLite persistence; every write is transactional and uses bound parameters."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from config import DB_PATH
from task_matching import same_task


class NotFoundError(LookupError):
    pass


class ConflictError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def initialize():
    with connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS meetings (
                id TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL, user_name TEXT NOT NULL, file_name TEXT NOT NULL,
                transcription TEXT NOT NULL, analysis TEXT,
                analysis_status TEXT NOT NULL DEFAULT 'pendiente',
                analysis_error TEXT NOT NULL DEFAULT '', progress INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                descripcion TEXT NOT NULL, responsable TEXT NOT NULL,
                fecha_limite TEXT, evidencia TEXT NOT NULL, inicio REAL, fin REAL,
                nota TEXT NOT NULL DEFAULT '', estado TEXT NOT NULL DEFAULT 'pendiente'
                    CHECK (estado IN ('pendiente','en_curso','completado')),
                version INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS meetings_created ON meetings(created_at DESC);
            CREATE INDEX IF NOT EXISTS tasks_meeting ON tasks(meeting_id);
        """)
        for table, columns in {
            "meetings": {"analysis_token": "TEXT NOT NULL DEFAULT ''"},
            "tasks": {"evidencias": "TEXT NOT NULL DEFAULT '[]'", "origen": "TEXT NOT NULL DEFAULT 'ia'"}
        }.items():
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS proposals (
                id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                descripcion TEXT NOT NULL, responsable TEXT, fecha_limite TEXT,
                evidencia TEXT NOT NULL, inicio REAL, fin REAL, motivo TEXT NOT NULL,
                opciones TEXT NOT NULL DEFAULT '[]', estado TEXT NOT NULL DEFAULT 'pendiente',
                version INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', user_name TEXT NOT NULL DEFAULT '',
                file_name TEXT NOT NULL DEFAULT '', input_path TEXT NOT NULL DEFAULT '',
                meeting_id TEXT, status TEXT NOT NULL, stage TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_sessions (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, user_name TEXT NOT NULL,
                status TEXT NOT NULL, duration REAL NOT NULL DEFAULT 0,
                segments TEXT NOT NULL DEFAULT '[]', error TEXT NOT NULL DEFAULT '',
                meeting_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS live_marks (
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES live_sessions(id) ON DELETE CASCADE,
                second REAL NOT NULL, created_at TEXT NOT NULL
            );
        """)


def recover_interrupted():
    with connection() as conn:
        conn.execute("""UPDATE meetings SET analysis_status='error', analysis_error=?,
                        updated_at=? WHERE analysis_status='procesando'""",
                     ("El servidor se reinició durante el análisis. Puedes reintentarlo sin subir el audio.", now()))


def create_meeting(data):
    stamp, meeting_id = now(), str(uuid4())
    transcription = json.dumps(data["transcription"], ensure_ascii=False)
    with connection() as conn:
        conn.execute("""INSERT INTO meetings
            (id,request_id,title,user_name,file_name,transcription,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(request_id) DO NOTHING""", (meeting_id, data["request_id"],
            data["title"].strip() or "Reunión sin título", data["userName"],
            data["fileName"], transcription, stamp, stamp))
        meeting_id = conn.execute("SELECT id FROM meetings WHERE request_id=?", (data["request_id"],)).fetchone()["id"]
    return get_meeting(meeting_id)


def get_meeting(meeting_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            raise NotFoundError("No se encontró la reunión.")
        tasks = conn.execute("SELECT * FROM tasks WHERE meeting_id=? ORDER BY rowid", (meeting_id,)).fetchall()
        proposals = conn.execute("SELECT * FROM proposals WHERE meeting_id=? AND estado='pendiente' ORDER BY rowid", (meeting_id,)).fetchall()
    analysis = json.loads(row["analysis"]) if row["analysis"] else {}
    general = analysis.get("resumen_general", "")
    if not general and analysis:
        from analysis_service import overview, normalized
        source = normalized(json.loads(row["transcription"])["texto"])
        evidence = {category: [quote for quote in quotes if normalized(quote) in source]
                    for category, quotes in analysis.get("evidencias_resumen", {}).items()}
        safe_agreements = [quote for quote in (analysis.get("resumen") or {}).get("acuerdos", []) if normalized(quote) in source]
        general = overview({"acuerdos": safe_agreements}, evidence)
    return {**json.loads(row["transcription"]), "id": row["id"], "title": row["title"],
            "userName": row["user_name"], "fileName": row["file_name"],
            "created_at": row["created_at"], "updated_at": row["updated_at"],
            "analysis_status": row["analysis_status"], "analysis_token": row["analysis_token"], "analysis_error": row["analysis_error"],
            "progress": row["progress"], "resumen": analysis.get("resumen"),
            "evidencias_resumen": analysis.get("evidencias_resumen", {}),
            "analysis_model": analysis.get("modelo"), "advertencias": analysis.get("advertencias", []),
            "resumen_general": general, "proximas_reuniones": analysis.get("proximas_reuniones", []),
            "por_confirmar": [{**dict(p), "opciones": json.loads(p["opciones"])} for p in proposals],
            "pendientes": [task_dict(task) for task in tasks]}


def list_meetings(query="", offset=0, limit=20):
    # instr treats search input literally, including percent signs and SQL quotes.
    where = "WHERE instr(lower(m.title || ' ' || m.user_name || ' ' || m.file_name), lower(?)) > 0"
    with connection() as conn:
        total = conn.execute(f"SELECT count(*) FROM meetings m {where}", (query,)).fetchone()[0]
        rows = conn.execute(f"""SELECT m.id,m.title,m.user_name AS userName,m.file_name AS fileName,
            m.created_at,m.analysis_status,m.analysis_error,
            (SELECT count(*) FROM tasks t WHERE t.meeting_id=m.id) AS task_count,
            (SELECT count(*) FROM tasks t WHERE t.meeting_id=m.id AND t.estado='completado') AS completed_count
            FROM meetings m {where} ORDER BY m.created_at DESC,m.id DESC LIMIT ? OFFSET ?""",
            (query, limit, offset)).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "offset": offset, "limit": limit}


def delete_meeting(meeting_id):
    """Delete one meeting and its contents atomically; never delete active work."""
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT analysis_status,request_id FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            raise NotFoundError("Esta reunión ya no está en el historial.")
        active_job = conn.execute("SELECT 1 FROM jobs WHERE status='procesando' AND (meeting_id=? OR id=?)", (meeting_id, row["request_id"])).fetchone()
        if row["analysis_status"] == "procesando" or active_job:
            raise ConflictError("La reunión se está procesando. Cancela el procesamiento antes de eliminarla.")
        conn.execute("DELETE FROM proposals WHERE meeting_id=?", (meeting_id,))
        conn.execute("DELETE FROM tasks WHERE meeting_id=?", (meeting_id,))
        # Retain an anonymous terminal job token so an outstanding poll can finish.
        conn.execute("""UPDATE jobs SET meeting_id=NULL,title='',user_name='',file_name='',input_path='',updated_at=?
                        WHERE meeting_id=?""", (now(), meeting_id))
        conn.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
    return {"id": meeting_id, "eliminada": True}


def claim_analysis(meeting_id):
    with connection() as conn:
        result = conn.execute("""UPDATE meetings SET analysis_status='procesando',analysis_error='',
            progress=0,updated_at=?,analysis_token=? WHERE id=? AND analysis_status IN ('pendiente','error','cancelado')""", (now(), str(uuid4()), meeting_id))
        if not result.rowcount:
            get_meeting(meeting_id)
            return False
    return True


def analysis_progress(meeting_id, value, token=None):
    with connection() as conn:
        conn.execute("UPDATE meetings SET progress=? WHERE id=? AND analysis_status='procesando' AND (? IS NULL OR analysis_token=?)", (value, meeting_id, token, token))


def fail_analysis(meeting_id, message, token=None):
    with connection() as conn:
        conn.execute("UPDATE meetings SET analysis_status='error',analysis_error=?,updated_at=? WHERE id=? AND (? IS NULL OR (analysis_token=? AND analysis_status='procesando'))",
                     (message, now(), meeting_id, token, token))


def finish_analysis(meeting_id, analysis, token=None):
    # Reanalysis cannot erase personal notes or replace an already completed analysis.
    stamp = now()
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT analysis_status,analysis_token FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        if not row:
            raise NotFoundError("No se encontró la reunión.")
        if token is not None and (row["analysis_status"] != "procesando" or row["analysis_token"] != token):
            return
        if row["analysis_status"] == "listo":
            return
        for task in analysis["pendientes"]:
            conn.execute("""INSERT INTO tasks
                (id,meeting_id,descripcion,responsable,fecha_limite,evidencia,inicio,fin,updated_at,evidencias)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (str(uuid4()), meeting_id, task["descripcion"], task["responsable"],
                task["fecha_limite"], task["evidencia"], task.get("inicio"), task.get("fin"), stamp, json.dumps(task.get("evidencias", []), ensure_ascii=False)))
        for proposal in analysis.get("por_confirmar", []):
            conn.execute("""INSERT INTO proposals (id,meeting_id,descripcion,responsable,fecha_limite,evidencia,inicio,fin,motivo,opciones)
                            VALUES (?,?,?,?,?,?,?,?,?,?)""", (str(uuid4()), meeting_id, proposal["descripcion"], proposal.get("responsable"),
                proposal.get("fecha_limite"), proposal["evidencia"], proposal.get("inicio"), proposal.get("fin"),
                proposal["motivo"], json.dumps(proposal.get("opciones", []), ensure_ascii=False)))
        stored = {key: value for key, value in analysis.items() if key not in ("pendientes", "por_confirmar")}
        conn.execute("""UPDATE meetings SET analysis=?,analysis_status='listo',analysis_error='',
                        progress=100,updated_at=? WHERE id=?""",
                     (json.dumps(stored, ensure_ascii=False), stamp, meeting_id))


def update_task(meeting_id, task_id, change):
    with connection() as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id=? AND meeting_id=?", (task_id, meeting_id)).fetchone()
        if not row:
            raise NotFoundError("No se encontró el pendiente de esta reunión.")
        note = row["nota"] if change.get("nota") is None else change["nota"]
        status = row["estado"] if change.get("estado") is None else change["estado"]
        result = conn.execute("""UPDATE tasks SET nota=?,estado=?,version=version+1,updated_at=?
            WHERE id=? AND meeting_id=? AND version=?""", (note, status, now(), task_id, meeting_id, change["version"]))
        if not result.rowcount:
            raise ConflictError("Este pendiente cambió en otra pestaña. Actualiza los resultados antes de guardar; tu nota se conserva.")
        updated = task_dict(conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
    return updated


def task_dict(row):
    return {**dict(row), "evidencias": json.loads(row["evidencias"])}


def cancel_analysis(meeting_id, token=None):
    with connection() as conn:
        conn.execute("""UPDATE meetings SET analysis_status='cancelado',analysis_token=?,analysis_error=?,updated_at=?
                        WHERE id=? AND analysis_status='procesando' AND (? IS NULL OR analysis_token=?)""",
                     (str(uuid4()), "Cancelaste el análisis. La transcripción sigue guardada.", now(), meeting_id, token, token))
    return get_meeting(meeting_id)


def analysis_cancelled(meeting_id, token):
    with connection() as conn:
        row = conn.execute("SELECT analysis_token,analysis_status FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    return not row or row["analysis_token"] != token or row["analysis_status"] != "procesando"


def resolve_proposal(meeting_id, proposal_id, data):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM proposals WHERE id=? AND meeting_id=?", (proposal_id, meeting_id)).fetchone()
        if not row:
            raise NotFoundError("No se encontró la tarea por confirmar.")
        if row["estado"] != 'pendiente' or row["version"] != data["version"]:
            raise ConflictError("Esta propuesta ya cambió. Actualiza los resultados.")
        if data["decision"] == 'confirmar':
            user = conn.execute("SELECT user_name FROM meetings WHERE id=?", (meeting_id,)).fetchone()[0]
            options = json.loads(row["opciones"])
            owner = (data.get("responsable") or user).strip()
            if owner not in (options or [user]):
                raise ConflictError("Elige tu nombre entre las personas indicadas antes de confirmar.")
            candidate = {**dict(row), "responsable": owner}
            existing = conn.execute("SELECT * FROM tasks WHERE meeting_id=?", (meeting_id,)).fetchall()
            match = next((task for task in existing if same_task(dict(task), candidate)), None)
            quote = {"texto": row["evidencia"], "inicio": row["inicio"], "fin": row["fin"]}
            if match:
                quotes = json.loads(match["evidencias"])
                if quote not in quotes:
                    quotes.append(quote)
                conn.execute("UPDATE tasks SET evidencias=?,origen='usuario',version=version+1,updated_at=? WHERE id=?",
                             (json.dumps(quotes, ensure_ascii=False), now(), match["id"]))
            else:
                conn.execute("""INSERT INTO tasks (id,meeting_id,descripcion,responsable,fecha_limite,evidencia,inicio,fin,updated_at,evidencias,origen)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (str(uuid4()), meeting_id, row["descripcion"], owner, row["fecha_limite"],
                    row["evidencia"], row["inicio"], row["fin"], now(), json.dumps([quote], ensure_ascii=False), 'usuario'))
        conn.execute("UPDATE proposals SET estado=?,version=version+1 WHERE id=?", (data["decision"], proposal_id))
    return get_meeting(meeting_id)


def create_job(job_id, title='', user_name='', file_name='', input_path='', status='procesando'):
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if status == 'procesando' and conn.execute("SELECT 1 FROM jobs WHERE status='procesando' AND id!=?", (job_id,)).fetchone():
            raise ConflictError("Ya se está procesando una reunión. Espera a que termine o cancélala primero.")
        conn.execute("""INSERT INTO jobs (id,title,user_name,file_name,input_path,status,stage,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING""",
            (job_id,title,user_name,file_name,input_path,status,'recibido',now(),now()))
    return get_job(job_id)


def get_job(job_id):
    with connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise NotFoundError("No se encontró el procesamiento.")
    return dict(row)


def update_job(job_id, stage, status='procesando', meeting_id=None, error=''):
    with connection() as conn:
        conn.execute("""UPDATE jobs SET stage=?,status=?,meeting_id=coalesce(?,meeting_id),error=?,updated_at=?
                        WHERE id=? AND status='procesando'""", (stage,status,meeting_id,error,now(),job_id))


def cancel_job(job_id):
    job = create_job(job_id, status='cancelado')
    with connection() as conn:
        conn.execute("UPDATE jobs SET status='cancelado',stage='cancelado',updated_at=? WHERE id=? AND status='procesando'", (now(),job_id))
    if job['meeting_id'] and job['status'] == 'procesando':
        cancel_analysis(job['meeting_id'])
    return get_job(job_id)


def recover_jobs():
    with connection() as conn:
        conn.execute("""UPDATE jobs SET status='error',error=?,updated_at=? WHERE status='procesando'""",
                     ("El servidor se reinició. Puedes volver a intentar el procesamiento.",now()))


def recover_live_sessions():
    with connection() as conn:
        conn.execute("""UPDATE live_sessions SET status='interrumpida',error=?,updated_at=?
            WHERE status IN ('capturando','pausada','finalizando','analizando')""",
            ("La aplicación se reinició. La captura guardada puede finalizarse.", now()))
