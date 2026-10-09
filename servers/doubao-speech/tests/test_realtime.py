"""Offline Seeduplex JSON contracts, lifecycle and audio extraction."""
import asyncio
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from doubao_speech_mcp import realtime


class FakeSocket:
    def __init__(self, ack=None):
        self.incoming = asyncio.Queue()
        self.incoming.put_nowait(json.dumps(ack or {"type": "session.created", "session": {"id": "remote"}}))
        self.sent = []
        self.closed = False

    async def send(self, raw):
        event = json.loads(raw)
        self.sent.append(event)
        if event["type"] == "session.close":
            self.incoming.put_nowait(json.dumps({"type": "session.closed"}))

    async def recv(self):
        return await self.incoming.get()

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.recv()

    async def close(self):
        self.closed = True


class RealtimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = realtime.RealtimeSessions()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.ws = FakeSocket()
        self.env = patch.dict('os.environ', {"VOLC_SPEECH_API_KEY": "test-key"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.transport = patch.object(realtime, "connect", new_callable=AsyncMock)
        self.connect = self.transport.start()
        self.connect.return_value = self.ws
        self.addCleanup(self.transport.stop)

    async def asyncTearDown(self):
        await self.manager.close_all()

    async def open(self):
        result = await self.manager.open({"audio": {"output": {"voice": "v"}}}, self.directory.name)
        self.assertTrue(result["ok"], result)
        return result["session_id"]

    async def test_defaults_extension_and_auth(self):
        session = {"audio": {"output": {"voice": "v"}}, "tools": [{"type": "function", "name": "f"}]}
        original = copy.deepcopy(session)
        result = await self.manager.open(session, self.directory.name, {"dialog": {"extra": {"enable_music": True}}})
        self.assertTrue(result["ok"])
        self.assertEqual(session, original)
        event = self.ws.sent[0]
        self.assertEqual(event["session"]["model"], "1.2.6.1")
        self.assertEqual(event["session"]["audio"]["output"]["format"], {"type": "pcm_s16le", "rate": 24000})
        self.assertTrue(event["extension"]["dialog"]["extra"]["enable_music"])
        self.assertEqual(self.connect.call_args.kwargs["additional_headers"], {"X-Api-Key": "test-key"})
        self.assertTrue(self.connect.call_args.args[0].endswith("/api/v3/duplex/realtime/dialogue"))

    async def test_validation_no_paid_request(self):
        for config in ({}, {"model": "wrong", "audio": {"output": {"voice": "v"}}}):
            result = await self.manager.open(config, self.directory.name)
            self.assertFalse(result["ok"])
        self.connect.assert_not_called()

    async def test_function_context_interrupt_raw_send(self):
        handle = await self.open()
        for event in [{"type": "response.cancel"}, {"type": "conversation.item.retrieve"},
                      {"type": "session.update", "session": {"tools": []}},
                      {"type": "conversation.item.create", "items": [{"role": "tool", "call_id": "c", "content": [{"type": "input_text", "text": "result"}]}]}]:
            result = await self.manager.send(handle, event)
            self.assertTrue(result["ok"])
            for key, value in event.items():
                self.assertEqual(self.ws.sent[-1][key], value)
            self.assertNotIn("event_id", event)

    async def test_audio_and_usage_preserved_without_base64(self):
        handle = await self.open()
        events = [{"type": "response.output_audio.delta", "delta": base64.b64encode(b"\x01\x02").decode()},
                  {"type": "response.output_audio.done"},
                  {"type": "response.output_text.delta", "delta": "你好"},
                  {"type": "response.function_call_arguments.done", "items": [{"call_id": "c", "arguments": "{}"}]},
                  {"type": "response.done", "usage": {"audio_tokens": 1}}]
        for event in events:
            self.ws.incoming.put_nowait(json.dumps(event))
        await asyncio.sleep(0)
        result = await self.manager.receive(handle)
        self.assertEqual(len(result["events"]), 5)
        delta = result["events"][0]
        self.assertNotIn("delta", delta)
        self.assertEqual(Path(delta["audio_file"]).read_bytes(), b"\x01\x02")
        self.assertEqual(result["events"][-1], events[-1])
        self.assertEqual(result["events"][-2], events[-2])

    async def test_graceful_close_cleans_reader_and_socket(self):
        handle = await self.open()
        state = self.manager.sessions[handle]
        result = await self.manager.close(handle)
        self.assertTrue(result["graceful"], result)
        self.assertNotIn(handle, self.manager.sessions)
        self.assertTrue(self.ws.closed)
        self.assertTrue(state.reader.done())

    async def test_open_error_closes_connection(self):
        self.ws = FakeSocket({"type": "error", "error": {"message": "denied"}})
        self.connect.return_value = self.ws
        result = await self.manager.open({"audio": {"output": {"voice": "v"}}}, self.directory.name)
        self.assertFalse(result["ok"])
        self.assertTrue(self.ws.closed)
        self.assertEqual(self.manager.sessions, {})

    async def test_pcm_file_chunks_and_invalid_extension(self):
        handle = await self.open()
        path = Path(self.directory.name) / "input.pcm"
        path.write_bytes(b"\x00" * 1280)
        with patch.object(realtime.asyncio, "sleep", return_value=None) as sleep:
            result = await self.manager.send(handle, {"type": "input_audio_buffer.append"}, str(path))
        self.assertTrue(result["ok"])
        self.assertEqual(result["chunks"], 2)
        self.assertEqual(len(base64.b64decode(self.ws.sent[-1]["audio"])), 640)
        self.assertEqual(sleep.call_args.args, (0.02,))
        self.assertFalse((await self.manager.send(handle, {"type": "response.cancel"}, str(path)))["ok"])

    async def test_timeout_does_not_close_live_session(self):
        handle = await self.open()
        result = await self.manager.receive(handle, timeout=0.01)
        self.assertEqual(result["events"], [])
        self.assertFalse(result["closed"])
        self.assertTrue((await self.manager.send(handle, {"type": "input_audio_mute.commit"}))["ok"])

    async def test_malformed_event_stops_and_closes_reader(self):
        handle = await self.open()
        self.ws.incoming.put_nowait("not json")
        result = await self.manager.receive(handle)
        self.assertFalse(result["ok"])
        self.assertTrue(result["closed"])
        self.assertTrue(self.ws.closed)

    async def test_close_timeout_still_releases_socket(self):
        handle = await self.open()
        async def no_ack(raw):
            self.ws.sent.append(json.loads(raw))
        self.ws.send = no_ack
        result = await self.manager.close(handle, timeout=0.01)
        self.assertFalse(result["ok"])
        self.assertTrue(self.ws.closed)
        self.assertNotIn(handle, self.manager.sessions)

    async def test_cancelled_open_does_not_leak_reservation(self):
        started = asyncio.Event()
        async def pending(*args, **kwargs):
            started.set()
            await asyncio.Event().wait()
        self.connect.side_effect = pending
        task = asyncio.create_task(self.manager.open({"audio": {"output": {"voice": "v"}}}, self.directory.name))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.manager.sessions, {})

    async def test_interrupt_during_stream_does_not_wait_for_whole_audio(self):
        handle = await self.open()
        path = Path(self.directory.name) / "stream.pcm"
        path.write_bytes(b"\x00" * 6400)
        first_packet = asyncio.Event()
        resume = asyncio.Event()
        async def pause(_):
            first_packet.set()
            await resume.wait()
        with patch.object(realtime.asyncio, "sleep", side_effect=pause):
            stream = asyncio.create_task(self.manager.send(handle, {"type": "input_audio_buffer.append"}, str(path)))
            await first_packet.wait()
            interrupt = await asyncio.wait_for(self.manager.send(handle, {"type": "response.cancel"}), 0.1)
            self.assertTrue(interrupt["ok"])
            self.assertEqual(self.ws.sent[-1]["type"], "response.cancel")
            stream.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await stream

    async def test_error_event_is_reported_and_connection_closed(self):
        handle = await self.open()
        event = {"type": "error", "error": {"code": 42000020, "message": "invalid option"}}
        self.ws.incoming.put_nowait(json.dumps(event))
        result = await self.manager.receive(handle)
        self.assertFalse(result["ok"])
        self.assertEqual(result["events"], [event])
        self.assertTrue(result["closed"])
        self.assertTrue(self.ws.closed)

    async def test_interrupted_audio_starts_new_output_file(self):
        handle = await self.open()
        chunk = {"type": "response.output_audio.delta", "delta": base64.b64encode(b"ab").decode()}
        for event in [chunk, {"type": "response.canceled"}, chunk, {"type": "response.output_audio.done"}]:
            self.ws.incoming.put_nowait(json.dumps(event))
        await asyncio.sleep(0)
        result = await self.manager.receive(handle)
        first = result["events"][0]["audio_file"]
        second = result["events"][2]["audio_file"]
        self.assertNotEqual(first, second)
        self.assertEqual(Path(first).read_bytes(), b"ab")
        self.assertEqual(Path(second).read_bytes(), b"ab")


if __name__ == "__main__":
    unittest.main()
