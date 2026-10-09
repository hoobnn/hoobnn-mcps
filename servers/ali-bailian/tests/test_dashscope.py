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
        stream += frame({"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"total_tokens": 5}})
        result = self.call(io.BytesIO(stream + b"data: [DONE]\n\n"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["partial"])
        self.assertEqual(result["content"], "answer")
        self.assertEqual(result["reasoning"], "think")
        self.assertEqual(result["usage"], {"total_tokens": 5})

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


if __name__ == "__main__":
    unittest.main()
