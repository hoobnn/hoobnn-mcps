import copy
import json
import os
import unittest
import urllib.parse
from unittest.mock import MagicMock, patch

from doubao_speech_mcp import legacy


def connection(payload):
    response = MagicMock()
    response.headers = {"X-Tt-Logid": "log"}
    response.read.return_value = json.dumps(payload).encode()
    context = MagicMock()
    context.__enter__.return_value = response
    return context


class LegacyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"VOLC_SPEECH_APP_ID": "appid", "VOLC_SPEECH_ACCESS_TOKEN": "test-token"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_subtitle_url_submit_preserves_options_and_auth(self):
        request = {"url": "https://example.com/audio.mp3", "extra": 2}
        params = {"caption_type": "singing", "words_per_line": 15, "max_lines": 2}
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"code": "0", "id": "task"})) as network:
            result = legacy.legacy_call("subtitle_submit", request, params)
        sent = network.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(sent.full_url).query)
        self.assertEqual(query["appid"], ["appid"])
        self.assertEqual(query["caption_type"], ["singing"])
        self.assertEqual(json.loads(sent.data), request)
        self.assertEqual(sent.get_header("Authorization"), "Bearer; test-token")
        self.assertTrue(result["ok"])
        self.assertEqual(result["task_id"], "task")
        self.assertIn("Audiovideosubtitlegeneration", result["source"])

    def test_alignment_has_distinct_endpoints_and_text(self):
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"code": 0, "id": "task"})) as network:
            result = legacy.legacy_call("alignment_submit", {"url": "https://example.com/a.wav", "audio_text": "你好"}, {"caption_type": "speech"})
        sent = network.call_args.args[0]
        self.assertIn("/api/v1/vc/ata/submit?", sent.full_url)
        self.assertIn("cluster=ata_cluster", sent.full_url)
        self.assertEqual(json.loads(sent.data)["audio_text"], "你好")
        self.assertTrue(result["ok"])

    def test_get_query_pending_never_polls(self):
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"code": 2000})) as network:
            result = legacy.legacy_call("subtitle_query", {"id": "task", "blocking": 0})
        sent = network.call_args.args[0]
        self.assertEqual(sent.get_method(), "GET")
        self.assertIsNone(sent.data)
        self.assertIn("blocking=0", sent.full_url)
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["ok"])
        network.assert_called_once()

    def test_asr_post_query_uses_flat_credentials_nested_status(self):
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"resp": {"code": 2001, "id": "task"}})) as network:
            result = legacy.legacy_call("asr_query", {"id": "task", "cluster": "configured-cluster"})
        sent = network.call_args.args[0]
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(json.loads(sent.data), {"id": "task", "cluster": "configured-cluster", "appid": "appid", "token": "test-token"})
        self.assertEqual(result["state"], "running")

    def test_asr_submit_preserves_cluster_and_does_not_mutate_request(self):
        body = {"app": {"cluster": "user-configured"}, "audio": {"url": "https://example.com/a.wav"}, "additions": {"use_ddc": "True"}}
        original = copy.deepcopy(body)
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"resp": {"code": "1000", "id": "task"}})) as network:
            result = legacy.legacy_call("asr_submit", body)
        self.assertEqual(body, original)
        self.assertEqual(json.loads(network.call_args.args[0].data)["app"]["cluster"], "user-configured")
        self.assertTrue(result["ok"])

    def test_tts_response_and_emotion_task_error_preserved(self):
        output = {"code": 3000, "data": "base64-audio"}
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection(output)):
            result = legacy.legacy_call("tts", {"app": {"cluster": "configured"}, "request": {"text": "你好"}})
        self.assertEqual(result["response"], output)
        self.assertTrue(result["ok"])
        with patch.object(legacy.urllib.request, "urlopen", return_value=connection({"task_status": 2, "message": "synthesis failed"})) as network:
            result = legacy.legacy_call("tts_emotion_submit", {"text": "你好", "voice_type": "voice", "format": "mp3"})
        self.assertIn("/api/v1/tts_async_with_emotion/submit", network.call_args.args[0].full_url)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "synthesis failed")

    def test_missing_old_credentials_never_uses_api_key(self):
        with patch.dict(os.environ, {"VOLC_SPEECH_API_KEY": "v3-key"}, clear=True), patch.object(legacy.urllib.request, "urlopen") as network:
            result = legacy.legacy_call("subtitle_query", {"id": "task"})
        self.assertFalse(result["ok"])
        self.assertIn("ACCESS_TOKEN", result["error"])
        network.assert_not_called()

    def test_allowlist_validation_no_network(self):
        with patch.object(legacy.urllib.request, "urlopen") as network:
            for operation, body, params in (("https://evil.example", {}, {}), ("asr_submit", {}, {}),
                    ("alignment_submit", {"url": "https://example.com/a.wav"}, {"caption_type": "speech"}),
                    ("subtitle_query", {}, {}), ("tts", [], {})):
                self.assertFalse(legacy.legacy_call(operation, body, params)["ok"])
            network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
