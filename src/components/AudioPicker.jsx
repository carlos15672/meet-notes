import { useEffect, useRef, useState } from "react";
import { FileAudio, Upload, X } from "lucide-react";
import { AUDIO_ACCEPT, formatBytes, validateAudio } from "../lib/validation.js";

export default function AudioPicker({ file, onChange }) {
  const inputRef = useRef(null);
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  const [playbackError, setPlaybackError] = useState("");
  const [announcement, setAnnouncement] = useState("");

  useEffect(() => {
    setPlaybackError("");

    if (!file) {
      setSource("");
      return;
    }

    const url = URL.createObjectURL(file);
    setSource(url);

    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(event) {
    const candidate = event.target.files?.[0];

    // Cancelar el selector conserva el archivo anterior.
    if (!candidate) return;

    const message = validateAudio(candidate);

    if (message) {
      setError(
        message + (file ? " Se conservó el audio seleccionado anteriormente." : "")
      );
    } else {
      setError("");
      onChange(candidate);
      setAnnouncement("Archivo seleccionado: " + candidate.name);
    }

    // Permite seleccionar nuevamente el mismo archivo.
    event.target.value = "";
  }

  function removeFile() {
    onChange(null);
    setError("");
    setAnnouncement("Se quitó el audio seleccionado.");
    inputRef.current?.focus();
  }

  return (
    <section className="audio-section" aria-labelledby="audio-title">
      <h3 id="audio-title" className="sr-only">Seleccionar audio</h3>
      <p className="sr-only" id="audio-help">
        MP3, WAV, M4A o MP4 · Máximo 100 MB.
        Duración máxima: 45 minutos.
      </p>

      <div className={"upload-box" + (file ? " has-file" : "")}>
        <span className="icon-tile">
          <Upload size={26} aria-hidden="true" />
        </span>
        <p className="upload-title">
          {file ? "Audio seleccionado" : "Elige el audio de tu reunión"}
        </p>
        <p className="help">Busca el archivo en tu computadora.</p>

        <input
          ref={inputRef}
          id="meeting-audio"
          type="file"
          className="file-input"
          accept={AUDIO_ACCEPT}
          onChange={selectFile}
          aria-describedby={"audio-help" + (error ? " audio-error" : "")}
          aria-invalid={Boolean(error)}
        />
        <label htmlFor="meeting-audio" className="button secondary file-label">
          <Upload size={18} aria-hidden="true" />
          {file ? "Cambiar audio" : "Seleccionar audio"}
        </label>
      </div>

      {error && (
        <p className="error-message" id="audio-error" role="alert">
          {error}
        </p>
      )}

      {file && (
        <div className="selected-file">
          <div className="file-summary">
            <FileAudio size={24} aria-hidden="true" />
            <div className="file-description">
              <p className="file-name">{file.name}</p>
              <p className="help">{formatBytes(file.size)}</p>
            </div>
            <button
              type="button"
              className="icon-button"
              aria-label={"Quitar audio " + file.name}
              onClick={removeFile}
            >
              <X size={20} aria-hidden="true" />
            </button>
          </div>

          {source && (
            <audio
              key={source}
              controls
              preload="metadata"
              src={source}
              aria-label={"Escuchar grabación: " + file.name}
              onError={() => {
                setPlaybackError(
                  "Tu navegador no pudo reproducir la vista previa. Puedes intentar procesar el archivo."
                );
              }}
            />
          )}

          {playbackError && <p role="alert">{playbackError}</p>}
          <p className="help">
            Puedes escucharlo antes de procesar la reunión.
          </p>
        </div>
      )}

      <p className="sr-only" role="status" aria-live="polite">
        {announcement}
      </p>
    </section>
  );
}
