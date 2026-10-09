"""Offline checks against official event-frame layouts and full fake sessions."""

import asyncio
import gzip
import json
import struct
import tempfile
import time
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from doubao_speech_mcp import speech, ws_products as ws


def server_frame(event=None, payload=None, *, kind=9, sequence=None, compression=0,
                 serialization=1, error_code=None, header_size=1):
    """Official layout: header, sequence/error OR event+ID, length, payload."""
    if payload is None:
        payload = {}
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    if compression == 1:
        data = gzip.compress(data)
    flags = 4 if event is not None else (3 if sequence is not None and sequence < 0 else 1 if sequence is not None else 0)
    packet = bytes([(1 << 4) | header_size, (kind << 4) | flags,
                    (serialization << 4) | compression, 0]) + b"\0" * (header_size * 4 - 4)
    if error_code is not None:
        packet += struct.pack(">I", error_code)
    elif sequence is not None:
        packet += struct.pack(">i", sequence)
    if event is not None:
        packet += struct.pack(">i", event)
        if event not in {1, 2}:
            identifier = b"connection" if event in {50, 51, 52} else b"session"
            packet += struct.pack(">I", len(identifier)) + identifier
    return packet + struct.pack(">I", len(data)) + data


class FrameTests(unittest.TestCase):
    def test_start_connection_has_no_session_id(self):
        frame = ws.frame(event=1)
        self.assertEqual(frame[:8], bytes([0x11, 0x14, 0x10, 0]) + struct.pack(">i", 1))
        self.assertEqual(frame[8:], struct.pack(">I", 2) + b"{}")

    def test_session_frame_preserves_utf8_and_id(self):
        parsed = ws.parse_frame(ws.frame({"text": "你好"}, 100, "my-session"))
        self.assertEqual(parsed["session_id"], "my-session")
        self.assertEqual(parsed["data"], {"text": "你好"})

    def test_connection_response_has_connection_id(self):
        for event in (50, 52):
            parsed = ws.parse_frame(server_frame(event))
            self.assertEqual(parsed["connection_id"], "connection")
            self.assertNotIn("session_id", parsed)

    def test_gzip_json_and_audio(self):
        parsed = ws.parse_frame(server_frame(154, {"usage": {"text_words": 2}}, compression=1))
        self.assertEqual(parsed["data"]["usage"]["text_words"], 2)
        for event in (352, 361):
            parsed = ws.parse_frame(server_frame(event, b"raw audio", kind=11, compression=1))
            self.assertEqual(parsed["payload"], b"raw audio")
            self.assertNotIn("data", parsed)

    def test_extended_header_and_negative_sequence(self):
        parsed = ws.parse_frame(server_frame(sequence=-3, payload=b"pcm", kind=11,
                                             serialization=0, header_size=2))
        self.assertEqual(parsed["sequence"], -3)
        self.assertEqual(parsed["payload"], b"pcm")

    def test_truncation_at_every_boundary(self):
        packet = server_frame(360, {"text": "round"})
        for length in range(len(packet)):
            with self.subTest(length=length), self.assertRaises(speech.InputError):
                ws.parse_frame(packet[:length])

    def test_server_error_preserves_code_even_for_non_json(self):
        with self.assertRaisesRegex(speech.InputError, "45000000.*denied"):
            ws.parse_frame(server_frame(payload=b"denied", kind=15, error_code=45000000))
        for event in (51, 153):
            with self.subTest(event=event), self.assertRaisesRegex(speech.InputError, "服务端错误"):
                ws.parse_frame(server_frame(event, {"message": "failed"}))

    def test_invalid_compression_json_and_extra_bytes(self):
        cases = [server_frame(154, b"invalid json"), server_frame(154, {}) + b"extra",
                 server_frame(154, {}, compression=2),
                 bytes([0x11, 0x94, 0x31, 0]) + server_frame(154, {})[4:],
                 server_frame(154, {})[:2] + bytes([0x11]) + server_frame(154, {})[3:]]
        for packet in cases:
            with self.subTest(packet=packet[:4]), self.assertRaises(speech.InputError):
                ws.parse_frame(packet)
        with self.assertRaises(speech.InputError):
            ws.parse_frame("text frame")


