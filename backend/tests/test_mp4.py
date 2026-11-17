"""Real AAC/MP4 decoding and upload regression tests; no user files are changed."""
import io
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import av
import numpy as np

import test_workflow as workflow
from test_transcription import ROOT, upload
import database
import jobs
import jobs_service
import main
from faster_whisper.audio import decode_audio


def make_mp4(audio_path=None, video=False):
    """Encode an actual MP4, with AAC speech and/or MPEG-4 video."""
    buffer = io.BytesIO()
    with av.open(buffer, mode="w", format="mp4") as output:
        audio_stream = output.add_stream("aac", rate=16000) if audio_path else None
        video_stream = output.add_stream("mpeg4", rate=10) if video else None
        if audio_stream:
            audio_stream.layout = "mono"
        if video_stream:
            video_stream.width = 64
            video_stream.height = 48
            video_stream.pix_fmt = "yuv420p"
        if audio_stream:
            resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
            with av.open(str(audio_path)) as source:
                for frame in source.decode(audio=0):
                    for converted in resampler.resample(frame):
                        for packet in audio_stream.encode(converted):
                            output.mux(packet)
            for converted in resampler.resample(None):
                for packet in audio_stream.encode(converted):
                    output.mux(packet)
            for packet in audio_stream.encode(None):
                output.mux(packet)
        if video_stream:
            for index in range(10):
                frame = av.VideoFrame.from_ndarray(np.zeros((48, 64, 3), dtype=np.uint8), format="rgb24")
                frame.pts = index
                frame.time_base = Fraction(1, 10)
                for packet in video_stream.encode(frame):
                    output.mux(packet)
            for packet in video_stream.encode(None):
                output.mux(packet)
    return buffer.getvalue()


class Mp4Tests(unittest.TestCase):
    setUp = workflow.WorkflowTests.setUp
    tearDown = workflow.WorkflowTests.tearDown
    request = workflow.WorkflowTests.request

    @classmethod
    def setUpClass(cls):
        speech = ROOT / "samples" / "es_ganamos.wav"
        cls.audio_mp4 = make_mp4(speech)
        cls.video_mp4 = make_mp4(speech, video=True)
        cls.no_audio_mp4 = make_mp4(video=True)

    def post_job(self, data, filename="WhatsApp Audio.MP4", content_type="audio/mp4"):
        boundary = "Mp4RegressionBoundary"
        fields = {"request_id": str(uuid4()), "userName": "Carlos", "title": "Prueba MP4"}
        body = b""
        for name, value in fields.items():
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="{filename}"\r\n'
                 f'Content-Type: {content_type}\r\n\r\n').encode()
        body += data + f'\r\n--{boundary}--\r\n'.encode()
        return self.request("POST", "/api/trabajos", raw=body,
                            content_type="multipart/form-data; boundary=" + boundary)

    def test_mp4_audio_and_video_decodes_only_the_audio(self):
        audio = decode_audio(io.BytesIO(self.audio_mp4))
        with_video = decode_audio(io.BytesIO(self.video_mp4))
        self.assertGreater(len(audio), 16000)
        np.testing.assert_array_equal(audio, with_video)

    def test_real_whisper_transcribes_mp4_with_video(self):
        status, result = upload("WhatsApp Video.MP4", self.video_mp4)
        self.assertEqual(status, 200, result)
        self.assertIn("ganamos", result["texto"].lower())
        self.assertIn("partido", result["texto"].lower())
        self.assertTrue(result["segmentos"])

    def test_mp4_without_audio_returns_clear_error(self):
        status, result = upload("sin-sonido.mp4", self.no_audio_mp4)
        self.assertEqual(status, 422)
        self.assertIn("no contiene una pista de audio", result["detail"])

    def test_corrupt_mp4_is_not_accepted_as_audio(self):
        self.assertEqual(upload("corrupto.mp4", b"not an MP4")[0], 422)

    def test_main_job_route_accepts_audio_and_video_mp4(self):
        workspace = Path(self.temp.name) / "uploads"
        with patch.object(jobs, "WORK_ROOT", workspace), patch.object(jobs_service, "WORK_ROOT", workspace), \
             patch.object(jobs, "start_worker") as worker:
            for content, mime in ((self.audio_mp4, "audio/mp4"), (self.video_mp4, "video/mp4")):
                status, result = self.post_job(content, content_type=mime)
                self.assertEqual(status, 202, result)
                job = database.get_job(result["id"])
                self.assertEqual(job["file_name"], "WhatsApp Audio.MP4")
                saved = Path(job["input_path"])
                self.assertEqual(saved.suffix, ".mp4")
                self.assertEqual(saved.read_bytes(), content)
                database.update_job(job["id"], "listo", status="listo")
                jobs_service.clean_workspace(job["id"])
            self.assertEqual(worker.call_count, 2)

    def test_mp4_size_limit_still_applies_to_both_routes(self):
        with patch.object(main, "MAX_AUDIO_BYTES", 4):
            self.assertEqual(upload("grande.mp4", b"12345")[0], 413)
        workspace = Path(self.temp.name) / "uploads"
        with patch.object(jobs, "WORK_ROOT", workspace), patch.object(jobs_service, "WORK_ROOT", workspace), \
             patch.object(jobs, "MAX_AUDIO_BYTES", 4), patch.object(jobs, "start_worker") as worker:
            self.assertEqual(self.post_job(b"12345")[0], 413)
            worker.assert_not_called()
            self.assertEqual(list(workspace.iterdir()), [])
