"""Platform isolation and incomplete-audit gates for documentation PRs."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("upstream_docs", ROOT / "scripts/upstream_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)
sys.modules["upstream_docs"] = docs
spec = importlib.util.spec_from_file_location("upstream_pr", ROOT / "scripts/upstream_pr.py")
pr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pr)


class PlatformPRs(unittest.TestCase):
    def test_platform_baseline_override_preserves_other_platforms_and_removals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = [{"server": "minimax", "key": "minimax/old"},
                      {"server": "ali-bailian", "key": "ali-bailian/keep"}]
            (root / "baseline.json").write_text(json.dumps({"sources": legacy}))
            (root / "minimax").mkdir()
            new = [{"server": "minimax", "key": "minimax/new"}]
            (root / "minimax/baseline.json").write_text(json.dumps({"sources": new}))
            self.assertEqual(docs.load_baseline(root, "minimax")["sources"], new)
            self.assertEqual({r["key"] for r in docs.load_baseline(root)["sources"]},
                             {"minimax/new", "ali-bailian/keep"})

    def test_stage_validates_capture_and_only_writes_one_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = root / "audit"
            (audit / "minimax").mkdir(parents=True)
            body = b"# Official API\n"
            (audit / "minimax/page.md").write_bytes(body)
            record = {"server": "minimax", "id": "page", "key": "minimax/page",
                      "url": "https://platform.minimax.cn/docs/page", "sha256": hashlib.sha256(body).hexdigest()}
            result = {"errors": [], "sources": [record], "checked_at": "captured-time",
                      "changes": [{"key": "minimax/page"}]}
            (audit / "result.json").write_text(json.dumps(result))
            (audit / "report.md").write_text("# Captured changes\n")
            destination = root / "upstream/minimax"
            snapshots = root / "snapshots"
            fingerprint = pr.stage("minimax", audit, destination, snapshots, write=False)
            self.assertFalse(destination.exists() or snapshots.exists())
            digest = pr.stage("minimax", audit, destination, snapshots)
            self.assertEqual(digest, fingerprint)
            self.assertTrue(digest)
            self.assertEqual(json.loads((destination / "baseline.json").read_text())["sources"], [record])
            self.assertTrue((destination / "review" / digest / "report.md").exists())
            self.assertFalse((root / "upstream/ali-bailian").exists())
            previous = (destination / "baseline.json").read_bytes()
            (audit / "minimax/page.md").write_bytes(b"corrupted")
            with self.assertRaises(ValueError):
                pr.stage("minimax", audit, destination, snapshots)
            self.assertEqual((destination / "baseline.json").read_bytes(), previous)

    def test_failed_or_cross_platform_audit_creates_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for result in ({"errors": ["failed"]},
                           {"errors": [], "sources": [{"server": "ali-bailian"}]}):
                (root / "result.json").write_text(json.dumps(result))
                with self.assertRaises(ValueError):
                    pr.stage("minimax", root, root / "destination", root / "snapshots")
                self.assertFalse((root / "destination").exists())


if __name__ == "__main__":
    unittest.main()
