import { useId, useState } from "react";

export default function ProposalCard({ proposal, onResolve }) {
  const id = useId();
  const [owner, setOwner] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function resolve(decision) {
    setBusy(true); setError("");
    try { await onResolve(proposal, { decision, responsable: owner || undefined }); }
    catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  return <article className="task-card proposal-card">
    <span className="badge">Por confirmar</span><h3>{proposal.descripcion}</h3><p className="help">{proposal.motivo}</p>
    <blockquote>{proposal.evidencia}</blockquote>
    {proposal.opciones.length > 0 && <div className="field"><label htmlFor={id}>¿Cuál es tu nombre?</label>
      <select id={id} value={owner} onChange={e => setOwner(e.target.value)} disabled={busy}>
        <option value="">Elige tu nombre</option>{proposal.opciones.map(name => <option key={name}>{name}</option>)}
      </select></div>}
    <div className="proposal-actions"><button className="button primary" disabled={busy || (proposal.opciones.length > 0 && !owner)} onClick={() => resolve("confirmar")}>Es mi tarea</button>
      <button className="button secondary" disabled={busy} onClick={() => resolve("descartar")}>No me corresponde</button></div>
    {error && <p className="error-message" role="alert">{error}</p>}
  </article>;
}
