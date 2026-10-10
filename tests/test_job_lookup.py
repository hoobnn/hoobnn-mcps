"""get_job polls pending provider tasks, adopts foreign task IDs once and never resubmits."""
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for name in ("ali-bailian", "volcengine-ark"):
    sys.path.insert(0, str(ROOT / "servers" / name / "src"))

CASES = (("volcengine_ark_mcp", "products", {"status": "succeeded", "content": {"video_url": "https://example.test/v"}}),
         ("ali_bailian_mcp", "media", {"output": {"task_status": "SUCCEEDED", "video_url": "https://example.test/v"}}))


class JobLookup(unittest.TestCase):
    def test_task_id_adopts_then_reuses_delivered_record(self):
        for package, poll_module, response in CASES:
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                jobs = importlib.import_module(package + ".jobs")
                products = importlib.import_module(package + ".products")
                poller = importlib.import_module(package + "." + poll_module)
                store = jobs.Store("HOOBNN_TEST_JOB_PATH", Path(directory) / "jobs")
                fake = lambda url, path: jobs.atomic_bytes(path, b"video")
                with patch.object(products, "STORE", store), patch.object(jobs, "download", side_effect=fake), \
                        patch.object(poller, "request", return_value=(response, None)) as request:
                    first = products.get_job(task_id="remote", out_dir=Path(directory) / "out")
                    second = products.get_job(task_id="remote", out_dir=Path(directory) / "other")
                    mismatch = products.get_job(job_id=first["job_id"], task_id="different")
                self.assertTrue(first["ok"], first)
                self.assertEqual(first["job_state"], "delivered")
                self.assertEqual(second["job_id"], first["job_id"])
                self.assertEqual(request.call_count, 1)  # Delivered records are read locally.
                self.assertEqual(len(store.list()["jobs"]), 1)
                self.assertFalse(mismatch["ok"])

    def test_pending_job_is_polled_and_requires_an_identifier(self):
        from volcengine_ark_mcp import jobs, products
        with tempfile.TemporaryDirectory() as directory:
            store = jobs.Store("HOOBNN_TEST_JOB_PATH", Path(directory) / "jobs")
            job = store.create("video", "model", Path(directory) / "out")
            job.update(task_id="remote", state="running")
            store.save(job)
            with patch.object(products, "STORE", store), \
                    patch.object(products, "request", return_value=({"status": "running"}, None)) as request:
                result = products.get_job(job_id=job["job_id"])
                self.assertFalse(products.get_job()["ok"])
                self.assertFalse(products.get_job(job_id=job["job_id"], wait=91)["ok"])
            self.assertEqual(request.call_count, 1)
            self.assertEqual(result["job_state"], "running")
            self.assertFalse(result["completed"] if "completed" in result else False)


if __name__ == "__main__":
    unittest.main()
