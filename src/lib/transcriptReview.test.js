import test from "node:test";
import assert from "node:assert/strict";
import { MAX_TRANSCRIPT_LENGTH, prepareTranscriptReview } from "./transcriptReview.js";

const meeting = { id: "original", title: "Prueba", userName: "Carlos", fileName: "audio.mp4", idioma: "es",
  duracion_segundos: 24, modelo: "large-v3-turbo", texto: "Texto original.",
  segmentos: [{ inicio: 0, fin: 24, texto: "Texto original." }], pendientes: [{ id: "task", nota: "Conservar" }] };

test("La revisión crea una versión vinculada sin modificar la reunión ni sus notas", () => {
  const before = structuredClone(meeting);
  const result = prepareTranscriptReview(meeting, "  Texto corregido.  ", "request-1");
  assert.deepEqual(meeting, before);
  assert.equal(result.title, "Prueba · revisada");
  assert.equal(result.transcription.texto, "Texto corregido.");
  assert.equal(result.transcription.reunion_origen, "original");
  assert.equal(result.transcription.revision_manual, true);
  assert.equal(result.userName, "Carlos"); assert.equal(result.fileName, "audio.mp4");
});
test("El texto corregido conserva duración y modelo y no atribuye tiempos no verificados", () => {
  const result = prepareTranscriptReview(meeting, "Una frase nueva.", "request-1");
  assert.equal(result.transcription.duracion_segundos, 24);
  assert.equal(result.transcription.modelo, "large-v3-turbo");
  assert.deepEqual(result.transcription.segmentos, []);
});
test("Reintentar la misma revisión conserva la clave para evitar duplicados", () => {
  assert.deepEqual(prepareTranscriptReview(meeting, "Otro texto.", "stable-id"), prepareTranscriptReview(meeting, "Otro texto.", "stable-id"));
});
test("Rechaza revisiones vacías, sin cambios o demasiado largas", () => {
  for (const text of ["  ", meeting.texto, "x".repeat(MAX_TRANSCRIPT_LENGTH + 1)]) {
    assert.throws(() => prepareTranscriptReview(meeting, text, "request-1"));
  }
});
test("El título de la versión cabe en el límite del servidor", () => {
  assert.ok(prepareTranscriptReview({ ...meeting, title: "x".repeat(120) }, "Otro texto.", "request-1").title.length <= 120);
});
