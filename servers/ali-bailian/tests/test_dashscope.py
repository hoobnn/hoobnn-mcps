import io
import json
import os
import unittest
import urllib.error
from unittest.mock import patch

from ali_bailian_mcp import dashscope


def options():
    return {"prompt": "hello", "model": "max", "system": None, "history": None, "images": [],
            "thinking": None, "thinking_budget": None, "max_tokens": None, "temperature": None,
            "json_mode": False, "web_search": False}


def frame(data):
    return ("data: " + json.dumps(data) + "\n\n").encode()


class BrokenStream(io.BytesIO):
    def __iter__(self):
        while line := self.readline():
            yield line
        raise urllib.error.URLError("connection reset")


class StreamFaults(unittest.TestCase):
    def call(self, stream):
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test"}), patch.object(dashscope.transport, "urlopen", return_value=stream):
            return dashscope.chat(options())

    def test_complete_stream_keeps_reasoning_usage(self):
        stream = frame({"choices": [{"delta": {"reasoning_content": "think", "content": "answer"}}]})
        usage = {"total_tokens": 5, "x_tools": {"search": {"count": 2, "strategy": "agent"}}}
        stream += frame({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": usage})
        result = self.call(io.BytesIO(stream + b"data: [DONE]\n\n"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["content"], "answer")
        self.assertEqual(result["reasoning"], "think")
        self.assertEqual(result["usage"], usage)

    def test_eof_without_done_is_partial(self):
        result = self.call(io.BytesIO(frame({"choices": [{"delta": {"content": "part"}}]})))
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["content"], "part")

    def test_network_drop_keeps_received_text(self):
        result = self.call(BrokenStream(frame({"choices": [{"delta": {"content": "part"}}]})))
        self.assertFalse(result["ok"])
        self.assertEqual(result["content"], "part")

    def test_malformed_chunk_keeps_prior_text(self):
        stream = frame({"choices": [{"delta": {"content": "part"}}]}) + b"data: not-json\n\n"
        result = self.call(io.BytesIO(stream))
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])

    def test_heartbeats_multiline_and_empty_answer(self):
        stream = b': heartbeat\n\ndata: {"choices":\ndata: [{"delta":{"content":"answer"}}]}\n\ndata: [DONE]\n\n'
        self.assertTrue(self.call(io.BytesIO(stream))["ok"])
        self.assertFalse(self.call(io.BytesIO(b"data: [DONE]\n\n"))["ok"])

    def test_provider_error_after_text_is_not_success(self):
        stream = frame({"choices": [{"delta": {"content": "part"}}]}) + frame({"error": {"code": "bad"}})
        result = self.call(io.BytesIO(stream))
        self.assertFalse(result["ok"])
        self.assertEqual(result["content"], "part")

    def test_json_array_error_body_never_crashes(self):
        error = urllib.error.HTTPError("https://example.test", 500, "bad", {}, io.BytesIO(b"[]"))
        self.assertIn("HTTP 500", dashscope.http_error(error))


class ModelSpecificParameters(unittest.TestCase):
    def test_minimax_convenience_thinking_uses_provider_object(self):
        for model, enabled, expected in [("MiniMax/MiniMax-M3", True, "adaptive"),
                                         ("MiniMax/MiniMax-M3", False, "disabled"),
                                         ("MiniMax/MiniMax-M3.1-Flash", True, "adaptive")]:
            body = dashscope.build_chat_body({**options(), "thinking": enabled}, model)
            self.assertEqual(body["thinking"], {"type": expected})
            self.assertNotIn("enable_thinking", body)
        body = dashscope.build_chat_body({**options(), "thinking": False}, "qwen3.8-max")
        self.assertIs(body["enable_thinking"], False)

    def test_minimax_invalid_controls_never_send_a_request(self):
        cases = [{"thinking": False}, {"parameters": {"thinking": {"type": "disabled"}}},
                 {"parameters": {"thinking": True}}, {"parameters": {"reasoning_split": False}},
                 {"parameters": {"enable_thinking": True}}, {"parameters": {"n": 2}},
                 {"parameters": {"reasoning_effort": "none"}}, {"json_mode": True}, {"web_search": True},
                 {"thinking_budget": 1024}, {"thinking": True, "parameters": {"thinking": {"type": "disabled"}}}]
        with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test"}), patch.object(dashscope.transport, "urlopen") as request:
            for updates in cases:
                result = dashscope.chat({**options(), "model": "MiniMax/MiniMax-M3.1-Flash", **updates})
                self.assertFalse(result["ok"], updates)
            request.assert_not_called()
            self.assertFalse(dashscope.chat({**options(), "model": "MiniMax/MiniMax-M3",
                                             "parameters": {"reasoning_effort": "high"}})["ok"])
            request.assert_not_called()

    def test_new_optional_fields_survive_deep_merge(self):
        body = dashscope.build_chat_body({**options(), "parameters": {
            "thinking": {"type": "adaptive"}, "reasoning_effort": "high", "reasoning_split": True,
            "max_completion_tokens": 4096, "include_tool_usage": True}}, "MiniMax/MiniMax-M3.1-Flash")
        self.assertEqual(body["thinking"], {"type": "adaptive"})
        self.assertIs(body["reasoning_split"], True)
        self.assertEqual(body["reasoning_effort"], "high")
        self.assertEqual(body["max_completion_tokens"], 4096)
        self.assertIs(body["include_tool_usage"], True)


if __name__ == "__main__":
    unittest.main()
