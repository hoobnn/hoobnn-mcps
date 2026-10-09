import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doubao_speech_mcp import products


class RawContracts(unittest.TestCase):
    def test_tts_stream_preserves_subtitles_usage_and_saves_audio(self):
        request = {"req_params": {"speaker": "S_voice", "text": "你好", "audio_params": {"format": "pcm"}, "ssml": "<speak>你好</speak>"}}
        events = [{"code": 0, "data": base64.b64encode(b"\x00\x01").decode(), "sentence": {"text": "你好"}},
                  {"code": 20000000, "usage": {"text_words": 2}}]
        raw = "".join(json.dumps(e) for e in events)
        with tempfile.TemporaryDirectory() as directory, patch.object(products.speech, "post", return_value=({}, raw, None)) as post:
            result = products.raw_http("tts", request, Path(directory))
            self.assertTrue(result["ok"])
            self.assertEqual(Path(result["files"][0]).read_bytes(), b"\x00\x01")
            self.assertEqual(result["response"][-1]["usage"]["text_words"], 2)
            self.assertNotIn("data", result["response"][0])
            self.assertEqual(post.call_args.args[2], "seed-icl-2.0")
            self.assertEqual(post.call_args.args[1], request)

    def test_asr_silence_and_body_options(self):
        with patch.object(products.speech, "post", return_value=({"X-Api-Status-Code": "20000003"}, '{}', None)):
            result = products.raw_http("asr_flash", {"audio": {"url": "https://example.com/a.wav"}}, Path("."))
            self.assertTrue(result["ok"])
            self.assertEqual(result["status"], "silent")

    def test_error_after_partial_audio_does_not_report_success(self):
        raw = json.dumps({"data": "AAE="}) + json.dumps({"code": 45000001, "message": "bad"})
        with tempfile.TemporaryDirectory() as directory, patch.object(products.speech, "post", return_value=({}, raw, None)):
            result = products.raw_http("tts", {"req_params": {"speaker": "voice", "text": "x"}}, Path(directory))
            self.assertFalse(result["ok"])
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_unknown_product_never_connects(self):
        with patch.object(products.speech, "post") as post:
            self.assertFalse(products.raw_http("https://example.com", {}, Path("."))["ok"])
            post.assert_not_called()
