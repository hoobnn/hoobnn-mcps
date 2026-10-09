import asyncio
import copy
import gzip
import json
import os
import struct
import tempfile
import time
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from doubao_speech_mcp import streaming_asr as asr


def response(payload, sequence=1, final=False, code=None):
    compressed = gzip.compress(json.dumps(payload).encode())
    kind = 15 if code is not None else 9
    header = bytes((0x11, (kind << 4) | (3 if final else 1), 0x11, 0))
    return (header + struct.pack(">i", -sequence if final else sequence)
            + (struct.pack(">I", code) if code is not None else b"")
            + struct.pack(">I", len(compressed)) + compressed)


class FakeSocket:
    def __init__(self, messages=(), wait=False, send_error=False):
        self.messages = iter(messages)
        self.sent = []
        self.wait = wait
        self.send_error = send_error
        self.closed = False
        self.cancelled = False
        self.response = SimpleNamespace(headers={"X-Tt-Logid": "test-log"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def send(self, frame):
        self.sent.append(frame)
        if self.send_error and len(self.sent) > 1:
            raise OSError("upload failed")

    async def recv(self):
        if self.wait:
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
        try:
            return next(self.messages)
        except StopIteration:
            await asyncio.Future()


class ProtocolTests(unittest.TestCase):
    def test_encode_sequence_gzip(self):
        frame = asr.encode_frame(b"pcm", 3, audio=True, final=True)
        self.assertEqual(frame[:4], b"\x11\x23\x01\x00")
        self.assertEqual(struct.unpack(">iI", frame[4:12]), (-3, len(frame) - 12))
        self.assertEqual(gzip.decompress(frame[12:]), b"pcm")

    def test_decode_final_and_full_result(self):
        payload = {"result": {"text": "你好", "utterances": [{"definite": True}]}, "extra": 1}
        decoded = asr.decode_frame(response(payload, 9, final=True))
        self.assertTrue(decoded["is_last_package"])
        self.assertEqual(decoded["payload_sequence"], -9)
        self.assertEqual(decoded["payload_msg"], payload)

    def test_without_sequence_and_error(self):
        raw = json.dumps({"result": {"text": "final"}}).encode()
        frame = b"\x11\x92\x10\x00" + struct.pack(">I", len(raw)) + raw
        self.assertTrue(asr.decode_frame(frame)["is_last_package"])
        self.assertEqual(asr.decode_frame(response({"message": "denied"}, code=45000001))["code"], 45000001)

    def test_truncated_and_invalid_frame(self):
        for frame in (b"x", "text", response({})[:-1], b"\x21\x90\x00\x00" + b"\0" * 4):
            with self.subTest(frame=frame):
                with self.assertRaises(asr.speech.InputError):
                    asr.decode_frame(frame)

    def test_wav_metadata_and_request_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.wav"
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x01\x00\x02\x00" * 100)
            request = {"user": {"uid": "test"}, "audio": {"language": "ja-JP", "rate": 1},
                       "request": {"enable_auto_lang": True, "corpus": {"custom": "preserved"}}}
            original = copy.deepcopy(request)
            body, pcm, alignment = asr.prepare_audio(str(path), request)
            self.assertEqual(request, original)
            self.assertEqual(body["audio"], {"language": "ja-JP", "rate": 16000,
                             "bits": 16, "channel": 2, "format": "pcm", "codec": "raw"})
            self.assertEqual(body["request"]["corpus"], {"custom": "preserved"})
            self.assertEqual(len(pcm), 400)
            self.assertEqual(alignment, 4)


class StreamingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "audio.pcm"
        self.path.write_bytes(b"\x00\x00" * 1600)
        self.env = patch.dict(os.environ, {"VOLC_SPEECH_API_KEY": "fake-key"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    async def test_both_modes_final_and_metadata(self):
        for mode, endpoint in asr.ENDPOINTS.items():
            socket = FakeSocket([response({"result": {"text": "interim"}}),
                                 response({"result": {"text": "final", "advanced": 2}}, 2, final=True)])
            with patch.object(asr, "websocket_connect", return_value=socket) as connect:
                result = await asr.streaming_recognize(str(self.path), {"request": {"result_type": "single"}}, mode)
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["text"], "final")
            self.assertEqual(result["response"]["result"]["advanced"], 2)
            self.assertEqual(len(result["messages"]), 2)
            self.assertEqual(result["logid"], "test-log")
            self.assertTrue(connect.call_args.args[0].endswith(endpoint))
            self.assertEqual(connect.call_args.kwargs["additional_headers"]["X-Api-Resource-Id"], asr.DEFAULT_RESOURCE)
            self.assertTrue(socket.closed)

    async def test_chunks_negative_final_and_concurrent_receive(self):
        self.path.write_bytes(b"\0\0" * 4000)
        socket = FakeSocket()
        async def recv():
            while len(socket.sent) < 3:
                await asyncio.sleep(0.001)
            return response({"result": {"text": "ok"}}, final=True)
        socket.recv = recv
        with patch.object(asr, "websocket_connect", return_value=socket):
            result = await asr.streaming_recognize(str(self.path), resource_id="custom")
        self.assertTrue(result["ok"])
        self.assertEqual([struct.unpack(">i", packet[4:8])[0] for packet in socket.sent], [1, 2, -3])
        self.assertEqual(len(gzip.decompress(socket.sent[1][12:])), 6400)
        self.assertEqual(len(gzip.decompress(socket.sent[2][12:])), 1600)

    async def test_timeout_cleans_tasks_and_socket(self):
        socket = FakeSocket(wait=True)
        with patch.object(asr, "websocket_connect", return_value=socket):
            result = await asr.streaming_recognize(str(self.path), timeout=0.02)
        self.assertFalse(result["ok"])
        self.assertIn("超时", result["error"])
        self.assertTrue(socket.cancelled)
        self.assertTrue(socket.closed)

    async def test_sender_failure_interrupts_receiver(self):
        socket = FakeSocket(wait=True, send_error=True)
        with patch.object(asr, "websocket_connect", return_value=socket):
            result = await asr.streaming_recognize(str(self.path), timeout=1)
        self.assertIn("upload failed", result["error"])
        self.assertTrue(socket.cancelled)
        self.assertTrue(socket.closed)

    async def test_server_error_preserved(self):
        socket = FakeSocket([response({"message": "quota"}, code=45000001)])
        with patch.object(asr, "websocket_connect", return_value=socket):
            result = await asr.streaming_recognize(str(self.path))
        self.assertFalse(result["ok"])
        self.assertIn("45000001", result["error"])
        self.assertEqual(result["messages"][0]["payload_msg"], {"message": "quota"})

    async def test_slow_prepare_obeys_entire_deadline_without_connecting(self):
        def slow_prepare(*args):
            time.sleep(0.12)
            return {}, b"\0\0", 2
        started = time.monotonic()
        with patch.object(asr, "prepare_audio", side_effect=slow_prepare), patch.object(asr, "websocket_connect") as connect:
            result = await asr.streaming_recognize(str(self.path), timeout=0.02)
        elapsed = time.monotonic() - started
        self.assertFalse(result["ok"])
        self.assertLess(elapsed, 0.10, f"slow preparation blocked cancellation for {elapsed:.3f}s")
        connect.assert_not_called()

    async def test_slow_decode_obeys_deadline_and_closes_connection(self):
        def slow_decode(frame):
            time.sleep(0.12)
            return {"message_type": 9, "payload_msg": {}, "is_last_package": True}
        socket = FakeSocket([response({})])
        started = time.monotonic()
        with patch.object(asr, "decode_frame", side_effect=slow_decode), patch.object(asr, "websocket_connect", return_value=socket):
            result = await asr.streaming_recognize(str(self.path), timeout=0.02)
        self.assertLess(time.monotonic() - started, 0.10)
        self.assertFalse(result["ok"])
        self.assertTrue(socket.closed)

    async def test_invalid_mode_and_pcm_no_network(self):
        with patch.object(asr, "websocket_connect") as connect:
            self.assertFalse((await asr.streaming_recognize(str(self.path), mode="invalid"))["ok"])
            self.path.write_bytes(b"x")
            self.assertFalse((await asr.streaming_recognize(str(self.path)))["ok"])
            connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
