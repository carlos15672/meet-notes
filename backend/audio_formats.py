"""Formats accepted by both audio upload endpoints."""

MAX_AUDIO_BYTES = 100 * 1024 * 1024
ALLOWED_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".mp4"})
FORMAT_ERROR = "Selecciona un archivo MP3, WAV, M4A o MP4."
