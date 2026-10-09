import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for name in ("ali-bailian", "volcengine-ark", "doubao-speech"):
    sys.path.insert(0, str(ROOT / "servers" / name / "src"))


class QueryContracts(unittest.TestCase):
    def test_explicit_shared_output_parent_is_isolated_per_call(self):
        for package in ("volcengine_ark_mcp", "ali_bailian_mcp", "doubao_speech_mcp"):
            server = importlib.import_module(package + ".server")
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                paths = [server.target_dir(directory) for _ in range(10)]
                if package != "doubao_speech_mcp":
                    self.assertEqual(len(set(paths)), 10)
                    self.assertTrue(all(path.parent == Path(directory) for path in paths))
                else:
                    # Speech uses unique filenames inside the caller's directory.
                    self.assertEqual(set(paths), {Path(directory)})
    def test_failed_requery_does_not_claim_success_or_lose_delivered_state(self):
        for package, poll_module in (("volcengine_ark_mcp", "products"), ("ali_bailian_mcp", "media")):
            with self.subTest(package=package), tempfile.TemporaryDirectory() as directory:
                jobs = importlib.import_module(package + ".jobs")
                products = importlib.import_module(package + ".products")
                poller = importlib.import_module(package + "." + poll_module)
                store = jobs.Store("HOOBNN_TEST_JOB_PATH", directory)
                job = store.create("video", "model", Path(directory) / "out")
                job.update(task_id="remote-id", state="delivered")
                store.save(job)
                function = poller.poll_video if package == "volcengine_ark_mcp" else poller.poll_job
                with patch.object(products, "STORE", store), patch.object(poller, "request", return_value=(None, "HTTP 503")):
                    result = function(job)
                self.assertFalse(result["ok"])
                self.assertTrue(result["query_failed"])
                self.assertEqual(store.load(job["job_id"])["state"], "delivered")

    def test_initial_generation_holds_lease_through_paid_request(self):
        from volcengine_ark_mcp import ark, products
        from volcengine_ark_mcp.jobs import Store
        options = {"prompt": "cat", "model": "pro", "images": [], "size": None, "output_format": None,
                   "transparent": False, "layers": False, "group": None, "web_search": False,
                   "fast": False, "watermark": False}
        with tempfile.TemporaryDirectory() as directory:
            store = Store("HOOBNN_TEST_JOB_PATH", directory)
            def request(*args):
                import concurrent.futures
                job_id = next(store.root.glob("*/job.json")).parent.name
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    attempt = pool.submit(store.recover, job_id).result()
                self.assertFalse(attempt["ok"])
                self.assertIn("另一个调用", attempt["error"])
                return {"data": [], "request_id": "request"}, None
            with patch.object(products, "STORE", store), patch.object(ark, "post", side_effect=request):
                self.assertFalse(ark.generate(options, Path(directory) / "out")["ok"])


if __name__ == "__main__":
    unittest.main()
