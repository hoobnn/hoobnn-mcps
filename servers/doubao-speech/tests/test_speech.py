"""Offline delivery, partial paid-result recovery and malformed response checks."""
import base64
import concurrent.futures
import json
import os
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from doubao_speech_mcp import speech


def tts_options(**updates):
    return {"text": "hello", "voice": "v", "resource_id": None, "format": "mp3",
            "sample_rate": 24000, "subtitles": False, "speech_rate": 0, "loudness_rate": 0,
            "instructions": None, "dialect": None, "language": None, "pitch": 0,
            "pronunciations": None, "model": None, **updates}


def audio_options(**updates):
    return {"prompt": "rain", "model": "seed-audio-1.0", "speaker": None,
            "reference_audios": [], "reference_image": None, "format": "mp3", "sample_rate": None,
            "speech_rate": 0, "loudness_rate": 0, "pitch_rate": 0, "subtitles": False, **updates}


def stream(data=b"audio", words=5):
    return json.dumps({"code": 0, "data": base64.b64encode(data).decode()}) + json.dumps(
        {"code": 20000000, "usage": {"text_words": words}})


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def test_shared_directory_concurrent_tts_preserves_unique_files(self):
        with patch.object(speech, "post", return_value=({}, stream(), None)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(lambda _: speech.text_to_speech(tts_options(), self.directory), range(8)))
        self.assertTrue(all(result["ok"] for result in results), results)
        paths = [result["files"][0] for result in results]
        self.assertEqual(len(set(paths)), 8)
        for result in results:
            self.assertEqual(Path(result["files"][0]).read_bytes(), b"audio")
            self.assertEqual(json.loads(Path(result["manifest"]).read_text())["status"], "complete")
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_second_chunk_failure_keeps_audio_usage_and_remaining_input(self):
        options = tts_options(text="a" * 1001)
        with patch.object(speech, "post", side_effect=[({}, stream(b"first", 1000), None),
                                                     (None, None, "provider error")]) as post:
            result = speech.text_to_speech(options, self.directory)
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["chunks"], 1)
        self.assertEqual(result["usage"], {"text_words": 1000})
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"first")
        manifest = json.loads(Path(result["manifest"]).read_text())
        self.assertEqual(manifest["remaining_input"], ["a"])
        self.assertEqual(manifest["completed_chunks"][0]["file"], result["files"][0])
        self.assertEqual(manifest["status"], "partial")
        self.assertEqual(post.call_count, 2)

    def test_network_partial_read_keeps_incomplete_paid_audio(self):
        raw = json.dumps({"code": 0, "data": base64.b64encode(b"partial audio").decode()}).encode()
        error = speech.transport.PartialReadError("connection reset", raw, {})
        with patch.dict(os.environ, {"VOLC_SPEECH_API_KEY": "test"}), patch.object(
                speech.transport, "urlopen", side_effect=error):
            result = speech.text_to_speech(tts_options(), self.directory)
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["chunks"], 0)
        self.assertEqual(Path(result["files"][0]).read_bytes(), b"partial audio")
        manifest = json.loads(Path(result["manifest"]).read_text())
        self.assertFalse(manifest["incomplete_chunk"]["automatic_retry_safe"])

    def test_wav_merge_and_subtitles_preserve_chunk_outputs(self):
        sentence = [{"text": "hi", "start": 0, "end": 0.01}]
        with patch.object(speech, "synth_chunk", return_value=(b"\0" * 480, sentence, 1)):
            result = speech.text_to_speech(tts_options(text="a" * 1001, format="wav", subtitles=True), self.directory)
        self.assertTrue(result["ok"], result)
        self.assertEqual(len(result["chunk_files"]), 2)
        with wave.open(result["files"][0], "rb") as audio:
            self.assertEqual(audio.getnframes(), 480)
            self.assertEqual(audio.getframerate(), 24000)
        self.assertAlmostEqual(result["subtitles"][1]["start"], 0.01)
        self.assertIn("00:00:00,010", Path(result["files"][1]).read_text())
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_invalid_inputs_never_generate(self):
        with patch.object(speech, "post") as post:
            for changes in ({"sample_rate": 0}, {"sample_rate": True}, {"sample_rate": float("nan")},
                            {"sample_rate": 12000}, {"subtitles": "yes"}):
                self.assertFalse(speech.text_to_speech(tts_options(**changes), self.directory)["ok"])
            for changes in ({"sample_rate": -1}, {"sample_rate": True}, {"subtitles": "false"}):
                self.assertFalse(speech.generate_audio(audio_options(**changes), self.directory)["ok"])
            post.assert_not_called()

    def test_malformed_tts_responses_are_errors(self):
        for raw in ('[]', 'null', '{"data":', '{"data":"!!!!"}', '', '{"sentence":[]}'):
            with self.subTest(raw=raw), patch.object(speech, "post", return_value=({}, raw, None)):
                result = speech.text_to_speech(tts_options(), self.directory)
                self.assertFalse(result["ok"], result)
                self.assertEqual(result["files"], [])
                self.assertIsNotNone(result["error"])

    def test_truncated_stream_keeps_received_audio_without_claiming_completion(self):
        for tail in ('{"code":', ''):
            raw = json.dumps({"data": "YWJj", "usage": {"text_words": 3}}) + tail
            with self.subTest(tail=tail), patch.object(speech, "post", return_value=({}, raw, None)) as post:
                result = speech.text_to_speech(tts_options(), self.directory)
            self.assertFalse(result["ok"])
            self.assertTrue(result["partial"])
            self.assertEqual(result["chunks"], 0)
            self.assertEqual(Path(result["files"][0]).read_bytes(), b"abc")
            manifest = json.loads(Path(result["manifest"]).read_text())
            self.assertEqual(manifest["incomplete_chunk"]["status"], "partial_audio")
            self.assertFalse(manifest["incomplete_chunk"]["automatic_retry_safe"])
            self.assertEqual(manifest["remaining_input"], ["hello"])
            self.assertEqual(result["usage"], {"text_words": 3})
            post.assert_called_once()

    def test_manifest_records_paid_chunk_when_audio_delivery_fails(self):
        with patch.object(speech, "post", return_value=({}, stream(), None)), patch.object(
                speech, "_write_audio", side_effect=OSError("read only")):
            result = speech.text_to_speech(tts_options(), self.directory)
        manifest = json.loads(Path(result["manifest"]).read_text())
        self.assertEqual(manifest["incomplete_chunk"]["status"], "synthesized_not_saved")
        self.assertEqual(manifest["usage"], {"text_words": 5})
        self.assertEqual(manifest["request_options"]["voice"], "v")
        self.assertFalse(manifest["incomplete_chunk"]["automatic_retry_safe"])

    def test_write_failure_is_not_success_and_cleans_temporary(self):
        real_replace = speech.os.replace
        def reject_audio(source, destination):
            if Path(destination).suffix == ".mp3":
                raise OSError("disk full")
            return real_replace(source, destination)
        with patch.object(speech, "post", return_value=({}, stream(), None)), patch.object(
                speech.os, "replace", side_effect=reject_audio):
            result = speech.text_to_speech(tts_options(), self.directory)
        self.assertFalse(result["ok"])
        self.assertTrue(result["partial"])
        self.assertEqual(result["usage"], {"text_words": 5})
        self.assertEqual(result["files"], [])
        self.assertEqual(list(self.directory.glob("*.mp3")), [])
        self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_unwritable_initial_manifest_prevents_paid_request(self):
        with patch.object(speech, "_atomic_json", side_effect=OSError("permission denied")), patch.object(speech, "post") as post:
            result = speech.text_to_speech(tts_options(), self.directory)
        self.assertFalse(result["ok"])
        post.assert_not_called()

    def test_audio_generation_unique_names_and_invalid_responses(self):
        raw = json.dumps({"audio": base64.b64encode(b"music").decode()})
        with patch.object(speech, "post", return_value=({}, raw, None)):
            first = speech.generate_audio(audio_options(), self.directory)
            second = speech.generate_audio(audio_options(), self.directory)
        self.assertTrue(first["ok"])
        self.assertNotEqual(first["files"], second["files"])
        self.assertEqual(Path(first["files"][0]).read_bytes(), b"music")
        for raw in ('[]', '{"audio":', '{"audio":"!!!!"}', '{}'):
            with patch.object(speech, "post", return_value=({}, raw, None)):
                self.assertFalse(speech.generate_audio(audio_options(), self.directory)["ok"])

    def test_generated_audio_write_failure_returns_error(self):
        raw = json.dumps({"audio": "YWJj"})
        with patch.object(speech, "post", return_value=({}, raw, None)), patch.object(speech, "_atomic_bytes", side_effect=OSError("disk full")):
            result = speech.generate_audio(audio_options(), self.directory)
        self.assertFalse(result["ok"])
        self.assertEqual(result["files"], [])

    def test_audio_generation_official_pcm_and_format_specific_rates(self):
        raw = json.dumps({"audio": "YWJj"})
        with patch.object(speech, "post", return_value=({}, raw, None)) as post:
            for fmt, rate in (("pcm", 40000), ("wav", 40000), ("mp3", 44100), ("ogg_opus", 48000)):
                result = speech.generate_audio(audio_options(format=fmt, sample_rate=rate), self.directory)
                self.assertTrue(result["ok"], result)
                self.assertEqual(post.call_args.args[1]["audio_config"]["sample_rate"], rate)
                self.assertTrue(result["files"][0].endswith(".ogg" if fmt == "ogg_opus" else "." + fmt))
        with patch.object(speech, "post") as post:
            for fmt, rate in (("ogg_opus", 24000), ("mp3", 40000), ("wav", 22050), ("pcm", 192000)):
                result = speech.generate_audio(audio_options(format=fmt, sample_rate=rate), self.directory)
                self.assertFalse(result["ok"])
            post.assert_not_called()

    def test_malformed_asr_response_returns_error(self):
        options = {"audio": "https://example.com/a.wav", "format": None, "language": None,
                   "itn": True, "punc": True, "ddc": False, "utterances": False,
                   "hotwords": [], "context": None}
        for raw in ('[]', '{"result":', '{"result":[1]}'):
            with patch.object(speech, "post", return_value=({}, raw, None)):
                self.assertFalse(speech.speech_to_text(options)["ok"])


if __name__ == "__main__":
    unittest.main()
