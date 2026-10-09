"""Offline protobuf and session tests; no paid API calls."""

import asyncio
import tempfile
import struct
import time
import threading
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from doubao_speech_mcp import interpretation as ast
from doubao_speech_mcp._ast.ast_service_pb2 import TranslateRequest, TranslateResponse
from doubao_speech_mcp._ast.events_pb2 import Type


def response(event, text="", data=b""):
    message = TranslateResponse(event=event, text=text, data=data)
    message.response_meta.SessionID = "session"
    if event == Type.UsageResponse:
        message.response_meta.Billing.DurationMsec = 80
    return message.SerializeToString()


class FakeConnection:
    def __init__(self, fail=False, stall=False, start_event=Type.SessionStarted, with_audio=False):
        self.queue = asyncio.Queue()
        self.sent = []
        self.closed = False
        self.fail = fail
        self.stall = stall
        self.start_event = start_event
        self.with_audio = with_audio
        self.response = SimpleNamespace(headers={"X-Tt-Logid": "test-log"})

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.closed = True

    async def send(self, raw):
        message = TranslateRequest()
        message.ParseFromString(raw)
        self.sent.append(message)
        if message.event == Type.StartSession:
            await self.queue.put(response(self.start_event))
        elif message.event == Type.TaskRequest:
            if self.fail:
                await self.queue.put(response(Type.SessionFailed))
            elif not self.stall:
                for event, text in [(Type.SourceSubtitleStart, ""),
                                    (Type.SourceSubtitleResponse, "你好"),
                                    (Type.SourceSubtitleEnd, ""),
                                    (Type.TranslationSubtitleStart, ""),
                                    (Type.TranslationSubtitleResponse, "Hello"),
                                    (Type.TranslationSubtitleEnd, "")]:
                    await self.queue.put(response(event, text))
                if self.with_audio:
                    await self.queue.put(response(Type.TTSResponse, data=b"\0\0" * 10))
        elif message.event == Type.FinishSession and not self.stall:
            await self.queue.put(response(Type.UsageResponse))
            await self.queue.put(response(Type.SessionFinished))

    async def recv(self):
        return await self.queue.get()


