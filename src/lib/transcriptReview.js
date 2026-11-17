export const MAX_TRANSCRIPT_LENGTH = 250000;

export function prepareTranscriptReview(meeting, text, requestId) {
  const reviewed = text.trim();
  if (!reviewed) throw new Error("La transcripción no puede quedar vacía.");
  if (reviewed.length > MAX_TRANSCRIPT_LENGTH) throw new Error("La transcripción supera el límite de 250 000 caracteres.");
  if (reviewed === meeting.texto.trim()) throw new Error("Corrige el texto antes de guardar una nueva versión.");
  return {
    request_id: requestId,
    title: meeting.title.slice(0, 107) + " · revisada",
    userName: meeting.userName,
    fileName: meeting.fileName,
    transcription: {
      texto: reviewed, idioma: meeting.idioma, duracion_segundos: meeting.duracion_segundos,
      segmentos: [], modelo: meeting.modelo, revision_manual: true, reunion_origen: meeting.id,
    },
  };
}
