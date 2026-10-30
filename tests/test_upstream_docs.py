"""Official-body extraction and audit baseline failure contracts."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("upstream_docs", ROOT / "scripts" / "upstream_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


class DocumentContracts(unittest.TestCase):
    def test_minimax_export_requires_openapi_body_and_known_preamble(self):
        body = ("> ## Documentation Index\n> https://platform.minimaxi.com/docs/llms.txt\n\n"
                "# Video API\n\n```yaml\nopenapi: 3.1.0\npaths:\n  /v2/video_generation:\n"
                "    post:\n      description: Create an asynchronous video task.\n```\n")
        text, meta = docs.extract(body, {"fetch_kind": "minimax_markdown"})
        self.assertTrue(text.startswith("# Video API"))
        self.assertEqual(meta["title"], "Video API")
        for broken in (body.replace("openapi: 3.1.0", ""), body.replace("paths:\n", ""), "<html>" + body):
            with self.assertRaises(ValueError):
                docs.extract(broken, {"fetch_kind": "minimax_markdown"})
        docs.official_url("https://platform.minimax.cn/docs/api-reference/video-generation-v2-create.md")
        self.assertTrue(docs.is_api_endpoint("https://api.minimax.cn/v2/video_generation"))
        self.assertFalse(docs.is_api_endpoint("https://api.minimax.cn.evil.test/v2/video_generation"))

    def test_allowlist_rejects_nonofficial_and_redirect_targets(self):
        for url in ("http://docs.volcengine.com/api/doc/getDocDetail", "https://evil.com/page",
                    "https://docs.volcengine.com.evil.com/page", "https://user@help.aliyun.com/page"):
            with self.assertRaises(ValueError):
                docs.official_url(url)
        docs.official_url("https://docs.volcengine.com/api/doc/getDocDetail?LibraryCode=ark")

    def test_html_200_shell_and_tiny_text_are_not_success(self):
        for body in ("<!doctype html><html>enable JavaScript</html>", "<html>" + "shell" * 100, "Not found"):
            with self.assertRaises(ValueError):
                docs.extract(body, {"id": "article"})

    def test_volcengine_uses_mdcontent_without_editor_noise(self):
        text = "# API\n" + "endpoint and model contract\n" * 20
        payload = {"Result": {"MDContent": text, "Content": "editor random block IDs",
                              "DocumentID": 1, "UpdatedTime": "2026-10-10", "Title": "API"}}
        content, meta = docs.extract(json.dumps(payload), {"id": "api"})
        self.assertEqual(content, text)
        self.assertEqual(meta["document_id"], "1")
        payload["Result"]["MDContent"] = ""
        with self.assertRaises(ValueError):
            docs.extract(json.dumps(payload), {"id": "api"})

    def test_index_order_does_not_invent_a_change(self):
        entries = [{"DocumentCode": "b", "Title": "B"}, {"DocumentCode": "a", "Title": "A"}]
        first = docs.extract(json.dumps({"Result": entries}), {"id": "index"})
        entries.reverse()
        entries[0]["volatile"] = "different"
        self.assertEqual(first, docs.extract(json.dumps({"Result": entries}), {"id": "index"}))

    def test_aliyun_extracts_article_excluding_navigation(self):
        state = {"docDetailData": {"storeData": {"data": {"content": "<h1>API</h1><p>qwen-test</p>" * 20,
                                                          "docTitle": "API", "lastModifiedTime": 123}}}}
        body = "<nav>random navigation</nav><script>window.__ICE_PAGE_PROPS__ = " + json.dumps(state) + ";</script>"
        text, meta = docs.extract(body, {"id": "api", "fetch_kind": "aliyun_html"})
        self.assertIn("qwen-test", text)
        self.assertNotIn("random navigation", text)
        self.assertEqual(meta["updated_at"], 123)

    def test_empty_aliyun_and_disguised_error_pages_fail(self):
        for content in ("", "<p>Not found</p>"):
            state = {"docDetailData": {"storeData": {"data": {"content": content, "docTitle": "API"}}}}
            with self.assertRaises(ValueError):
                docs.extract("window.__ICE_PAGE_PROPS__ = " + json.dumps(state), {"id": "api", "fetch_kind": "aliyun_html"})
        for content in ("<div>Access denied</div>" * 20, "# Error\n" + "Unavailable documentation\n" * 20):
            with self.assertRaises(ValueError):
                docs.extract(content, {"id": "api"})

    def test_document_identity_and_kind_must_match(self):
        source = {"id": "api", "fetch_url": "https://docs.volcengine.com/api/doc/getDocDetail?DocumentCode=expected"}
        with self.assertRaises(ValueError):
            docs.extract(json.dumps({"Result": [{"DocumentCode": "expected"}]}), source)
        with self.assertRaises(ValueError):
            docs.extract(json.dumps({"Result": {"DocumentCode": "other", "MDContent": "body" * 100}}), source)

    def test_numeric_identity_survives_slug_migration_and_rejects_wrong_document(self):
        source = {"id": "api", "fetch_url": "https://docs.volcengine.com/api/doc/getDocDetail?LibraryID=6561&DocumentID=1329505"}
        result = {"LibraryID": 6561, "DocumentID": 1329505, "LibraryCode": "doubao-voice",
                  "DocumentCode": "websocket-bidirectional-streaming-v3", "Title": "API",
                  "MDContent": "# API\n" + "official contract\n" * 20}
        content, metadata = docs.extract(json.dumps({"Result": result}), source)
        self.assertEqual(content, result["MDContent"])
        self.assertEqual(metadata["document_id"], "1329505")
        for field, wrong in (("LibraryID", 82379), ("DocumentID", 1329506), ("LibraryID", None), ("DocumentID", None)):
            with self.subTest(field=field, wrong=wrong), self.assertRaisesRegex(ValueError, field):
                docs.extract(json.dumps({"Result": dict(result, **{field: wrong})}), source)
        # A retired page can return an empty Result with the requested DocumentID.
        with self.assertRaises(ValueError):
            docs.extract(json.dumps({"Result": {"DocumentID": 1329505, "LibraryID": 0}}), source)

    def test_official_markdown_may_embed_html_tables(self):
        body = "# API\n<table><tr><td><p>model contract</p></td></tr></table>\n" * 20
        self.assertEqual(docs.extract(body, {"id": "api"})[0], body)

    def test_api_endpoint_excludes_oss_artifacts(self):
        self.assertFalse(docs.is_api_endpoint("https://[API_HOST]/api/example"))
        self.assertFalse(docs.is_document_link("https://[API_HOST]/docs/example"))
        self.assertFalse(docs.is_api_endpoint("https://dashscope-result-bj.oss-cn-beijing.aliyuncs.com/output.mp4"))
        self.assertFalse(docs.is_api_endpoint("https://help.aliyun.com/zh/model-studio/qwen-api"))
        self.assertTrue(docs.is_api_endpoint("https://dashscope.aliyuncs.com/api/v1/models"))
        self.assertTrue(docs.is_api_endpoint("wss://openspeech.bytedance.com/api/v3/realtime/dialogue"))

    def test_parameter_change_emits_real_body_diff(self):
        import gzip
        import hashlib
        before, after = "# API\nmax_frames=10\n", "# API\nmax_frames=20\n"
        old = {"key": "ark/api", "server": "ark", "id": "api", "url": "https://docs.volcengine.com/api",
               "sha256": hashlib.sha256(before.encode()).hexdigest(), "tools": ["generate_video"]}
        new = dict(old, sha256=hashlib.sha256(after.encode()).hexdigest())
        with tempfile.TemporaryDirectory() as directory, patch.object(docs, "fetch", return_value=(new, after)):
            root = Path(directory)
            snapshots = root / "snapshots"
            snapshots.mkdir()
            (snapshots / (old["sha256"] + ".md.gz")).write_bytes(gzip.compress(before.encode()))
            result = docs.run([old], {"sources": [old]}, root / "output", snapshot_dir=snapshots)
            self.assertEqual(result["errors"], [])
            difference = (root / "output" / "diffs" / "ark" / "api.diff").read_text()
            self.assertIn("-max_frames=10", difference)
            self.assertIn("+max_frames=20", difference)
            (snapshots / (old["sha256"] + ".md.gz")).unlink()
            result = docs.run([old], {"sources": [old]}, root / "output", snapshot_dir=snapshots)
            self.assertIn("SnapshotError", result["errors"][0]["error"])
            (snapshots / (old["sha256"] + ".md.gz")).write_bytes(gzip.compress(before.encode())[:12])
            result = docs.run([old], {"sources": [old]}, root / "output", snapshot_dir=snapshots)
            self.assertIn("SnapshotError", result["errors"][0]["error"])

    def test_model_changes_include_impacted_tools(self):
        old = {"key": "ark/api", "url": "https://docs.volcengine.com/api", "sha256": "old",
               "tools": ["chat"], "models": ["doubao-old"], "endpoints": []}
        new = dict(old, sha256="new", models=["doubao-new"])
        changes = docs.compare([new], {"sources": [old]})
        self.assertEqual(changes[0]["tools"], ["chat"])
        self.assertEqual(changes[0]["models_removed"], ["doubao-old"])
        self.assertEqual(changes[0]["models_added"], ["doubao-new"])
        # Timestamp and transport headers alone must not invent body changes.
        self.assertEqual(docs.compare([dict(old, updated_at="later")], {"sources": [old]}), [])

    def test_fetch_discovers_deepseek_kimi_and_xiaomi_models_without_url_fragments(self):
        from unittest.mock import MagicMock
        body = ("# Recent models\n\nNew IDs: `deepseek-v4.1-flash-1017`, `kimi-k3-1-pro-261024`, `xiaomi/mimo-v2.6-pro-ultraspeed`, `antdigital/Ling-3.1-flash`.\n"
                "Existing qwen3.8-max remains supported.\n"
                "See https://help.aliyun.com/zh/model-studio/deepseek-not-a-model for the guide.\n")
        response = MagicMock()
        response.__enter__.return_value = response
        response.url = "https://help.aliyun.com/zh/model-studio/newly-released-models.md"
        response.headers = {"Content-Type": "text/markdown"}
        response.read.side_effect = [body.encode(), b""]
        source = {"id": "models", "server": "ali-bailian", "key": "ali-bailian/models",
                  "url": response.url, "tools": []}
        with patch.object(docs.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            record, _ = docs.fetch(source)
        self.assertEqual(record["models"], ["antdigital/Ling-3.1-flash", "deepseek-v4.1-flash-1017", "kimi-k3-1-pro-261024", "qwen3.8-max", "xiaomi/mimo-v2.6-pro-ultraspeed"])

    def test_fetch_failure_is_not_a_removed_document(self):
        source = {"key": "ark/api", "server": "ark", "id": "api", "url": "https://docs.volcengine.com/api"}
        old = dict(source, sha256="old", tools=["chat"])
        with tempfile.TemporaryDirectory() as directory, patch.object(docs, "fetch", side_effect=TimeoutError("slow")):
            result = docs.run([source], {"sources": [old]}, Path(directory))
            self.assertEqual(result["changes"], [])
            self.assertEqual(len(result["errors"]), 1)
            self.assertTrue((Path(directory) / "report.md").exists())

    def test_empty_and_duplicate_source_inventory_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                docs.load_sources(Path(directory))
            path = Path(directory) / "ark-sources.json"
            source = {"id": "api", "url": "https://docs.volcengine.com/api"}
            path.write_text(json.dumps([source, source]))
            with self.assertRaises(ValueError):
                docs.load_sources(Path(directory))

    def test_unmapped_remote_tool_fails_coverage(self):
        with self.assertRaisesRegex(ValueError, "missing="):
            docs.check_coverage([])


if __name__ == "__main__":
    unittest.main()
