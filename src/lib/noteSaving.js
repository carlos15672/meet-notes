const STORAGE_KEY = "meet-notes-note-drafts-v1";

export function createNoteSaver({ save, onSaved = () => {}, onState = () => {}, onDraft = () => {}, storage, delay = 800 }) {
  let persisted = {};
  try { persisted = JSON.parse(storage?.getItem(STORAGE_KEY) || "{}"); if (!persisted || typeof persisted !== "object" || Array.isArray(persisted)) persisted = {}; } catch { persisted = {}; }
  const entries = new Map();
  function dirty(e) { return e.note !== e.task.nota || e.state !== e.task.estado; }
  function notify(e, status, error = "") { e.status = status; onState(e.task.id, { status, error, remoteNote: e.task.nota, remoteState: e.task.estado, desiredState: e.state }); }
  function persist(e) {
    if (e.note !== e.task.nota) {
      persisted[e.task.id] = { nota: e.note, base_note: e.task.nota, meeting_id: e.task.meeting_id };
      onDraft(e.task.id, e.note);
    } else { delete persisted[e.task.id]; onDraft(e.task.id, undefined); }
    try { storage?.setItem(STORAGE_KEY, JSON.stringify(persisted)); }
    catch { onState(e.task.id, { status: e.status, error: "No se pudo guardar el borrador en el navegador. Mantén la página abierta hasta que se guarde la nota." }); }
  }
  function schedule(e, wait = delay) {
    clearTimeout(e.timer);
    if (e.blocked || e.running || !dirty(e)) return;
    notify(e, "pendiente");
    e.timer = setTimeout(() => { e.timer = null; void flush(e.task.id); }, wait);
  }
  function sync(tasks) {
    for (const task of tasks) {
      let e = entries.get(task.id);
      if (!e) {
        e = { task, note: task.nota, state: task.estado, status: "guardado", timer: null, running: null, blocked: false };
        entries.set(task.id, e);
        const draft = persisted[task.id];
        if (draft && typeof draft.nota === "string" && draft.meeting_id === task.meeting_id) {
          e.note = draft.nota;
          e.blocked = e.note !== task.nota && draft.base_note !== task.nota;
        }
        persist(e);
        if (e.blocked) notify(e, "conflicto", "La nota guardada cambió. Revisa ambas versiones antes de reemplazarla.");
        else if (dirty(e)) schedule(e);
      } else if (!e.running && task.version >= e.task.version) {
        const changedNote = task.nota !== e.task.nota;
        const hadNote = e.note !== e.task.nota;
        const stateConflict = e.state !== e.task.estado && task.estado !== e.task.estado && e.state !== task.estado;
        if (!hadNote) e.note = task.nota;
        if (e.state === e.task.estado) e.state = task.estado;
        e.task = task;
        if ((changedNote && hadNote && e.note !== task.nota) || stateConflict) {
          e.blocked = true;
          clearTimeout(e.timer);
          notify(e, "conflicto", "La nota cambió en otra pestaña. Tu borrador se conserva.");
        }
        persist(e);
        if (!e.blocked && dirty(e)) schedule(e);
      }
    }
  }
  function get(task) { if (!entries.has(task.id)) sync([task]); return entries.get(task.id); }
  function change(task, note) {
    const e = get(task); e.note = note; persist(e);
    if (!e.blocked) { if (dirty(e)) schedule(e); else notify(e, "guardado"); }
  }
  async function flush(id) {
    const e = entries.get(id);
    if (!e) return;
    clearTimeout(e.timer); e.timer = null;
    if (e.running) return e.running;
    if (e.blocked || !dirty(e)) return;
    const fields = { version: e.task.version };
    if (e.note !== e.task.nota) fields.nota = e.note;
    if (e.state !== e.task.estado) fields.estado = e.state;
    notify(e, "guardando");
    e.running = (async () => {
      try {
        const result = await save(e.task, fields);
        if (e.deleted) return result;
        e.task = result;
        persist(e);
        onSaved(result);
        notify(e, dirty(e) ? "pendiente" : "guardado");
        return result;
      } catch (error) {
        if (e.deleted) return;
        e.blocked = true;
        notify(e, error.status === 409 ? "conflicto" : "error", error.message);
      } finally {
        e.running = null;
        if (!e.deleted && !e.blocked && dirty(e)) schedule(e, 0);
      }
    })();
    return e.running;
  }
  async function saveFields(task, fields, overwrite = false) {
    const e = get(task);
    if (fields.nota !== undefined) e.note = fields.nota;
    if (fields.estado !== undefined) e.state = fields.estado;
    persist(e);
    if (e.status === "conflicto" && !overwrite) return;
    e.blocked = false;
    return flush(task.id);
  }
  function dispose() { for (const e of entries.values()) clearTimeout(e.timer); }
  function discardMeeting(meetingId) {
    const removed = new Set();
    for (const [id, e] of entries) {
      if (e.task.meeting_id !== meetingId) continue;
      e.deleted = true; e.blocked = true; clearTimeout(e.timer);
      entries.delete(id); removed.add(id); onDraft(id, undefined);
    }
    for (const [id, draft] of Object.entries(persisted)) {
      if (draft.meeting_id === meetingId) { delete persisted[id]; removed.add(id); onDraft(id, undefined); }
    }
    try { storage?.setItem(STORAGE_KEY, JSON.stringify(persisted)); } catch { /* Storage may be unavailable. */ }
    return removed;
  }
  return { sync, change, saveFields, flush, dispose, discardMeeting, hasPending: () => [...entries.values()].some(dirty) };
}
