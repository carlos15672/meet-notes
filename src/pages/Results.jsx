import { useEffect, useId, useRef, useState } from "react";
import { Copy, FileText, ListTodo, RefreshCw, Sparkles } from "lucide-react";
import { EmptyState, PageHeading } from "../components/UI.jsx";
import ProposalCard from "../components/ProposalCard.jsx";
import TaskCard from "../components/TaskCard.jsx";

const sections = [
  { id: "summary", label: "Resumen", icon: Sparkles },
  { id: "tasks", label: "Mis pendientes", icon: ListTodo },
  { id: "transcript", label: "Transcripción", icon: FileText },
];
function timestamp(seconds) {
  const value = Math.floor(seconds);
  return String(Math.floor(value / 60)).padStart(2, "0") + ":" + String(value % 60).padStart(2, "0");
}
export default function Results({ meeting, loading, loadError, onRefresh, onRetry, noteDrafts, onNoteChange, onSaveTask, saveStates = {}, onResolve, onCancel }) {
  const [active, setActive] = useState(0);
  const [copyMessage, setCopyMessage] = useState("");
  const [retrying, setRetrying] = useState(false);
  const [actionError, setActionError] = useState("");
  const touched = useRef(false);
  const tabs = useRef([]);
  const textRef = useRef(null);
  const prefix = useId();
  const ready = meeting?.analysis_status === "listo";
  const analyzing = meeting?.analysis_status === "procesando";
  useEffect(() => {
    if (!touched.current) setActive(ready ? 0 : 2);
    setCopyMessage("");
  }, [meeting?.id, ready]);
  function choose(index) { touched.current = true; setActive(index); }
  function handleKey(event, index) {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % sections.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + sections.length) % sections.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = sections.length - 1;
    else return;
    event.preventDefault(); choose(next); tabs.current[next]?.focus();
  }
  async function copyText() {
    try { await navigator.clipboard.writeText(meeting.texto); setCopyMessage("Transcripción copiada."); }
    catch {
      textRef.current?.focus(); textRef.current?.select();
      setCopyMessage("Texto seleccionado. Haz clic derecho y elige Copiar.");
    }
  }
  async function action(callback) {
    if (retrying) return;
    setRetrying(true); setActionError("");
    try { await callback(); } catch (error) { setActionError(error.message); }
    finally { setRetrying(false); }
  }
  if (!meeting) return <>
    <PageHeading eyebrow="RESULTADOS" title="No hay una reunión abierta">Elige una reunión del historial o sube una grabación.</PageHeading>
    {loading ? <p role="status" className="integration-notice">Recuperando tu reunión…</p>
      : loadError ? <div className="error-message" role="alert"><p>{loadError}</p><button className="button secondary" disabled={retrying} onClick={() => action(onRefresh)}>Volver a intentar</button><a className="button secondary" href="#/historial">Abrir historial</a></div>
      : <div className="card"><EmptyState icon={FileText} title="Aún no hay una reunión seleccionada" action={<a href="#/nueva" className="button primary">Preparar una reunión</a>}><p>Procesa una grabación o abre una reunión desde el historial.</p></EmptyState></div>}
    {actionError && <p className="error-message" role="alert">{actionError}</p>}
  </>;

  return <>
    <PageHeading eyebrow="RESULTADOS DE LA REUNIÓN" title={meeting.title}>
      {new Date(meeting.created_at).toLocaleDateString("es-MX", { day: "numeric", month: "long", year: "numeric" })}
      {" · "}{Math.ceil(meeting.duracion_segundos / 60)} min{" · Pendientes para "}{meeting.userName}
    </PageHeading>
    <div className="meeting-saved">
      <span className="saved-label"><span aria-hidden="true" />Guardada en el historial</span>
      <span className="help file-name">{meeting.fileName}</span>
      <a className="text-link" href="#/historial">Ver historial</a>
    </div>
    {(loadError || actionError) && <div className="error-message" role="alert"><p>{loadError || actionError}</p><button className="button secondary" disabled={retrying} onClick={() => action(onRefresh)}>Actualizar resultados</button></div>}
    {analyzing && <div className="analysis-progress" role="status">
      <Sparkles size={20} aria-hidden="true" /><div><p>Analizando la conversación…</p>
        <p className="help">Estamos preparando el resumen y tus tareas. Puedes consultar la transcripción mientras tanto.</p>
        <progress value={meeting.progress} max={100} aria-label="Avance del análisis" /><button className="button secondary" disabled={retrying} onClick={() => action(() => onCancel(meeting.id))}>Cancelar análisis</button></div>
    </div>}
    {!ready && !analyzing && <div className={meeting.analysis_status === "error" ? "error-message analysis-retry" : "analysis-retry card"}>
      <p>{meeting.analysis_error || "La transcripción está lista. Falta generar el resumen y tus tareas."}</p>
      <button className="button secondary" disabled={retrying} onClick={() => action(() => onRetry(meeting.id))}>
        <RefreshCw size={18} aria-hidden="true" />{retrying ? "Preparando…" : meeting.analysis_status === "error" ? "Reintentar análisis" : "Generar resumen y pendientes"}</button>
    </div>}
    <section className="card results-card" aria-label="Resultados de la reunión">
      <div className="tabs" role="tablist" aria-label="Secciones de resultados">
        {sections.map(({ id, label, icon: Icon }, index) => <button key={id} ref={element => { tabs.current[index] = element; }}
          id={prefix + "-tab-" + id} type="button" role="tab" tabIndex={active === index ? 0 : -1}
          aria-selected={active === index} aria-controls={prefix + "-panel-" + id}
          onClick={() => choose(index)} onKeyDown={event => handleKey(event, index)}>
          <Icon size={19} aria-hidden="true" /><span>{id === "tasks" && ready ? `${label} (${meeting.pendientes.length})` : label}</span></button>)}
      </div>
      {sections.map(({ id, icon }, index) => <div key={id} id={prefix + "-panel-" + id} role="tabpanel"
        aria-labelledby={prefix + "-tab-" + id} hidden={active !== index} tabIndex={0} className="result-panel">
        {id === "transcript" ? <div className="transcript-content">
          <div className="transcript-heading"><div><h2>Transcripción completa</h2><p className="help file-name">Duración: {timestamp(meeting.duracion_segundos)}</p></div>
            <div className="transcript-actions">
            <button type="button" className="button secondary" onClick={copyText}><Copy size={18} aria-hidden="true" />Copiar texto</button></div></div>
          <label htmlFor={prefix + "-text"} className="sr-only">Texto completo de la transcripción</label>
          <textarea id={prefix + "-text"} className="transcript-text" ref={textRef} value={meeting.texto} readOnly rows={8} />
          <p className="help" role="status" aria-live="polite">{copyMessage}</p>
          {meeting.segmentos.length > 0 && <details className="transcript-segments"><summary>Ver fragmentos con su hora</summary>
            <ol>{meeting.segmentos.map((segment, i) => <li key={i}><span className="segment-time">{timestamp(segment.inicio)} - {timestamp(segment.fin)}</span><p>{segment.texto}</p></li>)}</ol>
          </details>}
        </div> : !ready ? <EmptyState icon={icon} title={analyzing ? "Estamos analizando tu reunión" : "El análisis todavía no está listo"}><p>{analyzing ? "El resultado aparecerá aquí cuando termine. Mientras tanto puedes consultar la transcripción." : "Usa el botón de análisis que aparece arriba para continuar."}</p></EmptyState>
        : id === "summary" ? <div className="summary-content">
          <section className="summary-section"><h2>Resumen general</h2><p className="overview-text">{meeting.resumen_general || "Esta reunión se procesó con una versión anterior. Sus temas y acuerdos están disponibles abajo."}</p></section>
          {meeting.proximas_reuniones?.length > 0 && <section className="summary-section"><h2>Próxima reunión</h2><ul>{meeting.proximas_reuniones.map((text, i) => <li key={i}>{text}</li>)}</ul></section>}
          {[["temas", "Temas tratados"], ["acuerdos", "Acuerdos"]].map(([key, label]) => <section key={key} className="summary-section"><h2>{label}</h2>
            {meeting.resumen[key].length ? <ul>{meeting.resumen[key].map((text, i) => <li key={i}>{text}
              {meeting.evidencias_resumen?.[key]?.[i] && meeting.evidencias_resumen[key][i] !== text &&
                <details className="task-evidence"><summary>Ver evidencia</summary><blockquote>{meeting.evidencias_resumen[key][i]}</blockquote></details>}
            </li>)}</ul> : <p className="muted">{({ temas: "No se pudieron identificar los temas de esta reunión.", acuerdos: "No se encontraron acuerdos explícitos." })[key]}</p>}
          </section>)}
        </div> : <div className="tasks-content">
          <div className="transcript-heading"><div><h2>Mis pendientes</h2><p className="help">Para {meeting.userName}{meeting.pendientes.length > 0 && <> · {meeting.pendientes.filter(task => task.estado === "completado").length} de {meeting.pendientes.length} tareas completadas</>}</p></div></div>
          {meeting.advertencias.map((warning, i) => <p className="help" key={i}>{warning}</p>)}
          {meeting.pendientes.length ? meeting.pendientes.map(task => <TaskCard key={task.id} task={task} draft={noteDrafts[task.id]} saveState={saveStates[task.id]} onChange={onNoteChange} onSave={onSaveTask} />)
            : <EmptyState icon={ListTodo} title={"No hay tareas para " + meeting.userName}><p>No encontramos tareas asignadas a ese nombre. Revisa que coincida con el que se usa en el audio.</p></EmptyState>}
          {meeting.por_confirmar?.length > 0 && <section className="proposals-section" aria-labelledby={prefix + "-review"}>
            <h2 id={prefix + "-review"}>Por confirmar ({meeting.por_confirmar.length})</h2><p className="help">Estas propuestas todavía no cuentan como tus tareas. Revisa la cita antes de confirmarlas.</p>
            {meeting.por_confirmar.map(proposal => <ProposalCard key={proposal.id} proposal={proposal} onResolve={onResolve} />)}
          </section>}
        </div>}
      </div>)}
    </section>
    {active === 1 && meeting.pendientes.length > 0 && <p className="session-note">Las notas y los estados se guardan automáticamente. Si aparece un error, tu borrador se conserva para reintentarlo.</p>}
  </>;
}
