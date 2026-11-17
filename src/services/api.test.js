import test from "node:test";
import assert from "node:assert/strict";
import { analyzeMeeting, createMeeting, createReviewedMeeting, deleteMeeting, getMeeting, listMeetings, startJob, transcribeAudio, updateTask } from "./api.js";

const transcript = { texto: "Carlos preparará el informe.", duracion_segundos: 30,
  segmentos: [{ inicio: 0, fin: 3, texto: "Carlos preparará el informe." }], idioma: "es", modelo: "whisper" };
const reply = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("Una revisión no se envía a un servidor anterior que ignoraría su procedencia", async t => {
  const fetch = t.mock.method(globalThis, "fetch", async () => reply({ estado: "ok" }));
  await assert.rejects(createReviewedMeeting({}), /Reiniciar-meet-notes.cmd/);
  assert.equal(fetch.mock.callCount(), 1);
});

test("Una revisión se guarda cuando el servidor conserva la procedencia del texto", async t => {
  const data = { request_id: "review-test", transcription: { texto: "Texto corregido.", revision_manual: true } };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    if (url === "/api/estado") return reply({ revision_transcripciones: true });
    assert.equal(url, "/api/reuniones"); assert.deepEqual(JSON.parse(options.body), data);
    return reply({ id: "reviewed" }, 201);
  });
  assert.equal((await createReviewedMeeting(data)).id, "reviewed");
});

test("Un servidor anterior que rechaza MP4 indica cómo cargar la actualización", async t => {
  t.mock.method(globalThis, "fetch", async () => reply({ detail: "Selecciona un archivo MP3, WAV o M4A." }, 415));
  await assert.rejects(startJob({ id: "test-id", name: "Carlos", title: "Prueba", file: new File(["audio"], "WhatsApp.MP4") }),
    error => error.status === 415 && error.message.includes("Reiniciar-meet-notes.cmd"));
});

test("El audio se envía como multipart con el campo esperado por FastAPI", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/transcribir"); assert.equal(options.method, "POST");
    assert.equal(options.body.get("audio").name, "reunion.wav");
    assert.equal(options.headers, undefined); return reply(transcript);
  });
  assert.deepEqual(await transcribeAudio(new File(["audio"], "reunion.wav")), transcript);
});
test("Guardar conserva la clave de reintento y el nombre con acentos", async t => {
  const data = { request_id: "operation-1", userName: "José", transcription: transcript };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/reuniones"); assert.deepEqual(JSON.parse(options.body), data);
    return reply({ id: "saved" }, 201);
  });
  assert.equal((await createMeeting(data)).id, "saved");
});
test("El estado se guarda con control de versión y sin reemplazar la nota", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/reuniones/meeting/pendientes/task");
    assert.equal(options.method, "PATCH");
    assert.deepEqual(JSON.parse(options.body), { estado: "completado", version: 2 });
    return reply({ estado: "completado", nota: "Conservar" });
  });
  assert.equal((await updateTask("meeting", "task", { estado: "completado", version: 2 })).nota, "Conservar");
});
test("El historial codifica búsquedas y paginación sin alterar el texto", async t => {
  t.mock.method(globalThis, "fetch", async url => {
    const parsed = new URL(url, "http://localhost");
    assert.equal(parsed.searchParams.get("q"), "Carlos & José 100%");
    assert.equal(parsed.searchParams.get("offset"), "20"); return reply({ items: [], total: 0 });
  });
  await listMeetings("Carlos & José 100%", 20);
});
test("Una nota desactualizada conserva el mensaje de conflicto del servidor", async t => {
  t.mock.method(globalThis, "fetch", async () => reply({ detail: "La nota cambió en otra pestaña." }, 409));
  await assert.rejects(updateTask("m", "t", { nota: "Nueva", version: 0 }), error => error.status === 409 && error.message.includes("otra pestaña"));
});
test("La falta de IA se comunica sin simular un análisis exitoso", async t => {
  t.mock.method(globalThis, "fetch", async () => reply({ detail: "Falta preparar la IA local." }, 503));
  await assert.rejects(analyzeMeeting("meeting"), /Falta preparar la IA local/);
});
test("Un segmento malformado se rechaza antes de renderizar resultados", async t => {
  t.mock.method(globalThis, "fetch", async () => reply({ ...transcript, segmentos: [null] }));
  await assert.rejects(transcribeAudio(new File(["audio"], "reunion.wav")), /incompleta/);
});
test("Cancelar la consulta conserva AbortError para evitar avisos al cambiar de vista", async t => {
  const error = new DOMException("Cancelada", "AbortError");
  t.mock.method(globalThis, "fetch", async () => { throw error; });
  await assert.rejects(getMeeting("meeting"), result => result === error);
});

test("Eliminar usa DELETE sobre la reunión seleccionada", async t => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, "/api/reuniones/meeting-123"); assert.equal(options.method, "DELETE");
    assert.equal(options.body, undefined); return reply({ id: "meeting-123", eliminada: true });
  });
  assert.equal((await deleteMeeting("meeting-123")).eliminada, true);
});
