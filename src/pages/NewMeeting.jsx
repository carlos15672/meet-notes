import { useRef, useState } from "react";
import { ArrowRight, FileText, ListTodo, LoaderCircle, NotebookPen, ShieldCheck } from "lucide-react";
import AudioPicker from "../components/AudioPicker.jsx";
import { PageHeading } from "../components/UI.jsx";
import { validateAudio, validateName } from "../lib/validation.js";

export default function NewMeeting({ draft, onChange, onProcess, processing, onCancel }) {
  const [nameTouched, setNameTouched] = useState(false);
  const [fileError, setFileError] = useState("");
  const nameRef = useRef(null);
  const busy = processing.status === "processing";
  const nameError = nameTouched ? validateName(draft.name) : "";
  const ready = !validateName(draft.name) && !validateAudio(draft.file);
  function submit(event) {
    event.preventDefault();
    if (busy) return;
    setNameTouched(true);
    if (validateName(draft.name)) { nameRef.current?.focus(); return; }
    const error = validateAudio(draft.file);
    setFileError(error);
    if (!error) onProcess();
  }
  return <>
    <PageHeading eyebrow="NUEVA REUNIÓN" title="Subir una reunión">
      Elige una grabación para obtener el resumen y las tareas que te asignaron.
    </PageHeading>
    <div className="meeting-layout">
      <form className="card meeting-form" noValidate onSubmit={submit} aria-labelledby="meeting-form-title">
        <fieldset className="meeting-fields" disabled={busy}>
          <legend className="sr-only">Datos y audio de la reunión</legend>
          <div className="section-heading">
            <span className="step-number" aria-hidden="true">1</span>
            <div><h2 id="meeting-form-title">Datos de la reunión</h2><p className="help">El título es opcional.</p></div>
          </div>
          <div className="form-columns">
            <div className="field">
              <label htmlFor="user-name">Tu nombre <span className="required-label">Obligatorio</span></label>
              <input ref={nameRef} id="user-name" name="name" autoComplete="given-name" required maxLength={80}
                value={draft.name} placeholder="Ej. Carlos"
                onChange={event => onChange("name", event.target.value)} onBlur={() => setNameTouched(true)}
                aria-invalid={Boolean(nameError)} aria-describedby={"name-help" + (nameError ? " name-error" : "")} />
              <p id="name-help" className="help">Usa el nombre con el que te mencionan en el audio.</p>
              {nameError && <p id="name-error" className="error-message" role="alert">{nameError}</p>}
            </div>
            <div className="field">
              <label htmlFor="meeting-title">Título <span className="optional-label">Opcional</span></label>
              <input id="meeting-title" name="title" maxLength={120} value={draft.title}
                placeholder="Ej. Revisión del proyecto" onChange={event => onChange("title", event.target.value)} />
              <p className="help">Para encontrarla después en el historial.</p>
            </div>
          </div>
          <div className="form-divider" />
          <div className="section-heading">
            <span className="step-number" aria-hidden="true">2</span>
            <div><h2>Audio de la reunión</h2><p className="help">MP3, WAV, M4A o MP4 · Hasta 100 MB y 45 minutos.</p><p className="help">De los MP4 se utiliza solo el audio.</p></div>
          </div>
          <AudioPicker file={draft.file} onChange={file => { setFileError(""); onChange("file", file); }} />
        </fieldset>
        {fileError && <p className="error-message" role="alert">{fileError}</p>}
        <div className="process-area">
          <button type="submit" className="button primary process-button" disabled={busy || !ready} aria-describedby="processing-help">
            {busy && <LoaderCircle className="spinner" size={20} aria-hidden="true" />}
            {busy ? processing.phase : "Procesar reunión"}
            {!busy && <ArrowRight size={20} aria-hidden="true" />}
          </button>
          {busy && <button type="button" className="button secondary" onClick={onCancel}>Cancelar procesamiento</button>}
          {processing.status === "cancelled" && <p role="status" className="help">Procesamiento cancelado. Puedes elegir otro audio o volver a intentarlo.</p>}
          <p id="processing-help" className="help">
            {busy ? "Puede tardar unos minutos. El tiempo depende de la duración del audio."
              : ready ? "Todo listo. El procesamiento puede tardar unos minutos."
              : "Escribe tu nombre y elige un audio para continuar."}
          </p>
          <p className="sr-only" role="status" aria-live="polite">{busy ? processing.phase : ""}</p>
          {processing.status === "error" && <p className="error-message" role="alert">{processing.error}</p>}
          {processing.status === "success" && <a className="button secondary" href="#/resultados">Abrir resultados</a>}
        </div>
      </form>
      <aside className="meeting-aside" aria-labelledby="guide-title">
        <div className="guide">
          <p className="eyebrow">DESPUÉS DE PROCESAR</p>
          <h2 id="guide-title">Qué vas a encontrar</h2>
          <ol className="benefits">
            <li><span className="guide-icon"><FileText size={20} aria-hidden="true" /></span><div><h3>Resumen</h3><p>Los temas tratados y los acuerdos de la reunión.</p></div></li>
            <li><span className="guide-icon"><ListTodo size={20} aria-hidden="true" /></span><div><h3>Tus pendientes</h3><p>Las tareas asignadas a tu nombre y sus fechas, si se mencionan.</p></div></li>
            <li><span className="guide-icon"><NotebookPen size={20} aria-hidden="true" /></span><div><h3>Notas por tarea</h3><p>Un espacio para anotar detalles y marcar tu avance.</p></div></li>
          </ol>
          <p className="guide-footnote">También podrás leer y copiar la transcripción completa.</p>
        </div>
        <div className="local-note"><ShieldCheck size={20} aria-hidden="true" /><div><strong>Se procesa en tu computadora</strong><p>La transcripción y los resultados quedan guardados aquí, en el historial.</p></div></div>
      </aside>
    </div>
  </>;
}
