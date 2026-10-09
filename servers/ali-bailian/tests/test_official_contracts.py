import unittest
from unittest.mock import patch
from ali_bailian_mcp import dashscope, media, products


def video(**changes):
    data = dict(prompt="test", model="wan", first_frame=None, last_frame=None,
                reference_images=[], reference_videos=[], reference_audios=[], file=None, link=None,
                resolution="1080P", ratio="adaptive", duration=None, audio=True,
                prompt_extend=None, seed=None, watermark=False)
    data.update(changes)
    return data


class OfficialContracts(unittest.TestCase):
    def test_native_catalog_pagination_preserves_metadata(self):
        responses = [({"output": {"total": 2, "models": [{"model": "wan3.0-video", "capabilities": ["VG"]}]}}, None),
                     ({"output": {"total": 2, "models": [{"model": "qwen3.8-max"}]}}, None)]
        with patch.object(dashscope, "request", side_effect=responses) as request:
            result = dashscope.list_models()
        self.assertTrue(result["complete"])
        self.assertFalse(result["account_verified"])
        self.assertEqual(result["catalog"][0]["capabilities"], ["VG"])
        self.assertTrue(request.call_args_list[0].args[0].startswith("/api/v1/models?"))
        self.assertIn("page_no=2", request.call_args_list[1].args[0])

    def test_catalog_partial_and_repeated_pages_are_explicit(self):
        response = ({"output": {"total": 2, "models": [{"model": "one"}]}}, None)
        with patch.object(dashscope, "request", return_value=response):
            self.assertFalse(dashscope.list_models(max_pages=1)["complete"])
            self.assertFalse(dashscope.list_models(max_pages=2)["ok"])

    def test_invalid_video_combination_fails_before_upload(self):
        cases = [video(first_frame="first.png", reference_images=["ref.png"]),
                 video(file="brief.pdf", link="https://example.test"),
                 video(file="brief.pdf", prompt_extend=False), video(duration=31),
                 video(reference_images=["image"] * 11), video(ratio="2:1")]
        with patch.object(media, "upload") as upload:
            for opts in cases:
                self.assertFalse(media.generate_video(opts, "/tmp/unused", 0)["ok"])
            upload.assert_not_called()

    def test_link_and_audio_only_are_valid_inputs(self):
        with patch.object(products, "submit_video", return_value={"ok": True}) as submit:
            self.assertTrue(media.generate_video(video(prompt="", link="https://example.test"), "/tmp/unused", 0)["ok"])
            body = submit.call_args.args[0]
            self.assertEqual(body["input"]["media"], [{"type": "link", "url": "https://example.test"}])
            self.assertTrue(media.generate_video(video(prompt="", reference_audios=["https://example.test/a.wav"]), "/tmp/unused", 0)["ok"])

    def test_incompatible_asr_model_is_never_sent_to_chat(self):
        with patch.object(media, "request") as request:
            for model in ["fun-asr-flash-2026-06-15", "qwen3-asr-flash-filetrans", "qwen3-asr-flash-realtime"]:
                self.assertFalse(media.speech_to_text({"model": model})["ok"])
            request.assert_not_called()

    def test_oversized_voice_preview_is_rejected_before_paid_create(self):
        with patch.object(products, "api") as api:
            result = products.design_voice("speaker", "x" * 1025, "qwen3-tts-vd-2026-01-26", "test", "/tmp/unused", "local")
            self.assertFalse(result["ok"])
            api.assert_not_called()

    def test_image_limits_match_specific_model_family(self):
        base = dict(prompt="cat", images=[], group=None, thinking=None, size=None, n=1)
        for model, updates in [("qwen-image-3.0-pro", {"images": ["x"] * 4}),
                               ("z-image-turbo", {"n": 2}),
                               ("wan2.7-image-pro", {"size": "4K", "images": ["x"]}),
                               ("wan2.7-image", {"n": 5})]:
            self.assertIsNotNone(dashscope.check_image({**base, **updates}, model, dashscope.image_family(model)))


if __name__ == "__main__":
    unittest.main()
