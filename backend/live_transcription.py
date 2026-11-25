"""Incremental previews and a complete final transcript from aligned live PCM tracks."""
import threading
import wave
from pathlib import Path

import numpy as np

from live_audio import SAMPLE_RATE, mixed_samples, sample_count
from whisper_service import TranscriptionBusyError, transcribe_samples, transcribir_audio

WINDOW = 12 * SAMPLE_RATE
TAIL = int(1.5 * SAMPLE_RATE)


class LiveTranscriber:
    def __init__(self, directory, on_segments, on_error=None):
        self.directory = Path(directory)
        self.on_segments = on_segments
        self.on_error = on_error or (lambda error: None)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._cursor = 0
        self._committed_until = 0
        self._segments = []
        self.error = ""

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.wait(1):
            available = min(sample_count(self.directory, "sistema"), sample_count(self.directory, "microfono"))
            if available - self._cursor < WINDOW:
                continue
            end = self._cursor + WINDOW
            samples = mixed_samples(self.directory, self._cursor, end)
            try:
                segments, _, _ = transcribe_samples(samples)
            except TranscriptionBusyError:
                continue
            except Exception as exc:
                self.error = str(exc)
                self.on_error(self.error)
                continue
            stable = end - TAIL
            additions = [{"inicio": round(self._cursor / SAMPLE_RATE + item["inicio"], 2),
                          "fin": round(self._cursor / SAMPLE_RATE + item["fin"], 2),
                          "texto": item["texto"]} for item in segments
                         if self._committed_until < self._cursor + round(item["fin"] * SAMPLE_RATE) <= stable]
            self._segments.extend(additions)
            self._committed_until = stable
            self._cursor = max(0, stable - SAMPLE_RATE)
            self.on_segments(list(self._segments))


def final_transcription(directory):
    directory = Path(directory)
    total = max(sample_count(directory, "sistema"), sample_count(directory, "microfono"))
    if not total:
        raise ValueError("No se capturó audio. Comprueba los dispositivos y vuelve a intentarlo.")
    path = directory / "mezcla.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        for start in range(0, total, SAMPLE_RATE * 10):
            samples = mixed_samples(directory, start, min(total, start + SAMPLE_RATE * 10))
            output.writeframes((np.clip(samples * 32767, -32768, 32767).astype("<i2")).tobytes())
    return transcribir_audio(path)
