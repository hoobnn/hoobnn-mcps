"""Offline payload regression for constraints verified in official Ark docs."""
import base64
import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from volcengine_ark_mcp import ark, products
from volcengine_ark_mcp.jobs import Store


def options(**updates):
    return dict(prompt="test", model="pro", images=[], size=None, output_format=None,
                transparent=False, layers=False, group=None, web_search=False, fast=False,
                watermark=False, **updates)


def video(**updates):
    body = {"model": products.VIDEO_MODELS["seedance"], "content": [{"type": "text", "text": "test"}],
            "resolution": "720p", "ratio": "adaptive"}
    body.update(updates)
    return body


class OfficialContracts(unittest.TestCase):
    def test_responses_assistant_history_is_typed_without_mutating_input(self):
        history = [
            {"role": "user", "content": [{"type": "text", "text": "question"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "answer"}]},
            {"role": "assistant", "content": [{"type": "output_text", "text": "already converted"}]},
            {"role": "assistant", "content": "plain text history"},
        ]
        original = copy.deepcopy(history)
        for routing in ({"web_search": True}, {"previous_response_id": "resp-prior"}):
            with self.subTest(routing=routing), patch.object(
                    products, "request", return_value=({"status": "completed", "output": []}, None)) as request:
                self.assertTrue(products.chat("followup", "pro", history=history, **routing)["ok"])
                path, body = request.call_args.args
                self.assertEqual(path, "/responses")
                for index in (1, 2):
                    self.assertEqual(body["input"][index]["type"], "message")
                    self.assertEqual(body["input"][index]["content"][0]["type"], "output_text")
                self.assertEqual(body["input"][0]["content"][0]["type"], "input_text")
                self.assertNotIn("type", body["input"][0])
                self.assertEqual(body["input"][3], original[3])
                self.assertEqual(history, original)

    def test_chat_history_keeps_chat_format(self):
        history = [{"role": "assistant", "content": [{"type": "text", "text": "answer"}]}]
        with patch.object(products, "request", return_value=({"choices": [{"message": {"content": "ok"}}]}, None)) as request:
            self.assertTrue(products.chat("followup", "pro", history=history)["ok"])
        path, body = request.call_args.args
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(body["messages"][0], history[0])
        self.assertNotIn("type", body["messages"][0])

    def test_lite_before_eos_keeps_model_capabilities_and_persists_notice(self):
        before = ark.LITE_EOS - timedelta(seconds=1)
        opts = options()
        opts.update(model="lite", group=3, size="4K", web_search=True)
        response = {"data": [{"url": "https://example.test/image.jpg"}]}
        with tempfile.TemporaryDirectory() as directory:
            store = Store("TEST_ARK_LIFECYCLE_STORE", Path(directory) / "jobs")
            with patch.object(ark, "datetime") as clock, patch.object(products, "STORE", store), patch.object(
                    ark, "post", return_value=(response, None)) as post:
                clock.now.return_value = before
                result = ark.generate(opts, Path(directory) / "out", mode="url")
                self.assertTrue(result["ok"])
                body = post.call_args.args[0]
                self.assertEqual(body["model"], "doubao-seedream-5-0-260128")
                self.assertEqual(body["sequential_image_generation_options"], {"max_images": 3})
                self.assertEqual(body["tools"], [{"type": "web_search"}])
                self.assertEqual(body["size"], "4K")
                self.assertEqual(result["model_lifecycle"]["status"], "deprecated")
                self.assertEqual(result["model_lifecycle"]["eos_at"], "2026-11-24T14:00:00+08:00")
                self.assertFalse(result["model_lifecycle"]["automatic_migration"])
                saved = store.get(result["job_id"])
                self.assertEqual(saved["model_lifecycle"], result["model_lifecycle"])
                # EOS only stops new generation; recorded results remain recoverable.
                clock.now.return_value = ark.LITE_EOS
                post.side_effect = AssertionError("must not generate during recovery")
                self.assertTrue(products.recover(result["job_id"])["ok"])

    def test_lite_at_and_after_eos_rejected_without_request_or_job(self):
        for model in ("lite", *sorted(ark.LITE_MODEL_IDS)):
            for now in (ark.LITE_EOS, ark.LITE_EOS + timedelta(seconds=1)):
                with self.subTest(model=model, now=now), patch.object(ark, "datetime") as clock, patch.object(
                        ark, "post") as post, patch.object(products.STORE, "create") as create:
                    clock.now.return_value = now
                    opts = options()
                    opts["model"] = model
                    result = ark.generate(opts, "/unused", mode="url")
                    self.assertFalse(result["ok"])
                    self.assertEqual(result["error_code"], "model_retired")
                    self.assertFalse(result["retryable"])
                    self.assertEqual(result["model_lifecycle"]["status"], "retired")
                    self.assertNotIn("job_id", result)
                    post.assert_not_called()
                    create.assert_not_called()
        with patch.object(ark, "datetime") as clock:
            clock.now.return_value = datetime(2026, 11, 24, 14, 0, tzinfo=timezone(timedelta(hours=8)))
            self.assertEqual(ark.image_model_lifecycle(ark.MODELS["lite"])["status"], "retired")
        for model in (ark.MODELS["pro"], ark.MODELS["flash"], "ep-opaque-model"):
            self.assertIsNone(ark.image_model_lifecycle(model))

    def test_flash_has_pro_image_capabilities_but_not_fast(self):
        model = ark.MODELS["flash"]
        self.assertEqual(ark.family(model), "flash")
        opts = options()
        opts.update(images=["https://example.test/input.png"], layers=True)
        self.assertIsNone(ark.check(opts, "flash"))
        opts["fast"] = True
        self.assertIsNotNone(ark.check(opts, "flash"))
        opts.update(fast=False, group=2)
        self.assertIsNotNone(ark.check(opts, "flash"))

    def test_image_invalid_size_and_group_rejected_before_request(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(ark, "post") as post:
            for updates in ({"size": "4K"}, {"size": "512x512"}, {"group": 0}, {"output_format": "webp"}):
                opts = options()
                opts.update(updates)
                self.assertFalse(ark.generate(opts, directory)["ok"])
            post.assert_not_called()
        opts = options()
        opts["size"] = "2048x1024"
        self.assertIsNone(ark.check(opts, "pro"))

    def test_layer_size_is_a_resolution_bucket(self):
        opts = options()
        opts.update(layers=True, images=["https://example.test/image"], size="2048x1024")
        self.assertIsNotNone(ark.check(opts, "pro"))
        opts["size"] = "auto"
        self.assertIsNone(ark.check(opts, "pro"))

    def test_duration_model_specific_bounds(self):
        for alias, maximum in (("seedance", 30), ("seedance-2", 15), ("seedance-fast", 15), ("seedance-mini", 15)):
            for duration in (-1, 4, maximum):
                products.validate_video(video(model=products.VIDEO_MODELS[alias], duration=duration))
            for duration in (2, 3, maximum + 1):
                with self.assertRaises(ValueError):
                    products.validate_video(video(model=products.VIDEO_MODELS[alias], duration=duration))

    def test_seed_and_frames_only_supported_by_legacy_video_models(self):
        for field in ("seed", "frames"):
            with self.assertRaises(ValueError):
                products.validate_video(video(**{field: 1}))

    def test_known_model_resolution_limits(self):
        products.validate_video(video(model=products.VIDEO_MODELS["seedance-2"], resolution="4k"))
        for alias, resolution in (("seedance", "4k"), ("seedance-fast", "1080p"), ("seedance-mini", "1080p")):
            with self.assertRaises(ValueError):
                products.validate_video(video(model=products.VIDEO_MODELS[alias], resolution=resolution))

    def test_modes_counts_and_audio_only_limits(self):
        frame = {"type": "image_url", "role": "first_frame"}
        ref = {"type": "image_url", "role": "reference_image"}
        with self.assertRaises(ValueError):
            products.validate_video(video(content=[frame, ref]))
        with self.assertRaises(ValueError):
            products.validate_video(video(content=[ref] * 31))
        audio = {"type": "audio_url", "role": "reference_audio"}
        products.validate_video(video(content=[audio]))
        with self.assertRaises(ValueError):
            products.validate_video(video(model=products.VIDEO_MODELS["seedance-2"], content=[audio]))

    def test_explicit_edit_and_draft_constraints(self):
        ref = {"type": "video_url", "role": "reference_video"}
        products.validate_video(video(content=[ref], omni_reference_task_type="edit", duration=-1))
        products.validate_video(video(content=[ref], omni_reference_task_type="edit"))
        with self.assertRaises(ValueError):
            products.validate_video(video(content=[ref], omni_reference_task_type="edit", duration=5))
        with self.assertRaises(ValueError):
            products.validate_video(video(draft=True))
        products.validate_video(video(draft=True, resolution="480p"))

    def test_parameters_cannot_bypass_final_body_validation(self):
        opts = dict(prompt="test", model="seedance", first_frame="https://example.test/frame.png", last_frame=None,
                    reference_images=[], reference_videos=[], reference_audios=[], duration=None, seed=None,
                    resolution="720p", ratio="adaptive", audio=True, watermark=False,
                    parameters={"ratio": "16:9"})
        with patch.object(products, "request") as request:
            result = products.submit_video(opts, "/unused", 0, "url")
        self.assertFalse(result["ok"])
        request.assert_not_called()

    def test_legacy_endpoint_skips_model_assumptions(self):
        products.validate_video(video(model="ep-private-model", duration=3, resolution="custom"))

    def test_tail_frame_is_jpeg_and_missing_image_format_uses_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store("TEST_OFFICIAL_CONTRACT_STORE", Path(directory) / "jobs")
            job = store.create("video", "test", Path(directory) / "out", "url")
            job.update(task_id="task", state="running")
            store.save(job)
            response = {"status": "succeeded", "content": {"video_url": "https://example.test/video.mp4", "last_frame_url": "https://example.test/frame"}}
            with patch.object(products, "STORE", store), patch.object(products, "request", return_value=(response, None)):
                result = products.poll_video(job)
            self.assertIn("last-frame.jpg", [item["name"] for item in result["artifacts"]])
            for data, suffix in ((b"\xff\xd8\xffjpeg", ".jpg"), (b"\x89PNG\r\n\x1a\npng", ".png")):
                job = store.create("image", "test", Path(directory) / "out", "local")
                with patch.object(products, "STORE", store), patch("volcengine_ark_mcp.jobs.media_info", return_value={}):
                    result = ark.deliver_image({"data": [{"b64_json": base64.b64encode(data).decode()}]}, job)
                self.assertTrue(result["ok"])
                self.assertTrue(result["files"][0].endswith(suffix))
