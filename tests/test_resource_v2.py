"""
Tests for Resource Detail Page Redesign (v2) and Feature Flag Switcher.
Verifies backward compatibility, canonical redirects, noindex enforcement,
server-side mock gating, and anti-piracy (zero download links).
"""

import os
import pytest
from unittest.mock import patch
from app import app


@pytest.fixture
def test_client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        yield client


@pytest.fixture
def mock_sample_doc():
    return {
        "success": True,
        "data": {
            "id": "c0007903-5e53-4e06-95b1-5169e7a4dece",
            "title": "Daa - CAE2",
            "file_type": "image",
            "file_url": "https://example.com/sample-paper.jpg",
            "file_size_bytes": 1048576,
            "document_category": "pyq",
            "description": '{"subject": "Design and Analysis of Algorithms", "exam": "CAE2", "marks": 50}',
            "topics_covered": ["Floyd-Warshall", "Graph Colouring"],
            "created_at": "2026-09-01T12:00:00Z",
            "updated_at": "2026-09-01T12:00:00Z",
            "view_count": 42,
            "like_count": 10,
            "bookmark_count": 5,
            "comment_count": 2,
            "subject_id": "subj-123",
            "college": {"name": "G. H. Raisoni College of Engineering", "abbreviation": "GHRCE"},
            "department": {"name": "Computer Science and Engineering", "abbreviation": "CSE"},
            "subject": {"name": "Design and Analysis of Algorithms"},
            "uploader": {"full_name": "Abhijeet", "is_verified": True},
        },
    }


def test_resource_flag_off_renders_legacy(test_client, mock_sample_doc):
    """When ?redesign=1 is absent, the page renders the legacy resource.html."""
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc), \
         patch("app.log_document_view"):
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "resource-hero" in html
        assert "resource-v2-page" not in html


def test_resource_flag_on_renders_v2(test_client, mock_sample_doc):
    """When ?redesign=1 is provided, the page renders resource_v2.html with noindex."""
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc), \
         patch("app.log_document_view"):
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "resource-v2-page" in html
        assert "r2-container" in html
        # Must have noindex tag for redesign preview
        assert 'name="robots" content="noindex' in html or 'noindex' in html


def test_canonical_redirect_preserves_query(test_client, mock_sample_doc):
    """301 Canonical redirect must preserve the ?redesign=1 query string."""
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc):
        res = test_client.get("/resource/wrong-slug-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        assert res.status_code == 301
        location = res.headers.get("Location", "")
        assert "ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece" in location
        assert "redesign=1" in location


def test_no_download_links_in_v2_and_legacy(test_client, mock_sample_doc):
    """Verify zero download buttons or download anchors exist in either template."""
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc), \
         patch("app.log_document_view"):
        # Legacy
        res_legacy = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece")
        html_legacy = res_legacy.data.decode("utf-8")
        assert 'download=""' not in html_legacy
        assert 'download=' not in html_legacy or '&download=false' in html_legacy
        assert '<button class="download-btn"' not in html_legacy

        # V2
        res_v2 = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        html_v2 = res_v2.data.decode("utf-8")
        assert 'download=""' not in html_v2
        assert 'download=' not in html_v2 or '&download=false' in html_v2
        assert '<button class="download-btn"' not in html_v2


def test_mock_study_kit_ignored_in_production(test_client, mock_sample_doc, monkeypatch):
    """MOCK_STUDY_KIT must be completely suppressed when app runs in production mode."""
    import flask
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("MOCK_STUDY_KIT", "1")
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc), \
         patch("app.log_document_view"), \
         patch("app.render_template", side_effect=flask.render_template) as mock_render:
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        assert res.status_code == 200
        assert mock_render.called
        kwargs = mock_render.call_args[1]
        assert kwargs.get("mock_study_kit") is False


def test_pdf_viewer_disables_downloads(test_client, mock_sample_doc):
    """When document is a PDF, the viewer iframe is loaded with download=false."""
    pdf_doc = dict(mock_sample_doc)
    pdf_doc["data"] = dict(mock_sample_doc["data"])
    pdf_doc["data"]["file_type"] = "pdf"
    pdf_doc["data"]["file_url"] = "https://example.com/sample-paper.pdf"

    with patch("app.get_document_by_id_rich", return_value=pdf_doc), \
         patch("app.log_document_view"):
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        assert res.status_code == 200
        html = res.data.decode("utf-8")
        assert "&download=false" in html


def test_questions_rendered_when_present_and_omitted_when_absent(test_client, mock_sample_doc):
    """Question list and pins appear when topics_covered has items, and disappear when empty."""
    # Present
    with patch("app.get_document_by_id_rich", return_value=mock_sample_doc), \
         patch("app.log_document_view"):
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        html = res.data.decode("utf-8")
        assert "Floyd-Warshall" in html
        assert "Solve with Tarika" in html

    # Absent
    no_topics_doc = dict(mock_sample_doc)
    no_topics_doc["data"] = dict(mock_sample_doc["data"])
    no_topics_doc["data"]["topics_covered"] = []
    with patch("app.get_document_by_id_rich", return_value=no_topics_doc), \
         patch("app.log_document_view"):
        res = test_client.get("/resource/ghrce-cse-design-and-analysis-of-algorithms-daa-cae2-c0007903-5e53-4e06-95b1-5169e7a4dece?redesign=1")
        html = res.data.decode("utf-8")
        assert "Solve with Tarika" not in html
