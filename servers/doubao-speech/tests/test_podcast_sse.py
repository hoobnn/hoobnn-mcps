"""Offline HTTP SSE wire contracts and complete-round resume; no paid calls."""
import asyncio
import base64
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from doubao_speech_mcp import podcast, server


def event(number, payload=None, **fields):
    message = {"code": 0, "payload": payload or {}, **fields}
    return f"event: {number}\r\ndata: {json.dumps(message, ensure_ascii=False)}\r\n\r\n".encode()


def round_events(number=0, audio=b"complete"):
    return (event(360, {"round_id": number, "text": "你好", "speaker": "voice"})
            + event(361, data=base64.b64encode(audio).decode())
            + event(362, {"round_id": number, "audio_duration": 1.0}))


class Response(io.BytesIO):
    def __init__(self, raw, content_type="text/event-stream; charset=utf-8", status=200):
        super().__init__(raw)
        self.status = status
        self.headers = {"Content-Type": content_type, "X-Tt-Logid": "log", "X-Api-Request-Id": "server-request"}


class PodcastSSETests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        env = patch.dict("os.environ", {"VOLC_SPEECH_API_KEY": "test"})
        env.start()
        self.addCleanup(env.stop)

    def generate(self, raw, request=None, **response_args):
        response = Response(raw, **response_args)
        with patch.object(podcast.transport, "urlopen", return_value=response) as transport:
            result = podcast.generate(request or {"input_text": "文章"}, self.directory.name)
        self.assertTrue(response.closed)
        return result, transport

    def test_sse_comments_multiline_bom_crlf_and_unknown_fields(self):
        raw = ("\ufeff:keep-alive\r\n\r\nid: ignored\r\nretry: 1000\r\nevent: 150\r\n"
               'data: {"session_id":\r\ndata: "remote", "code": 0}\r\n\r\n').encode()
        self.assertEqual(list(podcast.sse_events(Response(raw))), [(150, {"session_id": "remote", "code": 0})])
        self.assertEqual(list(podcast.sse_events(Response(b'event: 152\ndata: {"code":20000000}'))), [])

    def test_success_requires_terminal_code_and_retains_usage_meta_and_real_id(self):
        raw = (event(150, session_id="real-session") + round_events()
               + event(363, {"meta_info": {"audio_url": "https://example.com/a"}})
               + event(154, {"usage": {"audio_tokens": 2}}) + b":keep-alive\n\n"
               + event(154, {"usage": {"audio_tokens": 1}}) + event(152, code=20000000))
        result, transport = self.generate(raw)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["task_id"], "real-session")
        self.assertEqual(result["session_id"], "real-session")
        self.assertEqual(result["request_id"], "server-request")
        self.assertEqual(result["last_finished_round_id"], 0)
        self.assertEqual(len(result["usage"]), 2)
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"complete")
        req = transport.call_args.args[0]
        self.assertTrue(req.full_url.endswith("/api/v3/podcast/sse"))
        self.assertEqual(dict(req.header_items())["Accept"], "text/event-stream")
        self.assertEqual(dict(req.header_items())["X-api-resource-id"], "volc.service_type.10050")
        transport.assert_called_once()

    def test_http_200_or_podcast_end_or_usage_never_proves_success(self):
        for ending in (b"", event(363), event(154, {"usage": {}})):
            with self.subTest(ending=ending):
                result, _ = self.generate(event(150, session_id="real") + round_events() + ending)
                self.assertFalse(result["ok"])
                self.assertEqual(result["state"], "incomplete")
                self.assertIn(".partial.", result["files"][0])
                self.assertEqual(Path(result["files"][0]).read_bytes(), b"complete")

    def test_missing_zero_or_failed_terminal_code_is_not_success(self):
        for code in (None, 0, 55000000):
            with self.subTest(code=code):
                result, _ = self.generate(event(150, session_id="real") + round_events() + event(152, code=code))
                self.assertFalse(result["ok"])
                self.assertEqual(result["code"], code)
                self.assertEqual(result["state"], "failed")

    def test_canceled_failed_and_disconnect_keep_only_complete_rounds(self):
        beginning = (event(150, session_id="real") + round_events(0)
                     + event(360, {"round_id": 1}) + event(361, data=base64.b64encode(b"unfinished").decode()))
        for terminal, state in ((b"", "incomplete"), (event(151, message="cancel"), "canceled"),
                                (event(153, code=55000000, message="failed"), "failed"),
                                (event(362, {"round_id": 1, "is_error": True, "error_msg": "round failed"}), "failed")):
            with self.subTest(state=state):
                result, _ = self.generate(beginning + terminal)
                self.assertFalse(result["ok"])
                self.assertEqual(result["state"], state)
                self.assertEqual(Path(result["files"][0]).read_bytes(), b"complete")
                self.assertEqual(Path(result["diagnostic_file"]).read_bytes(), b"unfinished")
                self.assertEqual(result["discarded_bytes"], 10)
                self.assertEqual([row["round_id"] for row in result["rounds"]], [0])
                self.assertEqual(result["last_finished_round_id"], 0)
                self.assertEqual(result["unfinished_round"]["round_id"], 1)
                self.assertEqual(result["retry_info"], {"retry_task_id": "real", "last_finished_round_id": 0})

    def test_resume_preserves_original_task_and_request_parameters(self):
        request = {"input_text": "文章", "speaker_info": {"speakers": ["a", "b"]},
                   "retry_info": {"retry_task_id": "FIRST", "last_finished_round_id": 8}}
        original = copy.deepcopy(request)
        result, transport = self.generate(event(150, session_id="NEW") + round_events(9) + event(152, code=20000000), request)
        self.assertTrue(result["ok"], result)
        self.assertEqual(request, original)
        self.assertEqual(result["task_id"], "FIRST")
        self.assertEqual(result["session_id"], "NEW")
        self.assertEqual(result["retry_info"], {"retry_task_id": "FIRST", "last_finished_round_id": 9})
        self.assertEqual(json.loads(transport.call_args.args[0].data)["retry_info"], original["retry_info"])

    def test_script_only_and_unfinished_script_round(self):
        result, _ = self.generate(event(150, session_id="real") + event(360, {"round_id": 0, "text": "脚本"})
                                  + event(362) + event(152, code=20000000),
                                  {"input_text": "文章", "input_info": {"only_nlp_text": True}})
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["files"], [])
        result, _ = self.generate(event(150, session_id="real") + event(360, {"round_id": 0}) + event(152, code=20000000))
        self.assertFalse(result["ok"])
        self.assertIsNone(result["last_finished_round_id"])

    def test_invalid_base64_missing_session_and_wrong_content_type_fail_closed(self):
        for raw in (event(150) + event(152, code=20000000),
                    event(150, session_id="real") + event(360, {"round_id": 0}) + event(361, data="??"),
                    event(150, session_id="real") + event(362)):
            with self.subTest(raw=raw):
                result, _ = self.generate(raw)
                self.assertFalse(result["ok"])
                self.assertEqual(result["files"], [])
        for args in ({"content_type": "application/json"}, {"status": 201}):
            result, _ = self.generate(event(152, code=20000000), **args)
            self.assertFalse(result["ok"])
            self.assertIn("text/event-stream", result["error"])

    def test_invalid_requests_never_dispatch(self):
        requests = [{"input_text": "x", "audio_config": []}, {"action": 3, "nlp_texts": []},
                    {"input_text": "x", "retry_info": {"retry_task_id": "x", "last_finished_round_id": None}}]
        with patch.object(podcast.transport, "urlopen") as transport:
            for request in requests:
                self.assertFalse(podcast.generate(request, self.directory.name)["ok"])
        transport.assert_not_called()

    def test_cancellation_and_timeout_persist_real_id_and_complete_round_receipt(self):
        raw = (event(150, session_id="remote-real-id") + round_events(8)
               + event(360, {"round_id": 9}) + event(361, data=base64.b64encode(b"unfinished").decode()))
        for exception in (podcast.transport.OperationCancelled(), TimeoutError("deadline")):
            with self.subTest(exception=type(exception).__name__):
                directory = Path(self.directory.name) / type(exception).__name__
                owner = self
                class InterruptedResponse(Response):
                    def __iter__(self):
                        for line in io.BytesIO(raw):
                            yield line
                        # Progress was already durable at 150 and 362, before disconnect.
                        receipt = json.loads(next(directory.glob("*.progress.json")).read_text())
                        owner.assertEqual(receipt["task_id"], "remote-real-id")
                        owner.assertEqual(receipt["last_finished_round_id"], 8)
                        owner.assertEqual(Path(receipt["files"][0]).read_bytes(), b"complete")
                        raise exception
                response = InterruptedResponse(b"")
                with patch.object(podcast.transport, "urlopen", return_value=response) as transport:
                    if isinstance(exception, podcast.transport.OperationCancelled):
                        with self.assertRaises(podcast.transport.OperationCancelled):
                            podcast.generate({"input_text": "文章"}, directory)
                    else:
                        self.assertFalse(podcast.generate({"input_text": "文章"}, directory)["ok"])
                self.assertTrue(response.closed)
                transport.assert_called_once()
                receipt = json.loads(next(directory.glob("*.progress.json")).read_text())
                self.assertFalse(receipt["ok"])
                self.assertEqual(receipt["state"], "incomplete")
                self.assertEqual(receipt["retry_info"], {"retry_task_id": "remote-real-id", "last_finished_round_id": 8})
                self.assertEqual(Path(receipt["files"][0]).read_bytes(), b"complete")
                self.assertEqual(Path(receipt["diagnostic_file"]).read_bytes(), b"unfinished")
                self.assertEqual(receipt["request"], {"input_text": "文章", "audio_config": {"format": "mp3", "sample_rate": 24000}})
                self.assertNotIn("test", next(directory.glob("*.progress.json")).read_text())

    def test_mcp_budget_allows_keepalive_and_success_after_300_seconds(self):
        clock = [0.0]
        class SlowHTTPResponse:
            status_code = 200
            headers = {"Content-Type": "text/event-stream"}
            def iter_bytes(self):
                yield event(150, session_id="slow-real")
                clock[0] = 301.0
                yield b":keep-alive\n\n"
                clock[0] = 302.0
                yield round_events() + event(152, code=20000000)
            def close(self):
                pass
        def open_response(request, timeout):
            self.assertGreater(timeout, 300)
            return podcast.transport.Response(SimpleNamespace(max_response_bytes=16 * 1024 * 1024),
                                               SlowHTTPResponse(), timeout, False)
        operation = podcast.transport.Operation(900.0)
        token = podcast.transport.operation.set(operation)
        try:
            with patch.object(podcast.transport.time, "monotonic", side_effect=lambda: clock[0]), \
                    patch.object(podcast.transport, "urlopen", side_effect=open_response):
                result = podcast.generate({"input_text": "文章"}, self.directory.name)
        finally:
            podcast.transport.operation.reset(token)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["task_id"], "slow-real")

    def test_failed_audio_checkpoint_never_advances_durable_resume_boundary(self):
        raw = event(150, session_id="real") + round_events(0, b"ROUND0") + round_events(1, b"ROUND1")
        writer = podcast.speech._atomic_bytes
        def fail_second_round(path, data):
            if ".through-1.partial." in str(path):
                raise OSError("disk full")
            return writer(path, data)
        with patch.object(podcast.speech, "_atomic_bytes", side_effect=fail_second_round):
            result, _ = self.generate(raw)
        receipt = json.loads(Path(result["progress_file"]).read_text())
        self.assertFalse(result["ok"])
        self.assertEqual(receipt["last_finished_round_id"], 0)
        self.assertEqual(receipt["received_last_finished_round_id"], 1)
        self.assertEqual(receipt["retry_info"], {"retry_task_id": "real", "last_finished_round_id": 0})
        self.assertEqual([row["round_id"] for row in receipt["rounds"]], [0])
        self.assertEqual(Path(receipt["files"][0]).read_bytes(), b"ROUND0")

    def test_default_sse_and_opt_in_legacy_dispatch(self):
        async def run():
            with patch.object(server.podcast, "generate", return_value={"ok": True}) as sse, \
                    patch.object(server.ws_products, "podcast", new_callable=AsyncMock, return_value={"ok": True}) as legacy:
                self.assertTrue((await server.generate_podcast(text="文章"))["ok"])
                sse.assert_called_once()
                legacy.assert_not_called()
                self.assertTrue((await server.generate_podcast(text="文章", transport="websocket"))["ok"])
                legacy.assert_awaited_once()
                self.assertFalse((await server.generate_podcast(text="文章", transport="wrong"))["ok"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
