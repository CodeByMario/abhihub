import os
import json
import pytest

# Ensure dummy env vars so Supabase client doesn't crash test import
os.environ.setdefault("SECRET_KEY", "test-production-smoke-key")
os.environ.setdefault("SUPABASE_URL", "https://mock-supabase.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "mock-supabase-key")

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get("status") == "healthy"
    assert data.get("service") == "abhihub"
    assert "version" in data


def test_api_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data is not None
    assert data.get("status") == "healthy"


def test_static_sw_served(client):
    response = client.get("/static/sw.js")
    assert response.status_code == 200
    assert b"CACHE_NAME" in response.data or b"self.addEventListener" in response.data


def test_static_manifest_served(client):
    response = client.get("/static/manifest.json")
    assert response.status_code == 200
    manifest = json.loads(response.data.decode("utf-8"))
    assert "name" in manifest
    assert "icons" in manifest
