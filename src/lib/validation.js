export const MAX_AUDIO_BYTES = 100 * 1024 * 1024;
export const AUDIO_ACCEPT = ".mp3,.wav,.m4a,.mp4";

const AUDIO_TYPES = {
  mp3: ["audio/mpeg", "audio/mp3"],
  wav: ["audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"],
  m4a: ["audio/mp4", "audio/x-m4a", "audio/m4a", "video/mp4"],
  mp4: ["audio/mp4", "video/mp4", "application/mp4"],
};

export function validateAudio(file) {
  if (!file) return "Selecciona un archivo de audio.";

  if (!Number.isFinite(file.size) || file.size <= 0) {
    return "El archivo está vacío o su tamaño no es válido.";
  }

  if (file.size > MAX_AUDIO_BYTES) {
    return "El audio supera el límite de 100 MB.";
  }

  const extension = file.name.toLowerCase().split(".").pop();

  if (!Object.hasOwn(AUDIO_TYPES, extension)) {
    return "Elige un archivo MP3, WAV, M4A o MP4.";
  }

  const type = (file.type || "").toLowerCase();

  if (
    type &&
    type !== "application/octet-stream" &&
    !AUDIO_TYPES[extension].includes(type)
  ) {
    return "El tipo de archivo no coincide con su extensión. Selecciona otro audio.";
  }

  return "";
}

export function validateName(value) {
  const name = value.trim();

  if (!name) return "Escribe el nombre que se menciona en la reunión.";
  if (name.length > 80) return "Usa un nombre de hasta 80 caracteres.";

  return "";
}

export function formatBytes(bytes) {
  const isMB = bytes >= 1024 * 1024;
  const value = bytes / (isMB ? 1024 * 1024 : 1024);

  return (
    value.toLocaleString("es-MX", { maximumFractionDigits: 1 }) +
    (isMB ? " MB" : " KB")
  );
}
