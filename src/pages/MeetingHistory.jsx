import { useEffect, useRef, useState } from "react";
import { ArrowRight, CalendarDays, History, Search, Trash2 } from "lucide-react";
import { EmptyState, PageHeading } from "../components/UI.jsx";
import DeleteMeetingDialog from "../components/DeleteMeetingDialog.jsx";
import { listMeetings } from "../services/api.js";

const labels = { pendiente: "Transcripción guardada", procesando: "Analizando", listo: "Resultados listos", error: "Análisis por reintentar", cancelado: "Análisis cancelado" };
export default function MeetingHistory({ onOpen, onDelete, version }) {
  const [input, setInput] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [data, setData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [notice, setNotice] = useState("");
  const deletingRef = useRef(false);
  async function confirmDelete() {
    if (deletingRef.current || !selected) return;
    deletingRef.current = true; setDeleting(true); setDeleteError("");
    const target = selected;
    try {
      await onDelete(target.id);
      setData(previous => ({ ...previous, total: Math.max(0, previous.total - 1), items: previous.items.filter(item => item.id !== target.id) }));
      setSelected(null); setNotice(`Se eliminó «${target.title}».`); setRefresh(value => value + 1);
    } catch (error) { setDeleteError(error.message); }
    finally { deletingRef.current = false; setDeleting(false); }
  }
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError("");
    listMeetings(query, offset, controller.signal).then(result => {
      if (controller.signal.aborted) return;
      if (offset > 0 && offset >= result.total) {
        setOffset(result.total ? Math.floor((result.total - 1) / 20) * 20 : 0); return;
      }
      setData(result);
    }).catch(error => {
      if (error.name !== "AbortError") setError(error.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [query, offset, refresh, version]);
  return <>
    <PageHeading eyebrow="HISTORIAL" title="Tus reuniones">Abre una reunión para consultar su resumen, tus pendientes y tus notas.</PageHeading>
    {notice && <p className="history-notice" role="status">{notice}</p>}
    <form className="history-search" role="search" onSubmit={event => { event.preventDefault(); setOffset(0); setQuery(input.trim()); setRefresh(value => value + 1); }}>
      <label className="sr-only" htmlFor="history-search">Buscar reuniones por título, nombre o archivo</label>
      <div className="search-input"><Search size={19} aria-hidden="true" /><input id="history-search" value={input} maxLength={120} onChange={event => setInput(event.target.value)} placeholder="Buscar por título, nombre o archivo" /></div>
      <button className="button secondary" type="submit">Buscar</button>
    </form>
    {!loading && !error && <div className="history-count"><p>{data.total} {data.total === 1 ? "reunión" : "reuniones"}{query ? (data.total === 1 ? " encontrada" : " encontradas") : (data.total === 1 ? " guardada" : " guardadas")}</p>{query && <button className="text-link" onClick={() => { setInput(""); setQuery(""); setOffset(0); }}>Limpiar búsqueda</button>}</div>}
    {loading && <p className="help" role="status">Cargando reuniones…</p>}
    {error && <div className="error-message" role="alert"><p>{error}</p><button className="button secondary" onClick={() => setRefresh(value => value + 1)}>Reintentar</button></div>}
    {!loading && !error && !data.items.length && <div className="card"><EmptyState icon={History} title={query ? "No encontramos esa reunión" : "Todavía no hay reuniones"}
      action={<a className="button primary" href="#/nueva">Subir una reunión</a>}><p>{query ? "Prueba con otro título, nombre o archivo." : "Las reuniones que proceses aparecerán aquí."}</p></EmptyState></div>}
    {!error && <div className="history-list">{data.items.map(item => <article className="card history-card" key={item.id}>
      <span className="history-date" aria-hidden="true"><CalendarDays size={20} /><strong>{new Date(item.created_at).getDate()}</strong><span>{new Date(item.created_at).toLocaleDateString("es-MX", { month: "short" })}</span></span><div className="history-info"><div className="history-title"><h2>{item.title}</h2><span className="badge">{labels[item.analysis_status]}</span></div>
        <p className="help">{new Date(item.created_at).toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" })} · {item.userName}</p>
        <p className="help file-name">{item.fileName}</p><p className="help">{item.task_count ? `${item.completed_count} de ${item.task_count} tareas completadas` : "Sin tareas asignadas"}</p></div>
      <div className="history-actions"><button className="button secondary" disabled={loading || deleting} onClick={() => onOpen(item.id)} aria-label={"Abrir resultados de " + item.title}>Abrir reunión<ArrowRight size={18} aria-hidden="true" /></button>
        <button type="button" className="button delete-history-button" disabled={loading || deleting} aria-label={"Eliminar reunión " + item.title}
          onClick={() => { setSelected(item); setDeleteError(""); setNotice(""); }}><Trash2 size={18} aria-hidden="true" />Eliminar</button></div>
    </article>)}</div>}
    {!error && data.total > 20 && <nav className="pagination" aria-label="Páginas del historial">
      <button className="button secondary" disabled={loading || offset === 0} onClick={() => setOffset(value => Math.max(0, value - 20))}>Anterior</button>
      <p className="help">Página {Math.floor(offset / 20) + 1} de {Math.ceil(data.total / 20)}</p>
      <button className="button secondary" disabled={loading || offset + 20 >= data.total} onClick={() => setOffset(value => value + 20)}>Siguiente</button>
    </nav>}
    {selected && <DeleteMeetingDialog meeting={selected} busy={deleting} error={deleteError} onCancel={() => { if (!deleting) setSelected(null); }} onConfirm={confirmDelete} />}
  </>;
}
