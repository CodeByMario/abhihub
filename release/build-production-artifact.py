#!/usr/bin/env python3
"""Build a sanitized production artifact from the repository root."""

import json
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = Path(__file__).resolve().parent / "production-manifest.json"
OUTPUT_DIR = ROOT_DIR / "dist" / "production-artifact"


def _is_denied(relative_path: Path, denylist: set[str]) -> bool:
    return any(part in denylist for part in relative_path.parts)


def build_artifact() -> tuple[int, int]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    allowlist = [Path(item) for item in manifest["allowlist"]]
    denylist = set(manifest["denylist"])

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    copied_files = 0
    copied_bytes = 0
    for relative_path in allowlist:
        source = ROOT_DIR / relative_path
        if not source.exists() or _is_denied(relative_path, denylist):
            continue

        destination = OUTPUT_DIR / relative_path
        if source.is_dir():
            shutil.copytree(
                source,
                destination,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", ".env", ".git", "tests", "docs"
                ),
            )
            files = [path for path in destination.rglob("*") if path.is_file()]
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            files = [destination]

        for path in files:
            copied_files += 1
            copied_bytes += path.stat().st_size

    return copied_files, copied_bytes


if __name__ == "__main__":
    count, size = build_artifact()
    print(f"Built {count} files ({size} bytes) at {OUTPUT_DIR}")
