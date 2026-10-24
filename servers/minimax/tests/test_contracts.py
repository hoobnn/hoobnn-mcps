"""Offline provider and recovery evidence, no paid API calls."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from minimax_mcp import client, media, server, video
from minimax_mcp.jobs import Store


class Contracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store("TEST_MINIMAX_JOBS", str(self.root / "jobs"))
        for target, attribute, value in ((video, "STORE", self.store), (media, "STORE", self.store),
                                         (server, "OUT_ROOT", self.root / "out"), (server, "MODE", "url")):
            p = patch.object(target, attribute, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.dict(os.environ, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": "https://api.minimax.cn"})
        p.start()
        self.addCleanup(p.stop)

    def test_h3_and_max_model_specific_contracts(self):
        body = video.build_request("generation", prompt="猫看窗外")
        self.assertEqual(body, {"model": "MiniMax-H3", "content": [{"type": "text", "text": "猫看窗外"}],
                                "resolution": "2K", "duration": 5, "ratio": "16:9"})
        body = video.build_request("generation", prompt="cat", model="MiniMax-H3-Max")
        self.assertEqual(body["resolution"], "768P")
        for kwargs in ({"model": "MiniMax-H3-Max", "resolution": "2K"},
                       {"model": "MiniMax-H3-Max", "duration": 4}, {"duration": 3}, {"duration": True},
                       {"duration": 16}, {"ratio": "adaptive"}, {"model": "MiniMax-Hailuo-02"},
                       {"parameters": {"content": []}}, {"parameters": {"extra": {}}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                video.build_request("generation", prompt="cat", **kwargs)

    def test_highspeed_and_lite_model_specific_contracts(self):
        image = "https://example.test/input.png"
        body = video.build_request("generation", prompt="cat", model="MiniMax-H3-Highspeed", duration=4)
        self.assertEqual((body["resolution"], body["duration"]), ("768P", 4))
        body = video.build_request("generation", prompt="cat", model="MiniMax-H3-Lite", resolution="480P")
        self.assertEqual(body["resolution"], "480P")
        body = video.build_request("generation", prompt="cat", model="MiniMax-H3-Lite", reference_images=[image], ratio="9:16")
        self.assertEqual(body["ratio"], "9:16")
        self.assertEqual(video.build_request("generation", prompt="cat", model="MiniMax-H3-Lite",
                                             first_frame=image)["ratio"], "adaptive")
        for kwargs in ({"model": "MiniMax-H3-Highspeed", "resolution": "480P"},
                       {"model": "MiniMax-H3-Highspeed", "resolution": "2K"},
                       {"model": "MiniMax-H3-Lite", "resolution": "2K"},
                       {"model": "MiniMax-H3-Lite", "reference_images": [image]},
                       {"model": "MiniMax-H3-Lite", "reference_images": [image], "ratio": "adaptive"},
                       {"model": "MiniMax-H3-Lite", "parameters": {"extra": {"prompt_expansion_mode": "quality"}}}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                video.build_request("generation", prompt="cat", **kwargs)
        with self.assertRaises(ValueError):
            video.build_request("regeneration", model="MiniMax-H3-Highspeed", source_task_id="1")

    def test_modes_and_content_not_mutated(self):
        image = "https://example.test/input.png"
        for frames in ({"first_frame": image}, {"last_frame": image}, {"first_frame": image, "last_frame": image}):
            self.assertEqual(video.build_request("generation", prompt="cat", **frames)["ratio"], "adaptive")
        with self.assertRaises(ValueError):
            video.build_request("generation", prompt="cat", first_frame=image, reference_audios=["https://example.test/a.wav"])
        with self.assertRaises(ValueError):
            video.build_request("generation", prompt="cat", reference_images=[image] * 10)
        for content in ([{"type": "text", "text": ""}], [{"type": "video_url", "video_url": {"url": image}}],
                        [{"type": "text", "text": "cat"}, {"type": "image_url", "image_url": {"url": image}, "role": "reference_audio"}]):
            with self.assertRaises(ValueError):
                video.build_request("generation", content=content)
        content = [{"type": "text", "text": "cat"}, {"type": "image_url", "image_url": {"url": image}}]
        before = json.dumps(content)
        video.build_request("generation", content=content)
        self.assertEqual(json.dumps(content), before)

    def test_ir_and_regeneration_have_distinct_schemas(self):
        body = video.build_request("h3_context_ir", prompt="cat")
        self.assertNotIn("resolution", body)
        body = video.build_request("regeneration", source_task_id="123")
        self.assertEqual(body, {"model": "MiniMax-H3", "source_task_id": "123", "resolution": "2K"})
        content = [{"type": "text", "text": "final prompt"},
                   {"type": "video_url", "video_url": {"url": "mm_file://123"}, "role": "base_video"}]
        body = video.build_request("regeneration", content=content)
        self.assertNotIn("duration", body)
        self.assertNotIn("ratio", body)
        for kwargs in ({}, {"content": content, "source_task_id": "123"}, {"content": content + [content[1]]}):
            with self.assertRaises(ValueError):
                video.build_request("regeneration", **kwargs)

    def test_invalid_input_never_calls_provider(self):
        with patch.object(client, "request") as request:
            for kwargs in ({"prompt": ""}, {"prompt": "cat", "first_frame": "/not/existing.png"},
                           {"prompt": "cat", "duration": 19}, {"prompt": "cat", "wait": 91}):
                self.assertFalse(server.generate_video(**kwargs)["ok"])
            request.assert_not_called()
        self.assertEqual(self.store.list()["jobs"], [])

    def test_durable_before_submit_and_query_uses_v2_url(self):
        def submit(path, body):
            records = self.store.list()["jobs"]
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["state"], "unknown")
            self.assertEqual(path, "/v2/video_generation")
            return {"task_id": "123"}
        with patch.object(client, "request", side_effect=submit):
            answer = server.generate_video(prompt="cat")
        self.assertTrue(answer["ok"])
        self.assertFalse(answer["completed"])
        with patch.object(client, "request", return_value={"task": {"id": "123", "status": "succeeded",
                  "task_type": "generation", "content": {"url": "https://example.test/output.mp4"}, "usage": {"output_seconds": 5}}}) as request:
            answer = server.get_job(job_id=answer["job_id"])
        self.assertTrue(answer["completed"])
        self.assertEqual(answer["files"], ["https://example.test/output.mp4"])
        request.assert_called_once_with("/v2/query/video_generation/123")

    def test_timeout_keeps_unknown_and_never_replays(self):
        with patch.object(client, "request", side_effect=TimeoutError("network timeout")) as request:
            answer = server.generate_video(prompt="cat")
            self.assertEqual(answer["job_state"], "unknown")
            self.assertFalse(server.recover_job(answer["job_id"])["ok"])
            self.assertEqual(request.call_count, 1)
        self.assertIn("body", self.store.load(answer["job_id"])["resume"])

    def test_local_upload_receipts_and_input_replacement(self):
        path = self.root / "cat.png"
        path.write_bytes(b"fake-image")
        with patch.object(client, "upload", return_value={"file_id": "555", "uri": "mm_file://555"}) as upload, \
             patch.object(client, "request", return_value={"task_id": "123"}) as request:
            answer = server.generate_video(prompt="cat", first_frame=str(path))
        upload.assert_called_once_with(str(path))
        self.assertEqual(request.call_args.args[1]["content"][1]["image_url"]["url"], "mm_file://555")
        self.assertEqual(self.store.load(answer["job_id"])["uploads"][0]["file_id"], "555")

    def test_query_error_does_not_erase_task_id_and_can_recover(self):
        with patch.object(client, "request", return_value={"task_id": "123"}):
            answer = server.generate_video(prompt="cat")
        job_id = answer["job_id"]
        with patch.object(client, "request", side_effect=client.APIError("temporary", 500, definitive=False)):
            self.assertFalse(server.get_job(job_id=job_id)["ok"])
        with patch.object(client, "request", return_value={"task": {"id": "123", "status": "running"}}):
            answer = server.get_job(job_id=job_id)
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["task_id"], "123")
        self.assertFalse(answer["completed"])

    def test_failed_cancelled_missing_url_and_mismatched_identity(self):
        for task in ({"id": "123", "status": "failed", "error": {"code": "1026", "message": "blocked"}},
                     {"id": "123", "status": "cancelled"}, {"id": "123", "status": "succeeded"},
                     {"id": "different", "status": "running"}, {"id": "123", "status": "new-status"}):
            with self.subTest(task=task), patch.object(client, "request", return_value={"task_id": "123"}):
                answer = server.generate_video(prompt="cat")
            with patch.object(client, "request", return_value={"task": task}):
                self.assertFalse(server.get_job(job_id=answer["job_id"])["ok"])

    def test_ir_returns_prompt_and_persists_text(self):
        with patch.object(client, "request", return_value={"task_id": "ir123"}):
            answer = server.create_h3_context_ir_task(prompt="cat")
        with patch.object(client, "request", return_value={"task": {"id": "ir123", "status": "succeeded",
                  "task_type": "h3_context_ir", "content": {"prompt": "enhanced prompt"}}}):
            answer = server.get_job(job_id=answer["job_id"])
        self.assertEqual(answer["prompt"], "enhanced prompt")
        self.assertEqual(Path(answer["files"][0]).read_text(), "enhanced prompt")

    def test_download_failure_refreshes_original_task_without_post(self):
        with patch.object(server, "MODE", "local"), patch.object(client, "request", return_value={"task_id": "123"}):
            answer = server.generate_video(prompt="cat")
        response = {"task": {"id": "123", "status": "succeeded", "content": {"url": "https://example.test/old.mp4"}}}
        with patch.object(client, "request", return_value=response), patch("minimax_mcp.jobs.download", side_effect=OSError("expired")):
            answer = server.get_job(job_id=answer["job_id"])
        self.assertEqual(answer["job_state"], "download_failed")
        response["task"]["content"]["url"] = "https://example.test/new.mp4"
        def download(url, path):
            self.assertEqual(url, response["task"]["content"]["url"])
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_bytes(b"video")
        with patch.object(client, "request", return_value=response) as request, patch("minimax_mcp.jobs.download", side_effect=download):
            answer = server.recover_job(answer["job_id"])
        self.assertTrue(answer["ok"])
        request.assert_called_once_with("/v2/query/video_generation/123")

    def test_media_endpoints_outputs_and_partial_images(self):
        with patch.object(client, "request", return_value={"data": {"image_urls": ["https://example.test/a.jpg"]},
                                                         "metadata": {"failed_count": 1}}):
            answer = server.text_to_image(prompt="cat", n=2)
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["job_state"], "partial")
        with patch.object(client, "request", return_value={"data": {"audio": "https://example.test/a.mp3"}}) as request:
            self.assertTrue(server.text_to_audio(text="你好")["ok"])
            self.assertEqual(request.call_args.args[0], "/v1/t2a_v2")
            self.assertEqual(request.call_args.args[1]["model"], "speech-2.8-hd")
            self.assertTrue(server.music_generation(prompt="soft piano", is_instrumental=True)["ok"])
            self.assertEqual(request.call_args.args[0], "/v1/music_generation")
        with patch.object(client, "request", return_value={"voice_id": "designed", "trial_audio": b"audio".hex()}):
            answer = server.voice_design("warm", "hello")
        self.assertEqual(answer["voice_id"], "designed")
        self.assertEqual(Path(answer["files"][0]).read_bytes(), b"audio")
        with patch.object(client, "request", return_value={"base_resp": {"status_code": 0}}):
            self.assertTrue(server.voice_clone(voice_id="Voice1234", file_id="789")["ok"])

    def test_transport_auth_v1_error_v2_error_and_no_retry(self):
        def response(payload):
            return io.BytesIO(json.dumps(payload).encode())
        with patch.object(client.transport, "urlopen", return_value=response({"task_id": "123"})) as send:
            client.request("/v2/video_generation", {"model": "MiniMax-H3"})
        req = send.call_args.args[0]
        self.assertEqual(req.get_header("Authorization"), "Bearer test-key")
        self.assertEqual(req.full_url, "https://api.minimax.cn/v2/video_generation")
        with patch.object(client.transport, "urlopen", return_value=response({"base_resp": {"status_code": 1008, "status_msg": "balance"}})):
            with self.assertRaises(client.APIError):
                client.request("/v1/t2a_v2", {})
        error = urllib.error.HTTPError("https://api.minimax.cn/v2/video_generation", 429, "rate limited", {},
                                       response({"error": {"message": "test-key rate limit"}, "request_id": "req123"}))
        with patch.object(client.transport, "urlopen", side_effect=error) as send:
            with self.assertRaises(client.APIError) as caught:
                client.request("/v2/video_generation", {})
        self.assertNotIn("test-key", str(caught.exception))
        self.assertEqual(caught.exception.request_id, "req123")
        send.assert_called_once()

    def test_multipart_query_filter_and_region_guard(self):
        path = self.root / "audio.wav"
        path.write_bytes(b"audio")
        with patch.object(client, "request", return_value={"file": {"file_id": 123}}) as request:
            answer = client.upload(str(path))
        self.assertEqual(answer["uri"], "mm_file://123")
        self.assertIn(b"video_generation_input", request.call_args.kwargs["raw"])
        with patch.object(client.transport, "urlopen", return_value=io.BytesIO(b'{}')) as send:
            server.list_video_tasks(task_ids=["123", "456"], status="running")
        self.assertIn("filter.task_ids=123&filter.task_ids=456", send.call_args.args[0].full_url)
        with patch.object(client, "request", return_value={"task_id": "123"}):
            answer = server.generate_video(prompt="cat")
        with patch.dict(os.environ, {"MINIMAX_API_HOST": "https://api.minimax.io"}), patch.object(client, "request") as request:
            self.assertFalse(server.get_job(job_id=answer["job_id"])["ok"])
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
