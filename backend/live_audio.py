"""Two-track Windows capture: speaker loopback and microphone, stored as 16 kHz PCM."""
import os
import threading
from pathlib import Path

import av
import numpy as np

SAMPLE_RATE = 16000
MAX_SECONDS = 45 * 60
TRACKS = ("sistema", "microfono")


class CaptureError(RuntimeError):
    pass


def _pyaudio():
    if os.name != "nt":
        raise CaptureError("La captura en vivo requiere Windows.")
    try:
        import pyaudiowpatch
        return pyaudiowpatch
    except ImportError as exc:
        raise CaptureError("Falta PyAudioWPatch. Instala backend/requirements.txt.") from exc


def devices():
    pa = _pyaudio()
    with pa.PyAudio() as audio:
        loopback = audio.get_default_wasapi_loopback()
        microphone = audio.get_default_input_device_info()
        inputs = []
        for index in range(audio.get_device_count()):
            item = audio.get_device_info_by_index(index)
            if item["maxInputChannels"] > 0:
                inputs.append({"id": index, "nombre": item["name"],
                               "tipo": "sistema" if item.get("isLoopbackDevice") else "microfono"})
        return {"dispositivos": inputs, "sistema_predeterminado": loopback["index"],
                "microfono_predeterminado": microphone["index"]}


def pcm_path(directory, track):
    if track not in TRACKS:
        raise ValueError("Pista inválida.")
    return Path(directory) / (track + ".pcm")


def sample_count(directory, track):
    path = pcm_path(directory, track)
    return path.stat().st_size // 2 if path.exists() else 0


def read_track(directory, track, start, end):
    """Return a zero-padded float32 window from an aligned PCM track."""
    count = max(0, end - start)
    result = np.zeros(count, dtype=np.float32)
    path = pcm_path(directory, track)
    if not path.exists() or not count:
        return result
    with path.open("rb") as source:
        source.seek(start * 2)
        data = np.frombuffer(source.read(count * 2), dtype="<i2")
    result[:len(data)] = data.astype(np.float32) / 32768.0
    return result


def mixed_samples(directory, start, end):
    system = read_track(directory, "sistema", start, end)
    microphone = read_track(directory, "microfono", start, end)
    # Limit peaks when both streams contain sound at the same time.
    return np.clip(system + microphone, -1.0, 1.0)


class AudioCapture:
    def __init__(self, directory, system_id=None, microphone_id=None, on_error=None):
        self.directory = Path(directory)
        self.system_id = system_id
        self.microphone_id = microphone_id
        self.on_error = on_error or (lambda error: None)
        self.error = None
        self._stop = threading.Event()
        self._threads = []
        self._audio = None

    def start(self):
        pa = _pyaudio()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._stop.clear()
        self.error = None
        self._audio = pa.PyAudio()
        try:
            defaults = (self._audio.get_default_wasapi_loopback()["index"] if self.system_id is None else self.system_id,
                        self._audio.get_default_input_device_info()["index"] if self.microphone_id is None else self.microphone_id)
            opened = []
            for track, chosen, default in zip(TRACKS, (self.system_id, self.microphone_id), defaults):
                device = self._audio.get_device_info_by_index(default if chosen is None else chosen)
                if (device["maxInputChannels"] < 1
                        or (track == "sistema" and not device.get("isLoopbackDevice"))
                        or (track == "microfono" and device.get("isLoopbackDevice"))):
                    raise CaptureError("Selecciona una salida loopback y un micrófono válidos.")
                channels = min(2, int(device["maxInputChannels"]))
                rate = int(device["defaultSampleRate"])
                stream = self._audio.open(format=pa.paInt16, channels=channels, rate=rate, input=True,
                    input_device_index=device["index"], frames_per_buffer=max(256, rate // 10), start=False)
                opened.append((track, stream, channels, rate))
            for _, stream, _, _ in opened:
                stream.start_stream()
            for track, stream, channels, rate in opened:
                thread = threading.Thread(target=self._read, args=(track, stream, channels, rate), daemon=True)
                self._threads.append(thread)
                thread.start()
        except Exception:
            self.stop()
            raise

    def _read(self, track, stream, channels, rate):
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        try:
            with pcm_path(self.directory, track).open("ab", buffering=0) as output:
                while not self._stop.is_set():
                    raw = stream.read(max(256, rate // 10), exception_on_overflow=False)
                    samples = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
                    mono = np.mean(samples, axis=1).astype(np.int16).reshape(1, -1)
                    frame = av.AudioFrame.from_ndarray(mono, format="s16", layout="mono")
                    frame.sample_rate = rate
                    for converted in resampler.resample(frame):
                        output.write(converted.to_ndarray().tobytes())
                    if sample_count(self.directory, track) >= SAMPLE_RATE * MAX_SECONDS:
                        raise CaptureError("Se alcanzó el límite de 45 minutos de captura.")
                for converted in resampler.resample(None):
                    output.write(converted.to_ndarray().tobytes())
        except Exception as exc:
            if not self._stop.is_set():
                self.error = CaptureError(f"Se interrumpió la captura de {track}: {exc}")
                self._stop.set()
                self.on_error(self.error)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except OSError:
                pass

    def stop(self):
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=3)
        self._threads.clear()
        if self._audio is not None:
            self._audio.terminate()
            self._audio = None
        # Each stream may finish one buffer later. Pad the shorter track so both
        # next capture segments start at the same timeline position.
        counts = [sample_count(self.directory, track) for track in TRACKS]
        longest = max(counts)
        for track, count in zip(TRACKS, counts):
            if count < longest:
                with pcm_path(self.directory, track).open("ab") as output:
                    output.write(b"\0\0" * (longest - count))
        return longest / SAMPLE_RATE
