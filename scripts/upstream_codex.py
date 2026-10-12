"""Trusted orchestration for the upstream-document Codex workflow (no network)."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(os.environ.get("UPSTREAM_REPO_ROOT", Path(__file__).resolve().parents[1]))
AUDIT = ROOT / ".upstream-docs"


def fingerprint(result):
    if result["errors"]:
        raise ValueError("Incomplete audit; refusing Codex and baseline acceptance")
    payload = sorted((r["key"], r["sha256"]) for r in result["sources"])
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def allowed(path):
    return (path in {"README.md", "README.en.md"} or
            path.startswith(("servers/", "shared/", "tests/")) or
            (path.startswith("docs/") and not path.startswith("docs/upstream/")))


def export_patch(decision):
    if decision["status"] != "ready":
        raise ValueError("Codex could not fully reconcile the audit; baseline remains unchanged")
    subprocess.run(["git", "add", "-N", "."], cwd=ROOT, check=True)
    paths = subprocess.check_output(["git", "diff", "--name-only", "-z", "HEAD"], cwd=ROOT)
    for path in paths.decode().split("\0"):
        if not path:
            continue
        file = ROOT / path
        if not allowed(path) or file.is_symlink() or not file.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError(f"Codex edited a protected path: {path}")
    patch = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    (AUDIT / "codex.patch").write_bytes(patch)


def accept_captured(result, baseline_path, snapshot_dir):
    """Accept exactly the validated audit, never re-fetch newer unseen documents."""
    fingerprint(result)
    captured = []
    for record in result["sources"]:
        body = AUDIT / record["server"] / (record["id"] + ".md")
        if not body.resolve().is_relative_to(AUDIT.resolve()):
            raise ValueError("Captured document path escaped audit directory")
        content = body.read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError(f"Captured body fingerprint mismatch: {record['key']}")
        captured.append((record["sha256"], content))
    # Verify all documents before writing anything.
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for digest, content in captured:
        (snapshot_dir / (digest + ".md.gz")).write_bytes(gzip.compress(content, mtime=0))
    baseline_path.write_text(json.dumps({"format_version": 1, "reviewed_at": result["checked_at"],
                                         "sources": result["sources"]}, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "export", "accept"))
    args = parser.parse_args()
    result = json.loads((AUDIT / "result.json").read_text())
    digest = fingerprint(result)
    if args.command == "prepare":
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write(f"changed={'true' if result['changes'] else 'false'}\nfingerprint={digest}\n")
    elif args.command == "export":
        export_patch(json.loads((AUDIT / "decision.json").read_text()))
    else:
        if json.loads((AUDIT / "decision.json").read_text())["status"] != "ready":
            raise ValueError("Blocked decision; refusing baseline")
        accept_captured(result, ROOT / "docs/upstream/baseline.json", ROOT / "docs/upstream/snapshots")


if __name__ == "__main__":
    main()
