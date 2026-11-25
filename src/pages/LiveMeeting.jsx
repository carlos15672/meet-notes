import { useEffect, useState } from "react";
import { AudioLines, ArrowUpRight, CircleDot, Mic2, MonitorSpeaker, Play } from "lucide-react";
import { PageHeading } from "../components/UI.jsx";
import { listLiveSessions, openFloatingWindow } from "../services/api.js";

const labels = { capturando: "Escuchando", pausada: "Pausada", finalizando: "Transcribiendo",
  analizando: "Analizando", lista: "Lista", interrumpida: "Interrumpida", error: "Requiere atención" };

export default function LiveMeeting() {
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    let mounted = true;
    let timer;
    const refresh = async () => {
      try {
        const result = await listLiveSessions();
        if (mounted) setSessions(result.items);
      } catch (failure) {
        if (mounted) setError(failure.message);
      }
      if (mounted) timer = window.setTimeout(refresh, 3000);
    };
    void refresh();
    return () => { mounted = false; window.clearTimeout(timer); };
  }, []);
  async function launch() {
    setLoading(true); setError(""); setNotice("");
    try {
      const result = await openFloatingWindow();
      setNotice(result.ya_estaba_abierta ? "La ventana flotante ya está abierta." : "Ventana flotante abierta. Puedes moverla sobre tu reunión.");
    } catch (failure) { setError(failure.message); }
    finally { setLoading(false); }
  }
  const latest = sessions[0];
  return <>
    <PageHeading eyebrow="CAPTURA EN VIVO" title="Escucha una reunión en tu computadora">
      Abre una ventana flotante para capturar el sonido de la reunión y tu micrófono mientras trabajas en Zoom, Meet o Teams.
    </PageHeading>
    <div className="live-grid">
      <section className="card live-main" aria-labelledby="live-title">
        <span className="icon-tile"><AudioLines size={28} aria-hidden="true" /></span>
        <h2 id="live-title">Ventana flotante</h2>
        <p className="help">Elige tu nombre y los dispositivos de audio. Después podrás pausar, marcar momentos y terminar para generar el resumen y tus pendientes.</p>
        <button className="button primary" type="button" onClick={launch} disabled={loading}>
          <Play size={18} aria-hidden="true" />{loading ? "Abriendo…" : "Abrir ventana flotante"}
        </button>
        {notice && <p role="status" className="help">{notice}</p>}
        {error && <p role="alert" className="error-message">{error}</p>}
      </section>
      <aside className="card live-guide" aria-label="Cómo se captura el audio">
        <div><MonitorSpeaker size={22} aria-hidden="true" /><div><h2>Audio de la reunión</h2><p className="help">Se toma de la salida de sonido de Windows, incluso cuando usas audífonos.</p></div></div>
        <div><Mic2 size={22} aria-hidden="true" /><div><h2>Tu micrófono</h2><p className="help">Se guarda en una pista separada antes de combinar el audio para la transcripción.</p></div></div>
        <p className="help">La captura incluye otros sonidos que reproduzca esta computadora. La versión actual no identifica por nombre a los demás hablantes.</p>
      </aside>
    </div>
    {latest && <section className="card live-recent" aria-labelledby="live-recent-title">
      <div><h2 id="live-recent-title">Última captura</h2><span className="badge"><CircleDot size={14} aria-hidden="true" />{labels[latest.status] || latest.status}</span></div>
      <p>{latest.title}</p>
      <p className="help">{latest.marcas.length} {latest.marcas.length === 1 ? "momento marcado" : "momentos marcados"} · {latest.segmentos.length} fragmentos de texto</p>
      {latest.meeting_id && <a className="button secondary" href={"#/resultados/" + latest.meeting_id}>Abrir resultados<ArrowUpRight size={17} aria-hidden="true" /></a>}
    </section>}
  </>;
}