class EncodingTests(unittest.TestCase):
    def test_official_protobuf_roundtrip(self):
        payload = {"request_meta": {"SessionID": "my-session"}, "event": Type.TaskRequest,
                   "source_audio": {"binary_data": b"pcm"}}
        raw = ast.encode_request(payload)
        message = TranslateRequest()
        message.ParseFromString(raw)
        self.assertEqual(message.source_audio.binary_data, b"pcm")
        self.assertEqual(message.request_meta.SessionID, "my-session")
        self.assertEqual(payload["source_audio"]["binary_data"], b"pcm")

    def test_current_official_proto_language_fields_from_independent_wire(self):
        # Official ast_service.proto: event=2, speaker_id=9, detected_language=10,
        # language_confidence=11. The fixture is hand-encoded, not produced by our bindings.
        raw = b"\x10\x8c\x05\x4a\x01s\x52\x02zh\x59" + struct.pack("<d", .95)
        decoded = ast.decode_response(raw)
        self.assertEqual(decoded["event"], Type.SourceSubtitleEnd)
        self.assertEqual(decoded["speaker_id"], "s")
        self.assertEqual(decoded["detected_language"], "zh")
        self.assertAlmostEqual(decoded["language_confidence"], .95)
        encoded = ast.encode_request({"request": {"extra": "x", "enable_source_language_detect": True}})
        self.assertIn(b"\x82\x05\x01x", encoded)  # ReqParams.extra field number 80.

    def test_unknown_protobuf_field_rejected(self):
        with self.assertRaises(ast.speech.InputError):
            ast.encode_request({"guessed_field": 1})

    def test_decode_billing_and_audio(self):
        decoded = ast.decode_response(response(Type.UsageResponse))
        self.assertEqual(decoded["response_meta"]["Billing"]["DurationMsec"], "80")
        self.assertEqual(ast.decode_response(response(Type.TTSResponse, data=b"audio"))["data"], b"audio")

    def test_decode_text_frame_rejected(self):
        with self.assertRaises(ast.speech.InputError):
            ast.decode_response("{}")

    def test_wave_container_removed_and_format_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "audio.wav"
            for rate in (16000, 24000):
                with wave.open(str(audio), "wb") as source:
                    source.setnchannels(1)
                    source.setsampwidth(2)
                    source.setframerate(rate)
                    source.writeframes(b"\0\0" * 8)
                if rate == 16000:
                    self.assertEqual(ast.read_pcm(str(audio)), b"\0\0" * 8)
                else:
                    with self.assertRaises(ast.speech.InputError):
                        ast.read_pcm(str(audio))

    def test_initial_request_preserves_corpus_and_target(self):
        request = {"request": {"corpus": {"glossary_list": {"豆包": "Doubao"}}},
                   "target_audio": {"format": "ogg_opus"}}
        body = ast._start_request(request, "s", "zh", "en", "s2s")
        self.assertEqual(body["request"]["corpus"], request["request"]["corpus"])
        self.assertEqual(body["target_audio"]["rate"], 48000)
        self.assertNotIn("source_audio", request)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "input.pcm"
        self.path.write_bytes(b"\0\0" * 160)
        self.env = patch.dict(ast.os.environ, {"VOLC_SPEECH_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)

    async def test_session_orders_start_audio_finish_and_receives_usage(self):
        connection = FakeConnection()
        with patch.object(ast.websockets, "connect", return_value=connection) as connect:
            result = await ast.interpret_audio(str(self.path), "zh", "en", out_dir=Path(self.tmp.name))
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["source_text"], "你好")
        self.assertEqual(result["translation_text"], "Hello")
        self.assertEqual(result["usage"], [{"DurationMsec": "80"}])
        self.assertEqual([x.event for x in connection.sent], [100, 200, 102])
        self.assertEqual(connection.sent[1].source_audio.binary_data, self.path.read_bytes())
        self.assertEqual(connection.sent[0].source_audio.codec, "raw")
        self.assertEqual(connect.call_args.kwargs["additional_headers"]["X-Api-Key"], "test-key")
        self.assertTrue(connection.closed)

    async def test_speech_output_saved_as_valid_wave(self):
        connection = FakeConnection(with_audio=True)
        with patch.object(ast.websockets, "connect", return_value=connection):
            result = await ast.interpret_audio(str(self.path), "zh", "en", "s2s", out_dir=Path(self.tmp.name))
        self.assertTrue(result["ok"], result["error"])
        with wave.open(result["files"][0], "rb") as output:
            self.assertEqual((output.getframerate(), output.getsampwidth(), output.getnchannels()), (16000, 2, 1))
            self.assertEqual(output.readframes(output.getnframes()), b"\0\0" * 10)

    async def test_failed_server_cancels_sender_and_closes(self):
        connection = FakeConnection(fail=True)
        self.path.write_bytes(b"\0\0" * 16000)
        with patch.object(ast.websockets, "connect", return_value=connection):
            result = await ast.interpret_audio(str(self.path), "zh", "en", out_dir=Path(self.tmp.name))
        self.assertFalse(result["ok"])
        self.assertIn("SessionFailed", result["error"])
        self.assertEqual([x.event for x in connection.sent], [100, 200])
        self.assertTrue(connection.closed)
        self.assertEqual(result["files"], [])

    async def test_timeout_closes_connection(self):
        connection = FakeConnection(stall=True)
        with patch.object(ast.websockets, "connect", return_value=connection):
            result = await ast.interpret_audio(str(self.path), "zh", "en", timeout=.01)
        self.assertFalse(result["ok"])
        self.assertIn("超时", result["error"])
        self.assertTrue(connection.closed)

    async def test_start_rejected_does_not_send_audio(self):
        connection = FakeConnection(start_event=Type.SessionFailed)
        with patch.object(ast.websockets, "connect", return_value=connection):
            result = await ast.interpret_audio(str(self.path), "zh", "en")
        self.assertFalse(result["ok"])
        self.assertEqual([x.event for x in connection.sent], [100])
        self.assertTrue(connection.closed)

    async def test_detected_language_is_preserved_in_source_segments(self):
        original = response
        def tagged_response(event, text="", data=b""):
            raw = original(event, text, data)
            if event != Type.SourceSubtitleEnd:
                return raw
            message = TranslateResponse.FromString(raw)
            message.detected_language = "zh"
            message.language_confidence = .95
            message.speaker_id = "speaker"
            return message.SerializeToString()
        connection = FakeConnection()
        with patch.object(ast.websockets, "connect", return_value=connection), patch(__name__ + ".response", side_effect=tagged_response):
            result = await ast.interpret_audio(str(self.path), "zh", "en",
                request={"request": {"enable_source_language_detect": True}})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["source_segments"][0]["detected_language"], "zh")
        self.assertAlmostEqual(result["source_segments"][0]["language_confidence"], .95)
        self.assertEqual(result["source_segments"][0]["speaker_id"], "speaker")

    async def test_slow_pcm_read_can_be_cancelled_by_outer_deadline(self):
        def slow_read(*args):
            time.sleep(.12)
            return b"\0\0"
        started = time.monotonic()
        with patch.object(ast, "read_pcm", side_effect=slow_read), patch.object(ast.websockets, "connect") as connect:
            with self.assertRaises(asyncio.TimeoutError):
                await asyncio.wait_for(ast.interpret_audio(str(self.path), "zh", "en"), .02)
        self.assertLess(time.monotonic() - started, .10)
        connect.assert_not_called()

    async def test_audio_delivery_runs_in_worker_and_is_atomic(self):
        loop_thread = threading.get_ident()
        save = ast._save_audio
        def worker(*args):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            return save(*args)
        connection = FakeConnection(with_audio=True)
        with patch.object(ast.websockets, "connect", return_value=connection), patch.object(ast, "_save_audio", side_effect=worker):
            result = await ast.interpret_audio(str(self.path), "zh", "en", "s2s", out_dir=Path(self.tmp.name))
        self.assertTrue(result["ok"], result)
        self.assertEqual(list(Path(self.tmp.name).glob("*.tmp")), [])

    async def test_atomic_audio_publish_failure_does_not_report_success(self):
        connection = FakeConnection(with_audio=True)
        with patch.object(ast.websockets, "connect", return_value=connection), patch.object(
                ast.speech.os, "replace", side_effect=OSError("disk full")):
            result = await ast.interpret_audio(str(self.path), "zh", "en", "s2s", out_dir=Path(self.tmp.name))
        self.assertFalse(result["ok"])
        self.assertEqual(result["files"], [])
        self.assertEqual(list(Path(self.tmp.name).glob("interpretation*")), [])
        self.assertEqual(list(Path(self.tmp.name).glob("*.tmp")), [])

    async def test_invalid_input_never_connects(self):
        with patch.object(ast.websockets, "connect") as connect:
            result = await ast.interpret_audio(str(self.path), "zh", "en", "invalid")
        self.assertFalse(result["ok"])
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
