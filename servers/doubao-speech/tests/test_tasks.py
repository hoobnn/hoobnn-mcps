"""Typed speech tools map to official bodies; async tasks persist, poll and deliver once."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from doubao_speech_mcp import jobs, server, speech, tasks, ws_products


def reply(code="20000000", body=None):
    return {"X-Api-Status-Code": code}, json.dumps(body or {}), None


class AsyncTasks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        store = jobs.Store("HOOBNN_TEST_JOB_PATH", self.root / "jobs")
        for target in (patch.object(tasks, "STORE", store),
                       patch.object(jobs, "download", side_effect=lambda url, path: jobs.atomic_bytes(path, url.encode()))):
            target.start()
            self.addCleanup(target.stop)
        self.post = patch.object(speech, "post").start()
        self.addCleanup(patch.stopall)

    def test_long_text_submits_once_then_get_job_downloads(self):
        self.post.side_effect = [
            reply(body={"code": 20000000, "data": {"task_id": "remote"}}),
            reply(body={"code": 20000000, "data": {"task_status": 1}}),
            reply(body={"code": 20000000, "data": {"task_status": 2, "audio_url": "https://example.test/a.mp3",
                                                   "sentences": [{"text": "你好"}]}}),
        ]
        submitted = server.text_to_speech("你好" * 10, long_text=True, subtitles=True, out_dir=str(self.root / "out"),
                                          parameters={"req_params": {"additions": {"aigc_watermark": True}}})
        body = self.post.call_args_list[0].args[1]
        self.assertEqual(json.loads(body["req_params"]["additions"])["aigc_watermark"], True)
        self.assertTrue(body["req_params"]["audio_params"]["enable_timestamp"])
        self.assertEqual(submitted["job_state"], "running")
        running = tasks.get_job(submitted["job_id"])
        self.assertEqual(running["job_state"], "running")
        done = tasks.get_job(task_id="remote")
        self.assertEqual(done["job_state"], "delivered", done)
        self.assertEqual(sorted(Path(f).name for f in done["files"]), ["sentences.json", "speech.mp3"])
        self.assertEqual(tasks.get_job(submitted["job_id"])["job_state"], "delivered")
        self.assertEqual(self.post.call_count, 3)  # Finished jobs are not queried again.

    def test_transport_failure_is_unknown_and_never_resubmitted(self):
        self.post.return_value = (None, None, "请求失败：timed out")
        result = server.speech_to_text("https://example.test/meeting.wav", speakers=True, out_dir=str(self.root))
        self.assertEqual(result["job_state"], "unknown")
        self.assertTrue(result["task_id"])
        self.assertFalse(tasks.get_job(result["job_id"])["ok"])
        submits = [c for c in self.post.call_args_list if c.args[0].endswith("/submit")]
        self.assertEqual(len(submits), 1)  # Queries only; the paid submission is never repeated.

    def test_standard_recognition_with_speakers(self):
        self.post.side_effect = [reply(), reply(body={"audio_info": {"duration": 1000},
                                                      "result": {"text": "大家好", "utterances": []}})]
        self.assertFalse(server.speech_to_text("/local/a.wav", mode="standard")["ok"])
        submitted = server.speech_to_text("https://example.test/m.wav", speakers=True, out_dir=str(self.root),
                                          parameters={"request": {"ssd_version": "300"}})
        request = self.post.call_args_list[0].args[1]["request"]
        self.assertEqual((request["enable_speaker_info"], request["show_utterances"], request["ssd_version"]),
                         (True, True, "300"))
        done = tasks.get_job(submitted["job_id"])
        self.assertEqual(done["text"], "大家好")
        self.assertIn("transcript.txt", [Path(f).name for f in done["files"]])

    def test_minutes_flags_and_result_files(self):
        self.post.side_effect = [reply(body={"Data": {"TaskID": "minutes"}}),
                                 reply(body={"Data": {"Status": "success", "Result": {
                                     "AudioTranscriptionFile": "https://example.test/t.json",
                                     "SummarizationFile": "https://example.test/s.json"}}})]
        submitted = server.summarize_meeting("https://example.test/m.wav", todos=True, translate_to="en_us",
                                             out_dir=str(self.root))
        params = self.post.call_args_list[0].args[1]["Params"]
        self.assertEqual(params["InformationExtractionParams"], {"Types": ["todo_list"]})
        self.assertEqual(params["TranslationParams"], {"TargetLang": "en_us"})
        self.assertIs(params["AllActivate"], False)
        done = tasks.get_job(submitted["job_id"])
        self.assertEqual(sorted(Path(f).name for f in done["files"]), ["summary.json", "transcription.json"])
        self.assertFalse(server.summarize_meeting("https://example.test/m.wav", summary=False)["ok"])


class TypedBodies(unittest.TestCase):
    def test_clone_language_uses_official_integer(self):
        with patch.object(server.products, "voice_clone", return_value={"ok": True}) as clone:
            server.clone_voice("S_x", "/tmp/a.wav", language="en", demo_text="hello there")
            body = clone.call_args.args[0]
        self.assertEqual((body["language"], body["extra_params"]), (1, {"demo_text": "hello there"}))
        self.assertFalse(server.clone_voice("S_x", "/tmp/a.wav", language="klingon")["ok"])

    def test_podcast_inputs_map_to_actions(self):
        with patch.object(ws_products, "podcast", new=AsyncMock(return_value={"ok": True})) as podcast:
            asyncio.run(server.generate_podcast(topic="城市", speakers=["a", "b"]))
            body = podcast.call_args.args[0]
            self.assertEqual((body["action"], body["prompt_text"]), (4, "城市"))
            self.assertEqual(body["speaker_info"], {"speakers": ["a", "b"], "random_order": False})
            asyncio.run(server.generate_podcast(url="https://example.test/p", script_only=True))
            self.assertEqual(podcast.call_args.args[0]["input_info"], {"input_url": "https://example.test/p",
                                                                        "only_nlp_text": True})
        self.assertFalse(asyncio.run(server.generate_podcast(text="a", topic="b"))["ok"])
        self.assertFalse(asyncio.run(server.generate_podcast(topic="b", script_only=True))["ok"])


if __name__ == "__main__":
    unittest.main()
