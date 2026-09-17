import os
import json
import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist" / "production-artifact"
MANIFEST_FILE = ROOT_DIR / "release" / "production-manifest.json"


def test_manifest_structure():
    assert MANIFEST_FILE.exists(), "release/production-manifest.json must exist"
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "allowlist" in data
    assert "denylist" in data
    assert "required_environment_variables" in data
    assert "SECRET_KEY" in data["required_environment_variables"]
    assert "SUPABASE_URL" in data["required_environment_variables"]
    assert "SUPABASE_KEY" in data["required_environment_variables"]


def test_build_and_inspect_artifact():
    # Run the packager
    import importlib.util
    builder_path = ROOT_DIR / "release" / "build-production-artifact.py"
    spec = importlib.util.spec_from_file_location("packager", builder_path)
    packager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packager)

    file_count, total_bytes = packager.build_artifact()
    assert file_count > 0
    assert total_bytes > 0

    # Ensure critical runtime files exist in packaged output
    assert (DIST_DIR / "app.py").exists()
    assert (DIST_DIR / "gunicorn.conf.py").exists()
    assert (DIST_DIR / "Procfile").exists()
    assert (DIST_DIR / "requirements.txt").exists()
    assert (DIST_DIR / "static" / "sw.js").exists()
    assert (DIST_DIR / "static" / "manifest.json").exists()
    assert (DIST_DIR / "templates" / "offline.html").exists()

    # Ensure forbidden files DO NOT exist
    assert not (DIST_DIR / ".env").exists()
    assert not (DIST_DIR / ".git").exists()
    assert not (DIST_DIR / "tests").exists()
    assert not (DIST_DIR / "docs").exists()
    assert not (DIST_DIR / "conductor").exists()
    assert not (DIST_DIR / "README.md").exists()
    assert not (DIST_DIR / "bot.py").exists()
    assert not (DIST_DIR / "setup.py").exists()
