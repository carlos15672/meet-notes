const API_BASE = (import.meta.env?.VITE_API_BASE_URL || "").replace(/\/$/, "");

export async function request(path, options = {}) {
  let response;
  try { response = await fetch(API_BASE + path, options); }
  catch (error) {
    if (error.name === "AbortError") throw error;
    throw new Error("No se pudo conectar con meet-notes. Comprueba que la aplicación esté iniciada y vuelve a intentarlo.");
  }
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof payload?.detail === "string" ? payload.detail
      : Array.isArray(payload?.detail) ? "Hay datos inválidos. Revisa los campos e inténtalo de nuevo."
      : "El servicio no pudo completar la operación. Vuelve a intentarlo.";
    const error = new Error(message); error.status = response.status; throw error;
  }
  if (payload === null) throw new Error("El servicio devolvió una respuesta incompleta.");
  return payload;
}
function jsonOptions(method, data) {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
}
export async function transcribeAudio(file) {
  const form = new FormData(); form.append("audio", file);
  const data = await request("/api/transcribir", { method: "POST", body: form });
  if (typeof data?.texto !== "string" || !data.texto.trim()
    || !Number.isFinite(data.duracion_segundos) || data.duracion_segundos <= 0
    || !Array.isArray(data.segmentos) || !data.segmentos.every(s => s && typeof s.texto === "string"
      && Number.isFinite(s.inicio) && Number.isFinite(s.fin) && s.inicio >= 0 && s.fin >= s.inicio)) {
    throw new Error("La respuesta de transcripción está incompleta. Vuelve a intentarlo.");
  }
  return data;
}
export const createMeeting = data => request("/api/reuniones", jsonOptions("POST", data));
export async function createReviewedMeeting(data) {
  const status = await request("/api/estado");
  if (status.revision_transcripciones !== true) {
    throw new Error("Reinicia meet-notes con Reiniciar-meet-notes.cmd para guardar versiones revisadas y vuelve a intentarlo.");
  }
  return createMeeting(data);
}
export const getMeeting = (id, signal) => request("/api/reuniones/" + encodeURIComponent(id), { signal });
export const deleteMeeting = id => request("/api/reuniones/" + encodeURIComponent(id), { method: "DELETE" });
export const analyzeMeeting = id => request("/api/reuniones/" + encodeURIComponent(id) + "/analizar", { method: "POST" });
export const listMeetings = (q, offset, signal) => request("/api/reuniones?" + new URLSearchParams({ q, offset, limit: 20 }), { signal });
export const updateTask = (meetingId, taskId, data) => request(
  "/api/reuniones/" + encodeURIComponent(meetingId) + "/pendientes/" + encodeURIComponent(taskId), jsonOptions("PATCH", data));


export async function startJob({ id, name, title, file }, signal) {
  const form = new FormData();
  form.append("request_id", id); form.append("userName", name); form.append("title", title); form.append("audio", file);
  try { return await request("/api/trabajos", { method: "POST", body: form, signal }); }
  catch (error) {
    if (error.status === 415 && /\.mp4$/i.test(file.name)) {
      error.message = "El servidor abierto todavía no admite MP4. Abre Reiniciar-meet-notes.cmd y recarga la página para cargar los cambios.";
    }
    throw error;
  }
}
export const getJob = (id, signal) => request("/api/trabajos/" + encodeURIComponent(id), { signal });
export const cancelJob = id => request("/api/trabajos/" + encodeURIComponent(id) + "/cancelar", { method: "POST" });
export const cancelAnalysis = id => request("/api/reuniones/" + encodeURIComponent(id) + "/cancelar", { method: "POST" });
export const resolveProposal = (meetingId, proposalId, data) => request("/api/reuniones/" + encodeURIComponent(meetingId) + "/propuestas/" + encodeURIComponent(proposalId), jsonOptions("PATCH", data));
