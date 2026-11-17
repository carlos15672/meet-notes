import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ChevronRight, HardDrive, History, LayoutList, NotebookPen, Plus } from "lucide-react";
import { EmptyState } from "./components/UI.jsx";
import NewMeeting from "./pages/NewMeeting.jsx";
import Results from "./pages/Results.jsx";
import MeetingHistory from "./pages/MeetingHistory.jsx";
import { analyzeMeeting, createReviewedMeeting, getMeeting, deleteMeeting, updateTask, startJob, getJob, cancelJob, cancelAnalysis, resolveProposal } from "./services/api.js";

import { createNoteSaver } from "./lib/noteSaving.js";
import { prepareTranscriptReview } from "./lib/transcriptReview.js";

const navigation = [
  { path: "/nueva", label: "Nueva reunión", icon: Plus },
  { path: "/resultados", label: "Resultados", icon: LayoutList },
  { path: "/historial", label: "Historial", icon: History },
];
function readStorage(key) { try { return localStorage.getItem(key) || ""; } catch { return ""; } }
function writeStorage(key, value) { try { localStorage.setItem(key, value); } catch { /* SQLite remains authoritative. */ } }
function readRoute() { return window.location.hash.slice(1) || "/nueva"; }

export default function App() {
  const [route, setRoute] = useState(readRoute);
  const [draft, setDraft] = useState(() => ({ name: readStorage("notas-user-name"), title: "", file: null }));
  const [meeting, setMeeting] = useState(null);
  const [selectedId, setSelectedId] = useState(() => readStorage("notas-meeting-id"));
  const [processing, setProcessing] = useState({ status: "idle", error: "", phase: "" });
  const [loadError, setLoadError] = useState("");
  const [loading, setLoading] = useState(false);
  const [noteDrafts, setNoteDrafts] = useState({});
  const [historyVersion, setHistoryVersion] = useState(0);
  const mainRef = useRef(null);
  const previousRoute = useRef(route);
  const busy = useRef(false);
  const activeJob = useRef("");
  const uploadController = useRef(null);
  const cancelRequested = useRef(false);
  const [saveStates, setSaveStates] = useState({});
  const noteSaver = useRef(null);
  if (!noteSaver.current) {
    let storage; try { storage = window.localStorage; } catch { /* Saving to SQLite still works. */ }
    noteSaver.current = createNoteSaver({ storage,
      save: (task, fields) => updateTask(task.meeting_id, task.id, fields),
      onDraft: (id, value) => setNoteDrafts(previous => {
        if (previous[id] === value) return previous;
        const next = { ...previous }; if (value === undefined) delete next[id]; else next[id] = value; return next;
      }),
      onState: (id, state) => setSaveStates(previous => ({ ...previous, [id]: state })),
      onSaved: saved => {
        setMeeting(previous => previous?.id === saved.meeting_id ? { ...previous, pendientes: previous.pendientes.map(t => t.id === saved.id ? saved : t) } : previous);
        setHistoryVersion(value => value + 1);
      }
    });
  }
  const deletedMeetings = useRef(new Set());
  const current = navigation.find(item => item.path === route);

  useEffect(() => {
    const update = () => setRoute(readRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  useEffect(() => {
    document.title = (current?.label || "Página no encontrada") + " · meet-notes";
    if (previousRoute.current !== route) { mainRef.current?.focus(); previousRoute.current = route; }
  }, [route, current?.label]);
  useEffect(() => {
    if (!selectedId || meeting?.id === selectedId) return;
    const controller = new AbortController();
    setLoading(true); setLoadError("");
    getMeeting(selectedId, controller.signal).then(saved => { if (!controller.signal.aborted && !deletedMeetings.current.has(saved.id)) setMeeting(saved); }).catch(error => {
      if (error.name !== "AbortError") setLoadError(error.message);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [selectedId]);
  useEffect(() => {
    if (!meeting || meeting.analysis_status !== "procesando") return;
    const controller = new AbortController(); let timer;
    async function poll() {
      try {
        const updated = await getMeeting(meeting.id, controller.signal);
        if (controller.signal.aborted) return;
        setLoadError("");
        setMeeting(previous => previous?.id === updated.id ? updated : previous);
        if (updated.analysis_status !== "procesando") { setHistoryVersion(value => value + 1); return; }
      } catch (error) {
        if (error.name === "AbortError") return;
        setLoadError("No se pudo actualizar el avance. Seguiremos intentando; tus datos guardados se conservan.");
      }
      if (!controller.signal.aborted) timer = window.setTimeout(poll, 2500);
    }
    timer = window.setTimeout(poll, 1500);
    return () => { controller.abort(); window.clearTimeout(timer); };
  }, [meeting?.id, meeting?.analysis_status]);
  useEffect(() => {
    if (!Object.keys(noteDrafts).length && !noteSaver.current.hasPending()) return;
    const warn = event => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [noteDrafts, saveStates]);
  useEffect(() => { if (meeting) noteSaver.current.sync(meeting.pendientes); }, [meeting?.pendientes]);
  useEffect(() => () => noteSaver.current.dispose(), []);
  const conflicts = Object.entries(saveStates).filter(([, value]) => value.status === "conflicto").map(([id]) => id).join(",");
  useEffect(() => {
    if (!conflicts || !meeting) return;
    getMeeting(meeting.id).then(saved => { if (deletedMeetings.current.has(saved.id)) return; noteSaver.current.sync(saved.pendientes); setMeeting(old => old?.id === saved.id ? saved : old); }).catch(() => {});
  }, [conflicts, meeting?.id]);
  useEffect(() => {
    const id = readStorage("meet-notes-active-job");
    if (id && !busy.current) { busy.current = true; activeJob.current = id; void monitorJob(id).finally(() => { busy.current = false; }); }
  }, []);

  function updateDraft(field, value) {
    setDraft(previous => ({ ...previous, [field]: value }));
    if (field === "name") writeStorage("notas-user-name", value);

    if (processing.status !== "processing") setProcessing({ status: "idle", error: "", phase: "" });
  }
  async function retryAnalysis(id) {
    try {
      const updated = await analyzeMeeting(id);
      setMeeting(previous => previous?.id === id ? updated : previous);
    } catch (error) {
      try { const saved = await getMeeting(id); setMeeting(previous => previous?.id === id ? saved : previous); } catch { /* Keep the visible meeting. */ }
      throw error;
    } finally { setHistoryVersion(value => value + 1); }
  }
  async function selectSavedMeeting(id) {
    const saved = await getMeeting(id);
    if (deletedMeetings.current.has(id)) return null;
    setMeeting(saved); setSelectedId(id); writeStorage("notas-meeting-id", id);
    window.location.hash = "/resultados";
    return saved;
  }
  async function monitorJob(id, first) {
    let job = first, loadedId = "";
    setProcessing({ status: "processing", phase: "Preparando el procesamiento…", error: "" });
    while (true) {
      if (!job) {
        try { job = await getJob(id); }
        catch (error) {
          setProcessing({ status: "processing", phase: "Sin conexión. Reintentando…", error: error.message });
          await new Promise(resolve => setTimeout(resolve, 2000)); continue;
        }
      }
      if (job.meeting_id && (job.meeting_id !== loadedId || job.status !== "procesando")) {
        try { await selectSavedMeeting(job.meeting_id); loadedId = job.meeting_id; } catch { /* Retry while the job is available. */ }
      }
      const phases = { recibido: "Audio recibido…", transcribiendo: "Transcribiendo el audio…", analizando: "Preparando el resumen y las tareas…" };
      if (job.status !== "procesando") {
        writeStorage("meet-notes-active-job", ""); activeJob.current = "";
        setProcessing({ status: job.status === "listo" ? "success" : job.status === "cancelado" ? "cancelled" : "error", phase: "", error: job.error || "" });
        setHistoryVersion(value => value + 1); return;
      }
      setProcessing({ status: "processing", phase: phases[job.stage] || "Procesando…", error: "" });
      await new Promise(resolve => setTimeout(resolve, 1200)); job = null;
    }
  }
  async function processMeeting() {
    if (busy.current) return;
    busy.current = true; cancelRequested.current = false;
    const id = crypto.randomUUID(); activeJob.current = id;
    writeStorage("meet-notes-active-job", id);
    uploadController.current = new AbortController();
    setProcessing({ status: "processing", phase: "Subiendo el audio…", error: "" });
    try {
      const job = await startJob({ id, name: draft.name.trim(), title: draft.title.trim(), file: draft.file }, uploadController.current.signal);
      await monitorJob(id, job);
    } catch (error) {
      if (cancelRequested.current) {
        await monitorJob(id);
      } else {
        // A response can be lost after the server accepted the upload.
        try { await monitorJob(id, await getJob(id)); }
        catch {
          writeStorage("meet-notes-active-job", ""); activeJob.current = "";
          setProcessing({ status: "error", phase: "", error: error.message });
        }
      }
    } finally { busy.current = false; uploadController.current = null; }
  }
  async function cancelCurrentJob() {
    if (!activeJob.current) return;
    try {
      const job = await cancelJob(activeJob.current);
      if (job.status === "cancelado") { cancelRequested.current = true; uploadController.current?.abort(); }
    } catch (error) { setProcessing(old => ({ ...old, error: "No se pudo confirmar la cancelación. " + error.message })); }
  }
  async function cancelMeetingAnalysis(id) {
    const saved = await cancelAnalysis(id);
    setMeeting(old => old?.id === saved.id ? saved : old);
    if (activeJob.current) {
      const job = await getJob(activeJob.current).catch(() => null);
      if (job?.meeting_id === id) await cancelCurrentJob();
    }
    setHistoryVersion(value => value + 1);
  }
  async function resolveCandidate(proposal, data) {
    const saved = await resolveProposal(proposal.meeting_id, proposal.id, { ...data, version: proposal.version });
    setMeeting(old => old?.id === saved.id ? saved : old); setHistoryVersion(value => value + 1);
  }
  function openMeeting(id) {
    setLoadError("");
    if (selectedId !== id) setMeeting(null);
    setSelectedId(id); writeStorage("notas-meeting-id", id); window.location.hash = "/resultados";
  }
  async function refreshMeeting() {
    if (!selectedId) return;
    const saved = await getMeeting(selectedId); if (deletedMeetings.current.has(saved.id)) return; setMeeting(saved); setLoadError("");
  }
  async function reviewTranscript(source, text, requestId) {
    const saved = await createReviewedMeeting(prepareTranscriptReview(source, text, requestId));
    setHistoryVersion(value => value + 1);
    await selectSavedMeeting(saved.id);
    try { await retryAnalysis(saved.id); }
    catch (error) { setLoadError(error.message); }
  }
  async function removeMeeting(id) {
    try { await deleteMeeting(id); }
    catch (error) { if (error.status !== 404) throw error; }
    deletedMeetings.current.add(id);
    const removedTasks = noteSaver.current.discardMeeting(id);
    setSaveStates(previous => Object.fromEntries(Object.entries(previous).filter(([taskId]) => !removedTasks.has(taskId))));
    setMeeting(previous => previous?.id === id ? null : previous);
    setSelectedId(previous => previous === id ? "" : previous);
    if (readStorage("notas-meeting-id") === id) writeStorage("notas-meeting-id", "");
    setLoadError(""); setHistoryVersion(value => value + 1);
  }
  function changeNote(task, value) { noteSaver.current.change(task, value); }
  async function saveTask(task, fields, overwrite = false) { return noteSaver.current.saveFields(task, fields, overwrite); }
  return (
    <div className="app-shell">
      <a className="skip-link" href="#contenido" onClick={event => { event.preventDefault(); mainRef.current?.focus(); }}>Saltar al contenido</a>
      <aside className="sidebar">
        <a href="#/nueva" className="brand" aria-label="meet-notes, inicio"><span className="brand-mark"><NotebookPen size={25} aria-hidden="true" /></span><span><strong>meet-notes</strong></span></a>
        <nav aria-label="Navegación principal" className="main-nav">{navigation.map(({ path, label, icon: Icon }) => (
          <a key={path} href={"#" + path} className="nav-link" aria-current={route === path ? "page" : undefined}><Icon size={21} aria-hidden="true" /><span>{label}</span></a>
        ))}</nav>
        <div className="sidebar-note"><HardDrive size={19} aria-hidden="true" /><div><strong>Guardado local</strong><p>Tus reuniones quedan en esta computadora.</p></div></div>
      </aside>
      <div className="workspace">
        <header className="topbar"><div className="breadcrumb"><span>Reuniones</span><ChevronRight size={14} aria-hidden="true" /><span>{current?.label || "Página no encontrada"}</span></div><span className="local-status"><span aria-hidden="true" />En esta computadora</span></header>
        <main id="contenido" className="main" ref={mainRef} tabIndex={-1}>
          {processing.status === "processing" && route !== "/nueva" && (route !== "/resultados" || meeting?.analysis_status !== "procesando") && <div className="integration-notice"><p role="status">{processing.phase}</p><button className="button secondary" onClick={cancelCurrentJob}>Cancelar procesamiento</button></div>}
          {processing.status === "error" && route !== "/nueva" && <p className="error-message" role="alert">{processing.error} <a href="#/nueva" className="recovery-link">Volver al formulario</a></p>}
          {route === "/nueva" && <NewMeeting draft={draft} onChange={updateDraft} onProcess={processMeeting} processing={processing} onCancel={cancelCurrentJob} />}
          {route === "/resultados" && <Results key={selectedId || "empty"} meeting={meeting} loading={loading} loadError={loadError}
            onRefresh={refreshMeeting} onRetry={retryAnalysis} onReview={reviewTranscript} onCancel={cancelMeetingAnalysis} onResolve={resolveCandidate} saveStates={saveStates} noteDrafts={noteDrafts} onNoteChange={changeNote} onSaveTask={saveTask} />}
          {route === "/historial" && <MeetingHistory onOpen={openMeeting} onDelete={removeMeeting} version={historyVersion} />}
          {!current && <div className="card"><EmptyState title="No encontramos esta página" action={<a href="#/nueva" className="button secondary"><ArrowLeft size={18} aria-hidden="true" />Volver a Nueva reunión</a>}><p>Puedes continuar desde el formulario principal.</p></EmptyState></div>}
        </main>
        
      </div>
    </div>
  );
}
