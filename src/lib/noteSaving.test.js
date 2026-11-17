import test from "node:test";
import assert from "node:assert/strict";
import { createNoteSaver } from "./noteSaving.js";
const task = { id: "t1", meeting_id: "m1", nota: "", estado: "pendiente", version: 0 };
function setup(t, save, storage) {
  const states = [];
  const saver = createNoteSaver({ save, delay: 100000, storage, onState: (_, value) => states.push(value) });
  t.after(() => saver.dispose()); saver.sync([task]); return { saver, states };
}
test("Guarda la nota y conserva la versión devuelta por SQLite", async t => {
  const calls = []; const { saver } = setup(t, async (current, fields) => { calls.push(fields); return { ...current, ...fields, version: current.version + 1 }; });
  saver.change(task, "Nota nueva"); await saver.flush(task.id);
  assert.deepEqual(calls, [{ version: 0, nota: "Nota nueva" }]); assert.equal(saver.hasPending(), false);
});
test("Escribir durante un guardado conserva el texto más reciente", async t => {
  let release; let count = 0; const calls = [];
  const { saver } = setup(t, async (current, fields) => { calls.push(fields); if (++count === 1) await new Promise(resolve => { release = resolve; }); return { ...current, ...fields, version: current.version + 1 }; });
  saver.change(task, "Primera"); const pending = saver.flush(task.id);
  saver.change(task, "Segunda"); release(); await pending; await saver.flush(task.id);
  assert.equal(calls[1].nota, "Segunda"); assert.equal(calls[1].version, 1); assert.equal(saver.hasPending(), false);
});
test("Nota y estado se serializan sin usar versiones antiguas", async t => {
  const calls = []; const { saver } = setup(t, async (current, fields) => { calls.push(fields); return { ...current, ...fields, version: current.version + 1 }; });
  saver.change(task, "Revisar datos"); await saver.saveFields(task, { estado: "en_curso" });
  assert.deepEqual(calls[0], { version: 0, nota: "Revisar datos", estado: "en_curso" });
});
test("Un fallo conserva el borrador y permite reintentar", async t => {
  let fail = true; const { saver, states } = setup(t, async (current, fields) => { if (fail) throw new Error("Sin conexión"); return { ...current, ...fields, version: 1 }; });
  saver.change(task, "No perder"); await saver.flush(task.id); assert.equal(states.at(-1).status, "error"); assert.equal(saver.hasPending(), true);
  fail = false; await saver.saveFields(task, { nota: "No perder" }); assert.equal(saver.hasPending(), false);
});
test("Un conflicto no se sobrescribe automáticamente", async t => {
  let count = 0; const { saver, states } = setup(t, async () => { count++; throw Object.assign(new Error("Conflicto"), { status: 409 }); });
  saver.change(task, "Mi nota"); await saver.flush(task.id); saver.change(task, "Mi corrección"); await saver.flush(task.id);
  assert.equal(count, 1); assert.equal(states.at(-1).status, "conflicto");
});
test("Recupera borradores al reabrir y exige revisar una nota remota distinta", async t => {
  const storage = { getItem: () => JSON.stringify({ t1: { nota: "Mi borrador", base_note: "Original", meeting_id: "m1" } }), setItem() {} };
  let calls = 0; const { saver, states } = setup(t, async () => { calls++; }, storage);
  await saver.flush(task.id); assert.equal(calls, 0); assert.equal(states.at(-1).status, "conflicto");
});
test("La confirmación explícita usa la última versión recibida", async t => {
  const calls = []; const { saver } = setup(t, async (current, fields) => { calls.push(fields); return { ...current, ...fields, version: current.version + 1 }; });
  saver.change(task, "Mi borrador"); saver.sync([{ ...task, nota: "Otra pestaña", version: 3 }]);
  await saver.saveFields(task, { nota: "Mi borrador" }, true);
  assert.equal(calls[0].version, 3); assert.equal(calls[0].nota, "Mi borrador");
});
test("Un borrador que ya llegó al servidor se limpia sin repetir el guardado", async t => {
  const writes = []; const storage = { getItem: () => JSON.stringify({ t1: { nota: "", base_note: "", meeting_id: "m1" } }), setItem: (_, value) => writes.push(value) };
  const { saver } = setup(t, async () => { throw new Error("No debe guardar"); }, storage);
  await saver.flush(task.id); assert.equal(saver.hasPending(), false); assert.deepEqual(JSON.parse(writes.at(-1)), {});
});

test("Un cambio remoto de estado no se sobrescribe al actualizar los datos", async t => {
  let release; const { saver, states } = setup(t, async () => { await new Promise(resolve => { release=resolve; }); throw Object.assign(new Error("Conflicto"), { status:409 }); });
  const writing=saver.saveFields(task,{estado:"en_curso"}); release(); await writing;
  saver.sync([{...task,estado:"completado",version:2}]);
  assert.equal(states.at(-1).status,"conflicto");
  assert.equal(states.at(-1).remoteState,"completado");
  assert.equal(states.at(-1).desiredState,"en_curso");
});

test("Eliminar una reunión descarta sus borradores y no los de otras reuniones", async t => {
  const writes=[]; const storage={getItem:()=>null,setItem:(_,value)=>writes.push(JSON.parse(value))};
  const { saver }=setup(t,async()=>{throw new Error("No debe guardar");},storage);
  const other={...task,id:"t2",meeting_id:"m2"}; saver.sync([other]);
  saver.change(task,"Borrar este borrador"); saver.change(other,"Conservar este borrador");
  const removed=saver.discardMeeting("m1"); await saver.flush(task.id);
  assert.equal(removed.has("t1"),true); assert.equal(writes.at(-1).t1,undefined);
  assert.equal(writes.at(-1).t2.nota,"Conservar este borrador"); assert.equal(saver.hasPending(),true);
});
test("Una respuesta de guardado posterior al borrado no recupera el borrador", async t => {
  let reject; const writes=[]; const storage={getItem:()=>null,setItem:(_,value)=>writes.push(value)};
  const { saver, states }=setup(t,async()=>new Promise((_,fail)=>{reject=fail;}),storage);
  saver.change(task,"Pendiente"); const request=saver.flush(task.id);
  saver.discardMeeting("m1"); const notifications=states.length;
  reject(Object.assign(new Error("La tarea ya no existe"),{status:404})); await request;
  assert.equal(saver.hasPending(),false); assert.deepEqual(JSON.parse(writes.at(-1)),{});
  assert.equal(states.length,notifications);
});
test("Eliminar también limpia borradores de reuniones que aún no se han abierto", t => {
  const writes=[]; const storage={getItem:()=>JSON.stringify({hidden:{nota:"Privada",base_note:"",meeting_id:"old"}}),setItem:(_,value)=>writes.push(JSON.parse(value))};
  const { saver }=setup(t,async()=>{},storage); const removed=saver.discardMeeting("old");
  assert.equal(removed.has("hidden"),true); assert.deepEqual(writes.at(-1),{});
});