class FakeWebSocket:
    def __init__(self, product="tts", *, failure=None, only_text=False):
        self.queue = asyncio.Queue()
        self.product = product
        self.failure = failure
        self.only_text = only_text
        self.sent = []
        self.closed = False
        self.response = SimpleNamespace(headers={"X-Tt-Logid": "fake-log"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def send(self, raw):
        parsed = ws.parse_frame(raw)
        self.sent.append(parsed)
        event = parsed["event"]
        if event == 1:
            await self.queue.put(server_frame(50))
        elif event == 2:
            await self.queue.put(server_frame(52))
        elif event == 100:
            await self.queue.put(server_frame(150))
            if self.product == "podcast":
                await self.queue.put(server_frame(360, {"round_id": 0, "speaker": "voice", "text": "hello"}))
                if not self.only_text:
                    await self.queue.put(server_frame(361, b"podcast audio", kind=11))
                if self.failure == "disconnect":
                    await self.queue.put(server_frame(153, {"message": "disconnected"}))
                elif self.failure == "round":
                    await self.queue.put(server_frame(362, {"is_error": True, "error_msg": "round failed"}))
                else:
                    await self.queue.put(server_frame(362, {"audio_duration": 1.2, "start_time": 0, "end_time": 1.2}))
                    await self.queue.put(server_frame(154, {"usage": {"output_audio_tokens": 10}}))
                    await self.queue.put(server_frame(363, {"meta_info": {"topics": ["topic"]}}))
                    await self.queue.put(server_frame(152, {"status_code": 20000000}))
        elif event == 200:
            if self.failure == "send":
                raise OSError("send failed")
            await self.queue.put(server_frame(352, b"tts audio", kind=11))
        elif event == 102 or event is None:
            if event is None:
                await self.queue.put(server_frame(352, b"tts audio", kind=11))
            await self.queue.put(server_frame(152, {"status_code": 55000000 if self.failure == "finished" else 20000000}))

    async def recv(self):
        return await self.queue.get()


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.output = Path(self.tmp.name)
        self.env = patch.dict(ws.os.environ, {"VOLC_SPEECH_API_KEY": "offline-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.tts_body = {"req_params": {"text": "你好", "speaker": "voice",
                         "audio_params": {"format": "mp3", "sample_rate": 24000}}}

    async def test_complete_bidirectional_tts(self):
        fake = FakeWebSocket()
        with patch.object(ws.websockets, "connect", return_value=fake):
            result = await ws.synthesize(self.tts_body, self.output, text_chunks=["你好", "世界"])
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"tts audio" * 2)
        self.assertEqual([packet["event"] for packet in fake.sent], [1, 100, 200, 200, 102, 2])
        self.assertNotIn("text", fake.sent[1]["data"]["req_params"])
        self.assertEqual(fake.sent[2]["data"]["req_params"]["text"], "你好")
        self.assertEqual(self.tts_body["req_params"]["text"], "你好")
        self.assertTrue(fake.closed)

    async def test_complete_unidirectional_tts(self):
        fake = FakeWebSocket()
        with patch.object(ws.websockets, "connect", return_value=fake):
            result = await ws.synthesize(self.tts_body, self.output, mode="unidirectional")
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual([packet["event"] for packet in fake.sent], [None])
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"tts audio")
        self.assertTrue(fake.closed)

    async def test_failed_finished_status_does_not_report_success(self):
        fake = FakeWebSocket(failure="finished")
        with patch.object(ws.websockets, "connect", return_value=fake):
            result = await ws.synthesize(self.tts_body, self.output)
        self.assertFalse(result["ok"])
        self.assertIn("55000000", result["error"])
        self.assertEqual(result["files"], [])
        self.assertTrue(fake.closed)

    async def test_sender_failure_returns_without_waiting_receive_timeout(self):
        fake = FakeWebSocket(failure="send")
        with patch.object(ws.websockets, "connect", return_value=fake):
            result = await asyncio.wait_for(ws.synthesize(self.tts_body, self.output), .5)
        self.assertFalse(result["ok"])
        self.assertIn("send failed", result["error"])
        self.assertTrue(fake.closed)

    async def test_podcast_begins_with_start_session_and_finishes_connection(self):
        fake = FakeWebSocket("podcast")
        with patch.object(ws.websockets, "connect", return_value=fake) as connect:
            result = await ws.podcast({"action": 0, "input_text": "科技"}, self.output)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual([packet["event"] for packet in fake.sent], [100, 2])
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"podcast audio")
        self.assertEqual(result["last_finished_round_id"], 0)
        self.assertEqual(result["rounds"][0]["timing"]["audio_duration"], 1.2)
        self.assertEqual(result["usage"][0]["usage"]["output_audio_tokens"], 10)
        self.assertEqual(connect.call_args.kwargs["additional_headers"]["X-Api-Resource-Id"], "volc.service_type.10050")
        self.assertTrue(fake.closed)

    async def test_podcast_text_only(self):
        fake = FakeWebSocket("podcast", only_text=True)
        with patch.object(ws.websockets, "connect", return_value=fake):
            result = await ws.podcast({"input_text": "科技", "input_info": {"only_nlp_text": True}}, self.output)
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["files"], [])

    async def test_podcast_failure_preserves_explicit_partial_audio(self):
        for failure in ("disconnect", "round"):
            with self.subTest(failure=failure):
                fake = FakeWebSocket("podcast", failure=failure)
                with patch.object(ws.websockets, "connect", return_value=fake):
                    result = await ws.podcast({"input_text": "科技"}, self.output)
                self.assertFalse(result["ok"])
                self.assertIn(".partial.", result["files"][0])
                self.assertEqual(Path(result["files"][0]).read_bytes(), b"podcast audio")
                self.assertTrue(fake.closed)

    async def test_podcast_save_failure_is_structured_error(self):
        fake = FakeWebSocket("podcast")
        with patch.object(ws.websockets, "connect", return_value=fake), \
                patch.object(ws.speech, "_atomic_bytes", side_effect=OSError("disk full")):
            result = await ws.podcast({"input_text": "科技"}, self.output)
        self.assertFalse(result["ok"])
        self.assertIn("disk full", result["error"])
        self.assertEqual(result["files"], [])

    async def test_large_audio_delivery_does_not_block_cancellation(self):
        def slow_write(*args):
            time.sleep(.12)
        fake = FakeWebSocket()
        started = time.monotonic()
        with patch.object(ws.websockets, "connect", return_value=fake), patch.object(ws.speech, "_atomic_bytes", side_effect=slow_write):
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ws.synthesize(self.tts_body, self.output), .02)
        self.assertLess(time.monotonic() - started, .10)
        self.assertTrue(fake.closed)

    async def test_atomic_audio_writer_runs_in_worker_and_no_partial_file_leaks(self):
        loop_thread = threading.get_ident()
        writer = ws.speech._atomic_bytes
        def worker(*args):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return writer(*args)
        for product in ("tts", "podcast"):
            fake = FakeWebSocket(product)
            with patch.object(ws.websockets, "connect", return_value=fake), patch.object(ws.speech, "_atomic_bytes", side_effect=worker):
                if product == "tts":
                    result = await ws.synthesize(self.tts_body, self.output)
                else:
                    result = await ws.podcast({"input_text": "hi"}, self.output)
            self.assertTrue(result["ok"], result)
        self.assertEqual(list(self.output.glob("*.tmp")), [])

    async def test_atomic_publish_failure_leaves_no_tts_or_temporary_file(self):
        fake = FakeWebSocket()
        with patch.object(ws.websockets, "connect", return_value=fake), patch.object(ws.speech.os, "replace", side_effect=OSError("disk full")):
            result = await ws.synthesize(self.tts_body, self.output)
        self.assertFalse(result["ok"])
        self.assertEqual(result["files"], [])
        self.assertEqual(list(self.output.iterdir()), [])

    async def test_invalid_requests_fail_before_connect(self):
        with patch.object(ws.websockets, "connect") as connect:
            cases = [await ws.synthesize({"req_params": "bad"}, self.output),
                     await ws.synthesize(self.tts_body, self.output, text_chunks="bad"),
                     await ws.podcast({"input_text": "hi", "audio_config": []}, self.output),
                     await ws.podcast({"action": 3, "nlp_texts": []}, self.output)]
        self.assertTrue(all(not result["ok"] for result in cases))
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
