"""Failure gates for automatically proposing reviewed upstream baselines."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "upstream_codex", Path(__file__).resolve().parents[1] / "scripts/upstream_codex.py")
codex = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codex)


class AutomationGates(unittest.TestCase):
    def test_fingerprint_ignores_order_and_checked_time_but_detects_content(self):
        result = {"errors": [], "sources": [{"key": "b", "sha256": "2"}, {"key": "a", "sha256": "1"}]}
        digest = codex.fingerprint(result)
        result["sources"].reverse()
        result["checked_at"] = "later"
        self.assertEqual(digest, codex.fingerprint(result))
        result["sources"][0]["sha256"] = "3"
        self.assertNotEqual(digest, codex.fingerprint(result))
        result["errors"] = [{"error": "fetch failed"}]
        with self.assertRaises(ValueError):
            codex.fingerprint(result)

    def test_allowlist_protects_automation_and_baseline(self):
        for path in (".github/workflows/test.yml", "scripts/upstream_codex.py", "docs/upstream/baseline.json", ".env"):
            self.assertFalse(codex.allowed(path))
        for path in ("servers/minimax/new.py", "tests/test_new.py", "shared/transport.py", "docs/audits/minimax.md", "README.en.md"):
            self.assertTrue(codex.allowed(path))

    def test_blocked_decision_never_exports(self):
        with patch.object(codex.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                codex.export_patch({"status": "blocked"})
            run.assert_not_called()

    def test_baseline_verifies_all_bodies_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            audit = root / "audit"
            (audit / "provider").mkdir(parents=True)
            content = b"# verified official body\n"
            (audit / "provider/page.md").write_bytes(content)
            record = {"key": "provider/page", "server": "provider", "id": "page",
                      "sha256": hashlib.sha256(content).hexdigest()}
            result = {"errors": [], "sources": [record], "checked_at": "captured-time"}
            baseline = root / "baseline.json"
            with patch.object(codex, "AUDIT", audit):
                codex.accept_captured(result, baseline, root / "snapshots")
                self.assertEqual(json.loads(baseline.read_text())["reviewed_at"], "captured-time")
                previous = baseline.read_bytes()
                result["sources"].append(dict(record, id="missing"))
                with self.assertRaises(FileNotFoundError):
                    codex.accept_captured(result, baseline, root / "snapshots")
                self.assertEqual(previous, baseline.read_bytes())

    def test_patch_includes_new_files_and_rejects_protected_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "commit.gpgsign=false", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                            "commit", "--allow-empty", "-qm", "initial"], check=True)
            (root / ".upstream-docs").mkdir()
            (root / "tests").mkdir()
            (root / "tests/new.py").write_text("# new contract test\n")
            (root / ".git/info/exclude").write_text(".upstream-docs/\n")
            with patch.object(codex, "ROOT", root), patch.object(codex, "AUDIT", root / ".upstream-docs"):
                codex.export_patch({"status": "ready"})
                self.assertIn(b"tests/new.py", (root / ".upstream-docs/codex.patch").read_bytes())
                (root / "protected.txt").write_text("forbidden")
                with self.assertRaises(ValueError):
                    codex.export_patch({"status": "ready"})


if __name__ == "__main__":
    unittest.main()
