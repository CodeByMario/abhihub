#!/usr/bin/env python3
"""
AbhiHub Production Artifact Packager & Inspector
================================================
Builds a minimal, allowlisted production runtime package in dist/production-artifact/
and verifies zero secret/dev bloat leakage.
"""

import os
import sys
import json
import shutil
import hashlib
import fnmatch
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist" / "production-artifact"
MANIFEST_FILE = ROOT_DIR / "release" / "production-manifest.json"


def load_manifest():
    if not MANIFEST_FILE.exists():
        print(f"[ERROR] Manifest file not found: {MANIFEST_FILE}")
        sys.exit(1)
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_denylisted(rel_path: str, denylist: list) -> bool:
    rel_posix = rel_path.replace("\\", "/")
    for rule in denylist:
        pattern = rule.get("pattern", "")
        if fnmatch.fnmatch(rel_posix, pattern) or fnmatch.fnmatch(os.path.basename(rel_posix), pattern):
            return True
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
                return True
        elif pattern.endswith("/"):
            if rel_posix.startswith(pattern):
                return True
    return False


def build_artifact():
    print("[1/5] Loading production manifest...")
    manifest = load_manifest()
    allowlist = manifest.get("allowlist", [])
    denylist = manifest.get("denylist", [])

    print(f"[2/5] Preparing clean output directory: {DIST_DIR}")
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    print("[3/5] Packaging allowlisted runtime files...")
    copied_files = []

    for item in allowlist:
        if item.endswith("/**"):
            dir_name = item[:-3]
            src_dir = ROOT_DIR / dir_name
            if src_dir.exists() and src_dir.is_dir():
                for root, dirs, files in os.walk(src_dir):
                    # Filter out __pycache__ or hidden dirs
                    dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__" and d != "cache" and d != "raw"]
                    for file in files:
                        if file.startswith("."):
                            continue
                        src_file = Path(root) / file
                        rel_file = src_file.relative_to(ROOT_DIR).as_posix()
                        if not is_denylisted(rel_file, denylist):
                            dest_file = DIST_DIR / rel_file
                            dest_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src_file, dest_file)
                            copied_files.append(rel_file)
        else:
            src_file = ROOT_DIR / item
            if src_file.exists() and src_file.is_file():
                rel_file = Path(item).as_posix()
                if not is_denylisted(rel_file, denylist):
                    dest_file = DIST_DIR / rel_file
                    dest_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dest_file)
                    copied_files.append(rel_file)

    print(f"[4/5] Generating SHA-256 integrity checksums for {len(copied_files)} files...")
    checksums = {}
    total_bytes = 0
    for rel_file in copied_files:
        filepath = DIST_DIR / rel_file
        sha = calculate_sha256(filepath)
        size = filepath.stat().st_size
        total_bytes += size
        checksums[rel_file] = {
            "sha256": sha,
            "size_bytes": size
        }

    checksum_file = DIST_DIR / "artifact-checksums.json"
    with open(checksum_file, "w", encoding="utf-8") as f:
        json.dump({
            "artifact_name": "abhihub-production-runtime",
            "file_count": len(copied_files),
            "total_size_bytes": total_bytes,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2),
            "checksums": checksums
        }, f, indent=2)

    print("[5/5] Running automated inspection checks...")
    errors = inspect_artifact(DIST_DIR, denylist)
    if errors:
        print("\n[FAILED] Artifact inspection encountered errors:")
        for err in errors:
            print(f"  [!] {err}")
        sys.exit(1)

    print("\n[SUCCESS] Artifact successfully packaged and verified!")
    print(f"   Output location: {DIST_DIR}")
    print(f"   Packaged files:  {len(copied_files)}")
    print(f"   Total size:      {round(total_bytes / (1024 * 1024), 2)} MB")
    return len(copied_files), total_bytes


def inspect_artifact(artifact_path: Path, denylist: list) -> list:
    errors = []
    required_files = [
        "app.py",
        "gunicorn.conf.py",
        "cache_manager.py",
        "push_api.py",
        "push_notifications.py",
        "scheduled_tasks.py",
        "firebase_config.py",
        "Procfile",
        "requirements.txt",
        "static/sw.js",
        "static/manifest.json",
        "templates/offline.html"
    ]

    for req in required_files:
        if not (artifact_path / req).exists():
            errors.append(f"Missing required runtime file: {req}")

    # Check for forbidden patterns
    forbidden_substrings = [".env", ".git", "test", ".pytest", ".md", "secret", "private_key"]
    for root, dirs, files in os.walk(artifact_path):
        for file in files:
            if file == "artifact-checksums.json":
                continue
            file_path = Path(root) / file
            rel_file = file_path.relative_to(artifact_path).as_posix()
            
            # Markdown check
            if file.endswith(".md"):
                errors.append(f"Forbidden Markdown file in runtime artifact: {rel_file}")
            
            # Env check
            if file.startswith(".env"):
                errors.append(f"Forbidden environment file in runtime artifact: {rel_file}")
                
            # Git check
            if ".git" in rel_file:
                errors.append(f"Forbidden Git file in runtime artifact: {rel_file}")
                
            # Scan contents for hardcoded live API keys or private keys
            if file.endswith((".py", ".json", ".js", ".html")):
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        if "-----BEGIN PRIVATE KEY-----" in content:
                            errors.append(f"Private cryptographic key leaked in: {rel_file}")
                        if "eyJhbGciOi" in content and len(content) > 1000 and "service_role" in content:
                            errors.append(f"Potential JWT secret token leaked in: {rel_file}")
                except Exception:
                    pass

    return errors


if __name__ == "__main__":
    build_artifact()
