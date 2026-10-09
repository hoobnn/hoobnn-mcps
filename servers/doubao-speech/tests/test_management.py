import datetime
import hashlib
import json
import unittest
from unittest.mock import patch

from doubao_speech_mcp import management as m


class ManagementTests(unittest.TestCase):
    def test_mt_uses_speech_model_not_legacy_translate(self):
        response = {"code": 20000000, "data": {"translation_list": [{"translation": "hello"}]}}
        with patch.object(m.speech, "post", return_value=({}, json.dumps(response), None)) as post:
            result = m.translate_text(["你好"], "en", corpus={"glossary_list": {"你好": "hello"}})
        self.assertTrue(result["ok"])
        self.assertEqual(post.call_args.args[0], "/api/v3/machine_translation/matx_translate")
        self.assertEqual(post.call_args.args[2], "volc.speech.mt")
        self.assertNotIn("source_language", post.call_args.args[1])
        self.assertEqual(result["response"], response)

    def test_mt_rejects_too_many_texts_without_request(self):
        with patch.object(m.speech, "post") as post:
            self.assertFalse(m.translate_text(["a"] * 17, "en")["ok"])
        post.assert_not_called()

    def test_minutes_preserves_request_id_and_billing_choice(self):
        request = {"Input": {"Offline": {"FileURL": "https://example.com/a.wav", "FileType": "audio"}},
                   "Params": {"AllActivate": False, "AudioTranscriptionEnable": True,
                              "SummarizationEnabled": True}}
        with patch.object(m.speech, "post", return_value=({"X-Api-Status-Code": "20000000"}, '{"Data":{"TaskID":"task"}}', None)) as post:
            result = m.minutes_submit(request, "uuid")
        self.assertEqual(result["task_id"], "task")
        self.assertEqual(result["request_id"], "uuid")
        self.assertIs(post.call_args.args[1], request)
        self.assertFalse(post.call_args.args[1]["Params"]["AllActivate"])

    def test_minutes_query_pending_and_task_failure(self):
        with patch.object(m.speech, "post", return_value=({"X-Api-Status-Code": "20000001"}, '{"Data":{"Status":"running"}}', None)):
            self.assertTrue(m.minutes_query("task")["ok"])
        with patch.object(m.speech, "post", return_value=({}, '{"Data":{"Status":"failed","ErrCode":4809,"ErrMessage":"invalid URL"}}', None)):
            result = m.minutes_query("task")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "invalid URL")

    def test_minutes_allactivate_requires_explicit_billing_and_extra_feature(self):
        request = {"Input": {"Offline": {"FileURL": "https://example.com/a.wav", "FileType": "audio"}},
                   "Params": {"AudioTranscriptionEnable": True, "ChapterEnabled": True}}
        with patch.object(m.speech, "post") as post:
            self.assertIn("AllActivate", m.minutes_submit(request)["error"])
            request["Params"] = {"AudioTranscriptionEnable": True, "AllActivate": True}
            self.assertIn("附加功能", m.minutes_submit(request)["error"])
            post.assert_not_called()

    def test_top_error_on_http_success_is_not_success(self):
        result = m._response({}, '{"ResponseMetadata":{"Error":{"Code":"Denied"}},"Result":false}', None)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["Code"], "Denied")

    def test_signs_exact_bytes_and_utc_scope(self):
        payload = '{"Name":"豆包"}'.encode()
        headers = m.signed_headers(payload, "Action=CreateAPIKey&Version=2025-05-20", "AK", "SK",
                                   now=datetime.datetime(2026, 10, 9, 0, 1, 2, tzinfo=datetime.timezone.utc))
        self.assertEqual(headers["X-Date"], "20261009T000102Z")
        self.assertEqual(headers["X-Content-Sha256"], hashlib.sha256(payload).hexdigest())
        self.assertIn("Credential=AK/20261009/cn-beijing/speech_saas_prod/request", headers["Authorization"])
        changed = m.signed_headers(payload + b" ", "Action=CreateAPIKey&Version=2025-05-20", "AK", "SK",
                                   now=datetime.datetime(2026, 10, 9, 0, 1, 2, tzinfo=datetime.timezone.utc))
        self.assertNotEqual(changed["Authorization"], headers["Authorization"])

    def test_word_table_api_key_proxy_and_replacement_signed_route(self):
        with patch.object(m.speech, "post", return_value=({}, '{"Result":{}}', None)) as post:
            self.assertTrue(m.word_table("ListBoostingTable", {"PageNumber": 1})["ok"])
        self.assertEqual(post.call_args.args[0], "/api/proxy/invoke?Action=ListBoostingTable")
        self.assertEqual(post.call_args.args[1]["Version"], "2022-08-30")
        with patch.object(m, "_signed_post", return_value={"ok": True}) as post:
            m.word_table("ListCorrectTable", {"AppID": 123, "type": "regex_correct"})
        self.assertEqual(post.call_args.args[1], "2023-10-30")
        self.assertEqual(post.call_args.args[-1], "cn-north-1")

    def test_multipart_utf8_and_field_names(self):
        payload, content_type = m._multipart({"Action": "CreateBoostingTable", "BoostingTableName": "专有词"}, "豆包\n火山引擎")
        boundary = content_type.split("boundary=")[1]
        self.assertIn(b'name="File"; filename="words.txt"', payload)
        self.assertIn("豆包\n火山引擎".encode(), payload)
        self.assertTrue(payload.endswith(f"--{boundary}--\r\n".encode()))

    def test_console_has_no_api_key_fallback(self):
        with patch.dict(m.os.environ, {}, clear=True), patch.object(m.transport, "urlopen") as network:
            result = m.console_action("ListAPIKeys", {"ProjectName": "default"})
        self.assertFalse(result["ok"])
        network.assert_not_called()

    def test_legacy_quota_uses_signed_get_query(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.headers = {}
        response.read.return_value = b'{"status":"success","data":{"quota_monitoring":null}}'
        connection = MagicMock()
        connection.__enter__.return_value = response
        with patch.dict(m.os.environ, {"VOLC_ACCESS_KEY_ID": "AK", "VOLC_SECRET_ACCESS_KEY": "SK"}), patch.object(m.transport, "urlopen", return_value=connection) as network:
            result = m.console_action("QuotaMonitoring", {"AppID": "123", "ResourceID": "volc.service_type.10029", "Start": "2026-10-01", "End": "2026-10-01", "Mode": "5 minutely"}, "2021-08-30")
        request = network.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertIn("Mode=5%20minutely", request.full_url)
        self.assertIn("/cn-north-1/speech_saas_prod/request", request.get_header("Authorization"))
        self.assertTrue(result["ok"])


if __name__ == "__main__":
    unittest.main()
