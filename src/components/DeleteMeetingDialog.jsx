import { useEffect, useId, useRef } from "react";
import { Trash2 } from "lucide-react";

export default function DeleteMeetingDialog({ meeting, busy, error, onCancel, onConfirm }) {
  const id = useId();
  const dialog = useRef(null);
  const cancel = useRef(null);
  useEffect(() => {
    const previous = document.activeElement;
    const element = dialog.current;
    element.showModal(); cancel.current?.focus();
    return () => {
      element.close();
      if (previous?.isConnected) previous.focus();
      else document.getElementById("history-search")?.focus();
    };
  }, []);
  return <dialog ref={dialog} className="delete-dialog" role="alertdialog" aria-labelledby={id + "-title"} aria-describedby={id + "-description"}
    onCancel={event => { event.preventDefault(); if (!busy) onCancel(); }}>
    <span className="delete-dialog-icon" aria-hidden="true"><Trash2 size={24} /></span>
    <h2 id={id + "-title"}>¿Eliminar esta reunión?</h2>
    <p className="delete-meeting-title">{meeting.title}</p>
    <p id={id + "-description"}>Se eliminarán su transcripción, resumen, tareas y notas. Esta acción no se puede deshacer.</p>
    {error && <p className="error-message" role="alert">{error}</p>}
    <p className="sr-only" role="status">{busy ? "Eliminando reunión…" : ""}</p>
    <div className="delete-dialog-actions">
      <button ref={cancel} type="button" className="button secondary" disabled={busy} onClick={onCancel}>Cancelar</button>
      <button type="button" className="button danger" disabled={busy} onClick={onConfirm}>{busy ? "Eliminando…" : "Eliminar reunión"}</button>
    </div>
  </dialog>;
}
