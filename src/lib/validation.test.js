import test from "node:test";
import assert from "node:assert/strict";
import {
  MAX_AUDIO_BYTES,
  validateAudio,
  validateName,
} from "./validation.js";

const file = (name, size = 1024, type = "") => ({ name, size, type });

const audioCases = [
  ["Archivo ausente", null, true],
  ["Archivo vacío", file("a.mp3", 0), true],
  ["Límite exacto", file("a.wav", MAX_AUDIO_BYTES, "audio/wav"), false],
  ["Límite excedido", file("a.wav", MAX_AUDIO_BYTES + 1), true],
  ["Extensión doble", file("a.mp3.exe"), true],
  ["Extensión mayúscula", file("VOZ.MP3", 1024, "audio/mpeg"), false],
  ["Tipo incongruente", file("a.wav", 1024, "image/png"), true],
  ["M4A admitido", file("a.m4a", 1024, "audio/mp4"), false],
  ["MP4 de audio admitido", file("WhatsApp Audio.mp4", 1024, "audio/mp4"), false],
  ["MP4 con video admitido", file("reunion.mp4", 1024, "video/mp4"), false],
  ["MP4 con tipo de contenedor admitido", file("reunion.mp4", 1024, "application/mp4"), false],
  ["MP4 en mayúsculas sin tipo informado", file("WHATSAPP.MP4"), false],
  ["MP4 con tipo genérico admitido", file("reunion.mp4", 1024, "application/octet-stream"), false],
  ["MP4 con tipo incongruente rechazado", file("reunion.mp4", 1024, "image/png"), true],
  ["MP4 demasiado grande rechazado", file("reunion.mp4", MAX_AUDIO_BYTES + 1, "video/mp4"), true],
  ["MP4 con extensión doble rechazado", file("reunion.mp4.exe", 1024, "video/mp4"), true],
  ["Tipo no informado por navegador", file("a.mp3"), false],
];

for (const [name, input, invalid] of audioCases) {
  test(name, () => {
    assert.equal(Boolean(validateAudio(input)), invalid);
  });
}

const nameCases = [
  ["Nombre vacío", "  ", true],
  ["Nombre con acentos", "  Juan José  ", false],
  ["Nombre demasiado largo", "a".repeat(81), true],
];

for (const [name, input, invalid] of nameCases) {
  test(name, () => {
    assert.equal(Boolean(validateName(input)), invalid);
  });
}
