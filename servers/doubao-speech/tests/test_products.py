"""Offline contract tests; never send requests to the paid service."""

import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from doubao_speech_mcp import products


class ProductContracts(unittest.TestCase):
    def setUp(self):
        self.transport = patch.object(products.speech, "post")
        self.post = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.post.return_value = ({"X-Tt-Logid": "log"}, '{"code":20000000,"data":{"task_id":"task"}}', None)

    def test_long_text_submit_preserves_options(self):
        request = {"user": {"uid": "u"}, "req_params": {
            "text": "示例", "speaker": "voice", "audio_params": {
                "format": "mp3", "sample_rate": 24000, "enable_timestamp": True},
            "additions": '{"aigc_watermark":true}'}, "unique_id": "task-id-abcdefghijklmn"}
        original = copy.deepcopy(request)
        result = products.tts_submit(request)
        self.assertTrue(result["ok"])
        self.assertEqual(request, original)
        self.assertEqual(self.post.call_args.args[:3], ("/api/v3/tts/submit", request, "seed-tts-2.0"))

    def test_long_text_validation_does_not_call_service(self):
        result = products.tts_submit({"req_params": {"text": "a" * 100001,
            "speaker": "s", "audio_params": {"format": "wav"}}})
        self.assertFalse(result["ok"])
        self.post.assert_not_called()

    def test_tts_query_task_id_and_resource(self):
        result = products.tts_query("id", "seed-icl-2.0", {"extra": True})
        self.assertTrue(result["ok"])
        self.assertEqual(self.post.call_args.args[:3], (
            "/api/v3/tts/query", {"extra": True, "task_id": "id"}, "seed-icl-2.0"))

    def test_voice_clone_local_sample_does_not_mutate(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "sample.wav"
            audio.write_bytes(b"RIFF sample")
            request = {"speaker_id": "S_x", "audio": {"custom": True},
                       "extra_params": {"enable_audio_denoise": True}}
            result = products.voice_clone(request, str(audio))
        self.assertTrue(result["ok"])
        sent = self.post.call_args.args[1]
        self.assertEqual(sent["audio"]["format"], "wav")
        self.assertEqual(base64.b64decode(sent["audio"]["data"]), b"RIFF sample")
        self.assertEqual(request["audio"], {"custom": True})
        self.assertEqual(self.post.call_args.args[2], None)

    def test_invalid_audio_base64_rejected(self):
        self.assertFalse(products.voice_clone({"speaker_id": "S_x", "audio": {"data": "??"}})["ok"])
        self.post.assert_not_called()

    def test_voice_query_upgrade_and_custom_id(self):
        request = {"speaker_id": "custom_speaker_id", "custom_speaker_id": "my_voice_123"}
        for function, endpoint in [(products.voice_query, "get_voice"),
                                   (products.voice_upgrade, "upgrade_voice")]:
            with self.subTest(endpoint=endpoint):
                self.assertTrue(function(request)["ok"])
                self.assertEqual(self.post.call_args.args[0], "/api/v3/tts/" + endpoint)
        self.assertFalse(products.voice_query({"speaker_id": "custom_speaker_id"})["ok"])

    def test_design_image_and_text_preserved(self):
        request = {"speaker_id": "S_x", "text": "试听文字", "prompt": {"text_prompt": "沉稳男声"}}
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "p.png"
            image.write_bytes(b"image")
            self.assertTrue(products.voice_design(request, str(image))["ok"])
        sent = self.post.call_args.args[1]
        self.assertEqual(sent["prompt"]["text_prompt"], "沉稳男声")
        self.assertEqual(base64.b64decode(sent["prompt"]["image_prompt"]["image_bytes"]), b"image")
        self.assertNotIn("image_prompt", request["prompt"])

    def test_design_missing_prompt_rejected(self):
        self.assertFalse(products.voice_design({"speaker_id": "S_x", "text": "test"})["ok"])
        self.post.assert_not_called()

    def test_asr_submit_returns_original_task_id(self):
        self.post.return_value = ({"X-Api-Status-Code": "20000000", "X-Tt-Logid": "submit-log"}, "", None)
        request = {"audio": {"url": "https://example.com/a.wav", "format": "wav"},
                   "request": {"model_name": "bigmodel", "enable_speaker_info": True}}
        result = products.asr_submit(request, "idle", task_id="my-task")
        self.assertTrue(result["ok"])
        self.assertEqual(result["task_id"], "my-task")
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(self.post.call_args.args[:3], (
            "/api/v3/auc/bigmodel/idle/submit", request, "volc.bigasr.auc_idle"))
        self.assertEqual(self.post.call_args.args[3], {"X-Api-Request-Id": "my-task", "X-Api-Sequence": "-1"})

    def test_asr_query_pending_and_finished(self):
        for code, status in [("20000001", "running"), ("20000002", "queued"), ("20000000", "succeeded")]:
            with self.subTest(code=code):
                payload = {"result": {"text": "文字", "utterances": [{"text": "文字"}]}}
                self.post.return_value = ({"X-Api-Status-Code": code}, json.dumps(payload), None)
                result = products.asr_query("my-task", logid="submit-log")
                self.assertTrue(result["ok"])
                self.assertEqual(result["status"], status)
                self.assertEqual(result["data"], payload)
                self.assertEqual(self.post.call_args.args[3], {"X-Api-Request-Id": "my-task", "X-Tt-Logid": "submit-log"})

    def test_service_failure_and_invalid_response(self):
        for headers, raw, error in [({}, "", "HTTP 403 denied"),
                                     ({"X-Api-Status-Code": "45000001"}, '{}', None),
                                     ({}, "not json", None), ({}, '[]', None)]:
            with self.subTest(raw=raw, error=error):
                self.post.return_value = (headers, raw, error)
                self.assertFalse(products.asr_query("task")["ok"])

    def test_asr_rejects_local_url_and_unknown_mode(self):
        body = {"audio": {"url": "/tmp/file.wav"}, "request": {"model_name": "bigmodel"}}
        self.assertFalse(products.asr_submit(body)["ok"])
        self.assertFalse(products.asr_query("task", mode="unknown")["ok"])
        self.post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
