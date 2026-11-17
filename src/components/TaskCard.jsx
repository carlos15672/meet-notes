import { useId } from "react";
import { Save } from "lucide-react";

export default function TaskCard({ task, draft, saveState = {}, onChange, onSave }) {
  const prefix = useId();
  const note = draft ?? task.nota;
  const conflict = saveState.status === "conflicto";
  const saving = saveState.status === "guardando";
  const statusLabels = { pendiente: "Pendiente", en_curso: "En curso", completado: "Completado" };
  const labels = { pendiente: "Cambios sin guardar", guardando: "Guardando…", guardado: "Guardado", error: "No se pudo guardar", conflicto: "Hay otra versión guardada" };
  const quotes = task.evidencias?.length ? task.evidencias : [{ texto: task.evidencia, inicio: task.inicio, fin: task.fin }];
  return <article className={"task-card" + (task.estado === "completado" ? " task-complete" : "")}>
    <div className="task-heading"><h3>{task.descripcion}</h3><span className="badge">{task.fecha_limite || "Sin fecha"}</span></div>
    <p className="help">Responsable: {task.responsable}{task.origen === "usuario" && " · Confirmada por ti"}</p>
    <div className="task-status"><label htmlFor={prefix + "-status"}>Estado</label>
      <select id={prefix + "-status"} value={task.estado} disabled={saving || conflict} onChange={event => onSave(task, { estado: event.target.value })}>
        <option value="pendiente">Pendiente</option><option value="en_curso">En curso</option><option value="completado">Completado</option>
      </select></div>
    <details className="task-evidence"><summary>Ver dónde se asignó{quotes.length > 1 ? ` (${quotes.length} menciones)` : ""}</summary>
      {quotes.map((quote, i) => <div key={i}><blockquote>{quote.texto}</blockquote>
        {quote.inicio != null && <p className="help">Del segundo {quote.inicio} al {quote.fin}.</p>}</div>)}
    </details>
    <div className="task-note"><label htmlFor={prefix + "-note"}>Mis notas</label>
      <p id={prefix + "-help"} className="help">Se guardan automáticamente al dejar de escribir.</p>
      <textarea id={prefix + "-note"} rows={3} value={note} maxLength={10000} aria-describedby={prefix + "-help"}
        onChange={event => onChange(task, event.target.value)} placeholder="Ej. Incluir los cambios que revisamos el lunes." />
      {conflict && <details className="task-evidence"><summary>Ver la nota guardada</summary><blockquote>{saveState.remoteNote || "La nota guardada está vacía."}</blockquote><p className="help">Estado guardado: {statusLabels[saveState.remoteState] || task.estado}. Tu cambio: {statusLabels[saveState.desiredState] || task.estado}.</p></details>}
      <div className="note-actions"><button type="button" className="button secondary" disabled={saving || (!conflict && note === task.nota && saveState.status !== "error")} onClick={() => onSave(task, { nota: note }, conflict)}>
        <Save size={18} aria-hidden="true" />{conflict ? "Reemplazar con mis cambios" : saveState.status === "error" ? "Reintentar guardado" : "Guardar ahora"}</button>
        <p className="help" role="status" aria-live="polite">{labels[saveState.status] || "Guardado"}</p></div>
      {saveState.error && <p className="error-message" role="alert">{saveState.error}</p>}
    </div>
  </article>;
}
