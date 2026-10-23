import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from ali_bailian_mcp import dashscope, jobs, media, products

PREVIEW = "各位听众朋友们大家好，欢迎收听本期节目"


def video(**changes):
    data = dict(prompt="test", model="wan", first_frame=None, last_frame=None,
                reference_images=[], reference_videos=[], reference_audios=[], file=None, link=None,
                resolution="1080P", ratio="adaptive", duration=None, audio=True,
                prompt_extend=None, seed=None, watermark=False)
    data.update(changes)
    return data


def tts(**changes):
    data = dict(text="hi", voice=None, instructions=None, language=None, model=None, parameters=None)
    data.update(changes)
    return data


class OfficialContracts(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        store = patch.object(products, "STORE", jobs.Store("TEST_BAILIAN_CONTRACT_STORE", self.root / "jobs"))
        store.start()
        self.addCleanup(store.stop)

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

    def test_instruct_tts_on_qwen3_flash_is_rejected_locally(self):
        with patch.object(media, "request") as request:
            result = media.text_to_speech(tts(instructions="slow"), "/tmp/unused")
            self.assertIn("下线", result["error"])
            self.assertFalse(media.text_to_speech(tts(model="qwen3-tts-flash-realtime"), "/tmp/unused")["ok"])
            request.assert_not_called()

    def test_clone_voice_uses_voice_enrollment_create_voice(self):
        response = ({"output": {"voice_id": "qwen-audio-3.0-tts-flash-me-1"}, "usage": {"count": 1}}, None)
        with patch.object(products, "api", return_value=response) as api:
            result = products.clone_voice("https://example.test/a.wav", prefix="me", language="zh")
        path, body = api.call_args.args
        self.assertEqual(path, "/api/v1/services/audio/tts/customization")
        self.assertEqual(body, {"model": "voice-enrollment", "input": {
            "action": "create_voice", "target_model": "qwen-audio-3.0-tts-flash", "prefix": "me",
            "audio": "https://example.test/a.wav", "language_hints": ["zh"]}})
        self.assertEqual((result["voice"], result["target_model"]), ("qwen-audio-3.0-tts-flash-me-1", "qwen-audio-3.0-tts-flash"))

    def test_clone_voice_rejects_invalid_audio_and_bad_args_without_request(self):
        url = "https://example.test/a.wav"
        cases = [((str(self.root / "missing.wav"),), {}), (("oss://dashscope-instant/a.wav",), {}),
                 (("data:audio/wav;base64,not-base64",), {}), (("data:audio/wav;base64,",), {}),
                 (("data:text/plain;base64,AA==",), {}), ((None,), {}),
                 ((url,), {"url": url}), ((None,), {"url": "data:audio/wav;base64,AA=="}),
                 ((url,), {"prefix": "bad_name"}), ((url,), {"target_model": "qwen3-tts-vc-2026-01-22"}),
                 ((url,), {"target_model": "cosyvoice-v2", "language": "zh"}),
                 ((url,), {"target_model": "qwen-audio-3.1-tts-flash", "language": "xx"}),
                 ((url,), {"target_model": "cosyvoice-v3-plus", "enable_preprocess": True}),
                 ((url,), {"max_prompt_audio_length": 31.0})]
        with patch.object(products, "api") as api, patch.object(media, "upload") as upload:
            for args, kwargs in cases:
                self.assertFalse(products.clone_voice(*args, **kwargs)["ok"], (args, kwargs))
            api.assert_not_called()
            upload.assert_not_called()

    def test_clone_voice_encodes_local_audio_and_preserves_data_uri_without_upload(self):
        response = ({"output": {"voice_id": "qwen-audio-3.1-tts-plus-me-1"}}, None)
        with patch.object(products, "api", return_value=response) as api, patch.object(media, "upload") as upload:
            for suffix, mime in (("wav", "audio/wav"), ("mp3", "audio/mpeg"), ("m4a", "audio/mp4")):
                sample = self.root / ("sample." + suffix)
                sample.write_bytes(b"reference audio")
                result = products.clone_voice(str(sample), target_model="qwen-audio-3.1-tts-plus", language="fr")
                self.assertTrue(result["ok"], result)
                inp = api.call_args.args[1]["input"]
                self.assertEqual(inp["audio"], f"data:{mime};base64," + base64.b64encode(sample.read_bytes()).decode())
                self.assertEqual(inp["language_hints"], ["fr"])
                self.assertNotIn("url", inp)
            data_uri = "data:audio/wav;base64,AA=="
            self.assertTrue(products.clone_voice(data_uri)["ok"])
            self.assertEqual(api.call_args.args[1]["input"]["audio"], data_uri)
            self.assertTrue(products.clone_voice(url="https://example.test/legacy.wav")["ok"])
            self.assertEqual(api.call_args.args[1]["input"]["audio"], "https://example.test/legacy.wav")
            upload.assert_not_called()

    def test_clone_voice_bounds_decoded_audio_size_and_local_formats(self):
        sample = self.root / "sample.wav"
        sample.write_bytes(b"four")
        unsupported = self.root / "sample.ogg"
        unsupported.write_bytes(b"ogg")
        with patch.object(products, "CLONE_AUDIO_LIMIT", 3), patch.object(products, "api") as api:
            for source in (str(sample), str(unsupported), "data:audio/wav;base64,Zm91cg=="):
                self.assertFalse(products.clone_voice(source)["ok"], source)
            sample.write_bytes(b"")
            self.assertFalse(products.clone_voice(str(sample))["ok"])
            api.assert_not_called()

    def test_clone_voice_without_voice_id_never_retries(self):
        with patch.object(products, "api", return_value=({"output": {}}, None)) as api:
            result = products.clone_voice("https://example.test/a.wav")
        self.assertFalse(result["ok"])
        self.assertEqual(api.call_count, 1)

    def test_design_voice_body_preview_and_recovery(self):
        audio = base64.b64encode(b"RIFFfake").decode()
        response = {"output": {"voice_id": "qwen-audio-3.1-tts-plus-vd-me-1", "target_model": "qwen-audio-3.1-tts-plus",
                               "preview_audio": {"data": audio, "sample_rate": 24000, "response_format": "wav"}},
                    "usage": {"count": 1}, "request_id": "r1"}
        root, store = self.root, products.STORE
        with patch.object(products, "api", return_value=(response, None)) as api, \
                patch.object(jobs, "media_info", return_value={}):
            result = products.design_voice("沉稳的中年男性", PREVIEW, "qwen-audio-3.1-tts-plus",
                                           "me", Path(root) / "out", "local", language="zh")
            path, body = api.call_args.args
            self.assertEqual(path, "/api/v1/services/audio/tts/customization")
            self.assertEqual(body, {"model": "voice-enrollment", "input": {
                "action": "create_voice", "target_model": "qwen-audio-3.1-tts-plus", "voice_prompt": "沉稳的中年男性",
                "preview_text": PREVIEW, "prefix": "me", "language_hints": ["zh"]},
                "parameters": {"sample_rate": 24000, "response_format": "wav"}})
            self.assertTrue(result["ok"], result)
            self.assertEqual(store.load(result["job_id"])["result"]["voice"], "qwen-audio-3.1-tts-plus-vd-me-1")
            preview = Path(root) / "out" / "preview.wav"
            self.assertEqual(preview.read_bytes(), b"RIFFfake")
            preview.unlink()
            recovered = products.recover(result["job_id"])
            self.assertTrue(recovered["ok"], recovered)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(preview.read_bytes(), b"RIFFfake")

    def test_design_voice_validates_locally(self):
        cases = [("x" * 501, PREVIEW, "qwen-audio-3.0-tts-flash", "me"),
                 ("speaker", "too short", "qwen-audio-3.0-tts-flash", "me"),
                 ("speaker", PREVIEW, "cosyvoice-v2", "me"),
                 ("speaker", PREVIEW, "qwen3-tts-vd-2026-01-26", "me"),
                 ("speaker", PREVIEW, "qwen-audio-3.0-tts-flash", "toolongprefix")]
        with patch.object(products, "api") as api:
            for args in cases:
                self.assertFalse(products.design_voice(*args, "/tmp/unused", "local")["ok"], args)
            self.assertFalse(products.design_voice("speaker", PREVIEW, "qwen-audio-3.0-tts-flash", "me",
                                                   "/tmp/unused", "local", language="ja")["ok"])
            api.assert_not_called()

    def test_voice_listing_maps_legacy_kinds_to_voice_enrollment(self):
        response = ({"output": {"voice_list": [{"voice_id": "v", "status": "OK"}]}}, None)
        with patch.object(products, "api", return_value=response) as api:
            for kind in ["enrollment", "clone", "design", "cosyvoice"]:
                self.assertTrue(products.list_voices(kind, 0, 10, "me")["ok"])
                self.assertEqual(api.call_args.args, ("/api/v1/services/audio/tts/customization", {
                    "model": "voice-enrollment",
                    "input": {"action": "list_voice", "page_index": 0, "page_size": 10, "prefix": "me"}}))
            api.return_value = ({"output": {"status": "OK", "target_model": "cosyvoice-v3.5-plus"}}, None)
            result = products.get_voice("cosyvoice-v3.5-plus-me-1", "clone")
            self.assertEqual(api.call_args.args[1], {"model": "voice-enrollment", "input": {
                "action": "query_voice", "voice_id": "cosyvoice-v3.5-plus-me-1"}})
            self.assertEqual((result["status"], result["target_model"]), ("OK", "cosyvoice-v3.5-plus"))
            calls = api.call_count
            self.assertFalse(products.list_voices("qwen")["ok"])
            self.assertEqual(api.call_count, calls)

    def test_tts_routes_by_model_and_custom_voice_prefix(self):
        cases = [(tts(model="audio", voice="longanhuan_v3.6", instructions="用温柔的语气"), "qwen-audio-3.0-tts-flash"),
                 (tts(model="qwen-audio-3.1-tts-plus", voice="system-voice", language="zh"), "qwen-audio-3.1-tts-plus"),
                 (tts(voice="qwen-audio-3.1-tts-plus-vd-me-1", instructions="慢一点"), "qwen-audio-3.1-tts-plus"),
                 (tts(voice="cosyvoice-v3.5-plus-vd-me-1", parameters={"rate": 1.2}), "cosyvoice-v3.5-plus")]
        for opts, model in cases:
            with patch.object(media, "request", return_value=({"code": "InvalidParameter", "message": "stop"}, None)) as request:
                media.text_to_speech(opts, self.root / "out")
            path, body = request.call_args.args[:2]
            self.assertEqual(path, "/api/v1/services/audio/tts/SpeechSynthesizer")
            self.assertEqual(body["model"], model)
            self.assertEqual(set(body), {"model", "input"})
            self.assertEqual(body["input"]["voice"], opts["voice"])
        self.assertEqual(body["input"]["rate"], 1.2)
        with patch.object(media, "request", return_value=({"code": "InvalidParameter", "message": "stop"}, None)) as request:
            media.text_to_speech(tts(), self.root / "out")
        self.assertEqual(request.call_args.args[0], "/api/v1/services/aigc/multimodal-generation/generation")
        self.assertEqual(request.call_args.args[1]["input"]["voice"], "Cherry")

    def test_tts_request_bodies_follow_each_protocol(self):
        path, body = media.tts_request("qwen-audio-3.0-tts-plus", tts(voice="v", instructions="慢一点", language="en"), "hi")
        self.assertEqual((path, body), ("/api/v1/services/audio/tts/SpeechSynthesizer", {
            "model": "qwen-audio-3.0-tts-plus", "input": {"text": "hi", "voice": "v", "format": "wav", "sample_rate": 24000,
                                                          "instruction": "慢一点", "language_hints": ["en"]}}))
        path, body = media.tts_request("qwen3-tts-flash", tts(voice="Cherry", language="English", parameters={"x": 1}), "hi")
        self.assertEqual((path, body), ("/api/v1/services/aigc/multimodal-generation/generation", {
            "model": "qwen3-tts-flash", "input": {"text": "hi", "voice": "Cherry", "language_type": "English"},
            "parameters": {"x": 1}}))
        self.assertEqual(media.resolve_tts_model(None, "qwen-audio-3.1-tts-flash-me-1"), "qwen-audio-3.1-tts-flash")

    def test_speech_synthesizer_local_validation(self):
        cases = [tts(model="audio"), tts(model="cosyvoice-v2", voice="v", instructions="慢"),
                 tts(model="cosyvoice", voice="v", instructions="慢" * 51), tts(model="audio", voice="v", language="Chinese"),
                 tts(model="cosyvoice", voice="v", parameters={"instruction": "慢" * 51}),
                 tts(model="cosyvoice-v2", voice="v", parameters={"instruction": "slow"}),
                 tts(model="audio", voice="v", parameters={"format": "mp3"}),
                 tts(model="audio", voice="v", parameters={"voice": "x"})]
        with patch.object(media, "request") as request:
            for opts in cases:
                self.assertFalse(media.text_to_speech(opts, "/tmp/unused")["ok"], opts)
            request.assert_not_called()
        self.assertEqual(media.instruction_length("慢a"), 3)

    def test_qwen_audio_instruction_does_not_inherit_cosyvoice_character_limit(self):
        for model in media.QWEN_AUDIO_TTS:
            opts = tts(model=model, voice="v", instructions="慢" * 51)
            self.assertIsNone(media.check_tts(model, opts, "local"))
            self.assertEqual(media.tts_request(model, opts, "hi")[1]["input"]["instruction"], "慢" * 51)

    def test_tts_usage_keeps_provider_units_and_resumes_legacy_counters(self):
        plus_usage = {"characters": 3, "input_tokens": 2, "output_tokens": 5, "total_tokens": 7}
        flash_usage = {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3}
        for model, previous, current, expected in [
                ("qwen-audio-3.1-tts-plus", plus_usage, plus_usage,
                 {"characters": 6, "input_tokens": 4, "output_tokens": 10, "total_tokens": 14}),
                ("qwen-audio-3.1-tts-flash", 5, flash_usage,
                 {"legacy_untyped": 5, "input_tokens": 2, "output_tokens": 1, "total_tokens": 3})]:
            plan = {"options": tts(model=model, voice=model + "-me-1"), "chunks": [
                {"text": "old", "state": "generated", "url": "https://example.test/old.wav", "usage": previous},
                {"text": "new", "state": "unsubmitted", "usage": {}}]}
            job = products.STORE.create("tts", model, self.root / model, "url", resume=plan)
            response = {"output": {"audio": {"url": "https://example.test/new.wav"}}, "usage": current}
            with patch.object(media, "request", return_value=(response, None)) as request:
                result = media.resume_tts(job)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["usage"], expected)
                self.assertEqual(job["resume"]["chunks"][1]["usage"], current)
                recovered = media.resume_tts(job)
                self.assertEqual(recovered["usage"], expected)
                self.assertEqual(request.call_count, 1)

    def test_completed_legacy_tts_recovery_normalizes_usage_without_generation(self):
        import wave
        audio = self.root / "speech.wav"
        with wave.open(str(audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(24000)
            output.writeframes(b"\x00\x00" * 24)
        model = "qwen-audio-3.1-tts-flash"
        plan = {"options": tts(model=model, voice=model + "-me-1"), "chunks": [
            {"text": "old", "state": "generated", "url": "https://example.test/old.wav", "usage": 5}]}
        job = products.STORE.create("tts", model, self.root, "local", resume=plan)
        job.update(state="delivered", usage={"characters": 5}, result={
            "speech_file": str(audio), "speech_integrity": jobs.fingerprint(audio)})
        products.STORE.save(job)
        with patch.object(media, "request") as request, patch.object(jobs, "download") as download:
            result = products.recover(job["job_id"])
            self.assertTrue(result["ok"], result)
            self.assertEqual(result["usage"], {"legacy_untyped": 5})
            self.assertEqual(products.STORE.load(job["job_id"])["usage"], {"legacy_untyped": 5})
            request.assert_not_called()
            download.assert_not_called()

    def test_retired_asr_snapshots_rejected_and_current_id_sent(self):
        with patch.object(media, "request") as request:
            for model in ["qwen3-asr-flash-2025-09-08", "qwen3-asr-flash-2026-02-10", "qwen3-asr-flash-2025-09-08-us"]:
                self.assertIn("下线", media.speech_to_text({"model": model, "audio": "https://example.test/a.wav"})["error"])
            request.assert_not_called()
        reply = {"choices": [{"message": {"content": "hi", "annotations": []}}]}
        with patch.object(media, "request", return_value=(reply, None)) as request:
            result = media.speech_to_text({"model": "qwen3-asr-flash", "audio": "https://example.test/a.wav",
                                           "context": None, "language": None, "itn": False})
        self.assertTrue(result["ok"])
        self.assertEqual(request.call_args.args[1]["model"], "qwen3-asr-flash")

    def test_every_rerank_model_uses_native_nested_body(self):
        with patch.object(products, "api", return_value=({"output": {"results": [{"index": 0}]}}, None)) as api:
            result = products.rerank("q", ["a", "b"], "qwen3-rerank", top_n=1)
        path, body = api.call_args.args
        self.assertEqual(path, "/api/v1/services/rerank/text-rerank/text-rerank")
        self.assertEqual(body["input"], {"query": "q", "documents": ["a", "b"]})
        self.assertEqual(body["parameters"]["top_n"], 1)
        self.assertEqual(result["results"], [{"index": 0}])

    def test_image_limits_match_specific_model_family(self):
        base = dict(prompt="cat", images=[], group=None, thinking=None, size=None, n=1)
        for model, updates in [("qwen-image-3.0-pro", {"images": ["x"] * 4}),
                               ("z-image-turbo", {"n": 2}),
                               ("wan2.7-image-pro", {"size": "4K", "images": ["x"]}),
                               ("wan2.7-image", {"n": 5})]:
            self.assertIsNotNone(dashscope.check_image({**base, **updates}, model, dashscope.image_family(model)))


if __name__ == "__main__":
    unittest.main()
