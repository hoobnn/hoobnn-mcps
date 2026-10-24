"""Stage one platform's captured documentation as a human-reviewed PR."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

from upstream_docs import ROOT, SERVERS, atomic_bytes, atomic_json


def stage(server, audit, destination, snapshots, write=True):
    result = json.loads((audit / "result.json").read_text())
    if result["errors"]:
        raise ValueError("Incomplete platform audit; refusing PR baseline")
    records = result["sources"]
    if not records or any(r["server"] != server for r in records):
        raise ValueError("Empty or mixed platform audit")
    if any(not c["key"].startswith(server + "/") for c in result["changes"]):
        raise ValueError("Cross-platform change")
    captured = []
    for record in records:
        path = audit / server / (record["id"] + ".md")
        if not path.resolve().is_relative_to((audit / server).resolve()):
            raise ValueError("Unsafe captured body path")
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != record["sha256"]:
            raise ValueError("Captured fingerprint mismatch")
        captured.append((record["sha256"], content))
    # No write occurs until all captured bodies have passed validation.
    digest = hashlib.sha256(json.dumps(sorted(
        (r["key"], r["sha256"], r["url"], r.get("fetch_url"), r.get("tools", []))
        for r in records), separators=(",", ":")).encode()).hexdigest()
    if not result["changes"]:
        return None
    if not write:
        return digest
    destination.mkdir(parents=True, exist_ok=True)
    for sha, content in captured:
        atomic_bytes(snapshots / (sha + ".md.gz"), gzip.compress(content, mtime=0))
    atomic_json(destination / "baseline.json", {
        "format_version": 1, "reviewed_at": result["checked_at"], "sources": records})
    review = destination / "review" / digest
    review.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(audit / "report.md", review / "report.md")
    shutil.copyfile(audit / "result.json", review / "result.json")
    if (audit / "diffs" / server).exists():
        shutil.copytree(audit / "diffs" / server, review / "diffs")
    return digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", required=True, choices=SERVERS)
    parser.add_argument("--output", type=Path, default=ROOT / ".upstream-docs")
    parser.add_argument("--fingerprint-only", action="store_true",
                        help="validate and print the capture fingerprint without writing the repository")
    args = parser.parse_args()
    digest = stage(args.server, args.output, ROOT / "docs/upstream" / args.server,
                   ROOT / "docs/upstream/snapshots", write=not args.fingerprint_only)
    import os
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        output.write(f"changed={'true' if digest else 'false'}\nfingerprint={digest or ''}\n")


if __name__ == "__main__":
    main()
