"""Fault-oriented durable job tests; no provider credentials or paid requests."""
import contextvars
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ali_bailian_mcp import jobs


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = jobs.Store("TEST_MCP_JOB_STORE", self.root / "jobs")
        self.job = self.store.create("image", "test", self.root / "out")

    def add_urls(self, count=1):
        for index in range(count):
            self.store.add(self.job, f"{index}.bin", url=f"https://example.test/{index}")

    def fake_download(self, url, path):
        return jobs.atomic_bytes(path, url.encode())

    def test_parallel_delivery_bound_and_single_writer(self):
        self.add_urls(8)
        barrier = threading.Barrier(4)
        active, peak = 0, 0
        mutex = threading.Lock()
        writes = []
        save = self.store.save

        def download(url, path):
            nonlocal active, peak
            with mutex:
                active += 1
                peak = max(peak, active)
            barrier.wait(timeout=5)
            result = self.fake_download(url, path)
            with mutex:
                active -= 1
            return result

        def record_save(job):
            writes.append(threading.get_ident())
            return save(job)

        with patch.object(jobs, "download", download), patch.object(jobs, "media_info", return_value={}), patch.object(self.store, "save", record_save):
            result = self.store.deliver(self.job)
        self.assertTrue(result["ok"])
        self.assertEqual(peak, 4)
        self.assertEqual(set(writes), {threading.get_ident()})
        self.assertEqual([item["name"] for item in result["artifacts"]], [f"{index}.bin" for index in range(8)])
        self.assertEqual(self.store.load(self.job["job_id"])["state"], "delivered")

    def test_download_workers_inherit_context(self):
        marker = contextvars.ContextVar("test_deadline")
        token = marker.set("budget")
        self.addCleanup(marker.reset, token)
        self.add_urls(3)
        seen = []

        def download(url, path):
            seen.append(marker.get())
            return self.fake_download(url, path)

        with patch.object(jobs, "download", download), patch.object(jobs, "media_info", return_value={}):
            self.store.deliver(self.job)
        self.assertEqual(seen, ["budget"] * 3)

    def test_recovery_preserves_saved_file_mtime(self):
        self.add_urls()
        with patch.object(jobs, "download", self.fake_download), patch.object(jobs, "media_info", return_value={}):
            first = self.store.deliver(self.job)
        path = Path(first["files"][0])
        os.utime(path, ns=(1234567890000000000, 1234567890000000000))
        before = path.stat().st_mtime_ns
        with patch.object(jobs, "download", side_effect=AssertionError("must not download")), patch.object(jobs, "media_info", side_effect=AssertionError("must not probe")):
            recovered = self.store.recover(self.job["job_id"])
        self.assertTrue(recovered["ok"])
        self.assertEqual(path.stat().st_mtime_ns, before)

    def test_failed_artifact_only_is_retried(self):
        self.add_urls(2)
        calls = []

        def download(url, path):
            if url.endswith("/1"):
                raise OSError("network interrupted")
            return self.fake_download(url, path)

        with patch.object(jobs, "download", download), patch.object(jobs, "media_info", return_value={}):
            first = self.store.deliver(self.job)
        self.assertEqual(first["job_state"], "download_failed")
        self.assertEqual(first["artifacts"][0]["state"], "saved")

        def repaired(url, path):
            calls.append(url)
            return self.fake_download(url, path)

        with patch.object(jobs, "download", repaired), patch.object(jobs, "media_info", return_value={}):
            second = self.store.recover(self.job["job_id"])
        self.assertTrue(second["ok"])
        self.assertEqual(calls, ["https://example.test/1"])

    def test_tampered_file_is_downloaded_again(self):
        self.add_urls()
        with patch.object(jobs, "download", self.fake_download), patch.object(jobs, "media_info", return_value={}):
            self.store.deliver(self.job)
            Path(self.job["artifacts"][0]["file"]).write_bytes(b"tampered")
            with patch.object(jobs, "download", wraps=self.fake_download) as download:
                result = self.store.recover(self.job["job_id"])
        self.assertTrue(result["ok"])
        download.assert_called_once()

    def test_empty_artifacts_never_report_success(self):
        self.job["state"] = "delivered"
        self.store.save(self.job)
        result = self.store.deliver(self.job)
        self.assertFalse(result["ok"])
        self.assertEqual(result["job_state"], "failed")

    def test_empty_partial_result_preserves_failure(self):
        self.job.update(state="partial", error="all images rejected")
        self.store.save(self.job)
        result = self.store.deliver(self.job)
        self.assertFalse(result["ok"])
        self.assertEqual(result["job_state"], "partial")
        self.assertEqual(result["error"], "all images rejected")

    def test_partial_generation_remains_partial(self):
        self.add_urls()
        self.job["result"]["errors"] = ["generation failed for second input"]
        self.store.save(self.job)
        with patch.object(jobs, "download", self.fake_download), patch.object(jobs, "media_info", return_value={}):
            result = self.store.deliver(self.job)
        self.assertFalse(result["ok"])
        self.assertEqual(result["job_state"], "partial")
        with patch.object(jobs, "download", side_effect=AssertionError("must not regenerate")):
            self.assertFalse(self.store.recover(self.job["job_id"])["ok"])

    def test_unknown_never_retries_generation(self):
        result = self.store.recover(self.job["job_id"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["job_state"], "unknown")

    def test_corrupt_records_are_reported_by_get_list_recover(self):
        path = self.store.path(self.job["job_id"])
        for payload in ("invalid json", "[]", json.dumps({"job_id": self.job["job_id"]})):
            path.write_text(payload)
            self.assertFalse(self.store.get(self.job["job_id"])["ok"])
            self.assertFalse(self.store.recover(self.job["job_id"])["ok"])
            self.assertEqual(len(self.store.list()["errors"]), 1)

    def test_stale_save_cannot_overwrite_newer_record(self):
        stale = self.store.load(self.job["job_id"])
        self.job["state"] = "running"
        self.store.save(self.job)
        stale["state"] = "failed"
        with self.assertRaisesRegex(ValueError, "另一个调用更新"):
            self.store.save(stale)
        self.assertEqual(self.store.load(self.job["job_id"])["state"], "running")

    def test_full_processing_blocks_concurrent_recovery_and_save(self):
        stale = self.store.load(self.job["job_id"])
        with self.store.processing(self.job):
            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(self.store.recover, self.job["job_id"]).result(timeout=5)
                self.assertFalse(result["ok"])
                self.assertIn("另一个调用处理", result["error"])
                with self.assertRaisesRegex(ValueError, "另一个调用处理"):
                    pool.submit(self.store.save, stale).result(timeout=5)
            # Nested mutation and recovery ownership work in the same thread.
            self.store.save(self.job)
            with self.store.locked(self.job["job_id"]) as loaded:
                self.assertEqual(loaded["revision"], self.job["revision"])
        self.assertTrue(self.store.get(self.job["job_id"])["ok"])

    def test_processing_blocks_another_process(self):
        script = """import fcntl, sys
with open(sys.argv[1], 'a+b') as lock:
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    sys.exit(1)
"""
        with self.store.processing(self.job):
            result = subprocess.run([sys.executable, "-c", script,
                                     str(self.store.path(self.job["job_id"]).parent / "job.lock")],
                                    capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_damaged_artifact_schema_is_reported(self):
        self.add_urls()
        payload = self.store.load(self.job["job_id"])
        payload["artifacts"][0].update(state="saved")
        del payload["artifacts"][0]["file"]
        self.store.path(self.job["job_id"]).write_text(json.dumps(payload))
        self.assertFalse(self.store.get(self.job["job_id"])["ok"])
        self.assertFalse(self.store.recover(self.job["job_id"])["ok"])
        self.assertEqual(len(self.store.list()["errors"]), 1)

    def test_legacy_record_without_revision_is_supported(self):
        path = self.store.path(self.job["job_id"])
        legacy = json.loads(path.read_text())
        legacy.pop("revision")
        path.write_text(json.dumps(legacy))
        loaded = self.store.load(self.job["job_id"])
        self.store.save(loaded)
        self.assertEqual(loaded["revision"], 1)

    def test_spool_copy_is_streamed_and_atomic(self):
        data = b"x" * (2 * 1024 * 1024)
        self.store.add(self.job, "asset.bin", data=data)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("no full copy")), patch.object(jobs, "media_info", return_value={}):
            result = self.store.deliver(self.job)
        self.assertTrue(result["ok"])
        self.assertEqual(jobs.fingerprint(result["files"][0])["bytes"], len(data))
        self.assertFalse(list((self.root / "out").glob(".mcp-*")))

    def test_incomplete_download_keeps_existing_final_file(self):
        path = self.root / "final.bin"
        path.write_bytes(b"previous")
        response = io.BytesIO(b"partial")
        response.headers = {"Content-Length": "100"}
        with patch.object(jobs.transport, "urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "Content-Length"):
                jobs.download("https://example.test/data", path)
        self.assertEqual(path.read_bytes(), b"previous")
        self.assertFalse(list(self.root.glob(".mcp-download-*")))

    def test_reject_unsafe_artifact_names_and_job_ids(self):
        for name in ("../escape", "..", ".", "", "/absolute"):
            with self.assertRaises(ValueError):
                self.store.add(self.job, name, data=b"payload")
        for job_id in (None, "../escape", "0" * 31):
            self.assertFalse(self.store.get(job_id)["ok"])


if __name__ == "__main__":
    unittest.main()
