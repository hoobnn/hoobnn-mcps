"""Keep standalone distributions on one reviewed runtime source."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("transport.py", "mcp_runtime.py", "jobs.py")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for name in ("ali-bailian", "volcengine-ark", "doubao-speech"):
        package = ROOT / "servers" / name / "src" / (name.replace("-", "_") + "_mcp")
        for module in MODULES:
            source = (ROOT / "shared" / module).read_bytes()
            target = package / module
            if not target.exists() or target.read_bytes() != source:
                stale.append(str(target.relative_to(ROOT)))
                if not args.check:
                    target.write_bytes(source)
    if args.check and stale:
        parser.exit(1, "Shared sources out of sync: " + ", ".join(stale) + "\n")


if __name__ == "__main__":
    main()
