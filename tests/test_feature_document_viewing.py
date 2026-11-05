from unittest.mock import MagicMock, patch

from app import app


def test_view_doc_requires_existing_document():
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": False}):
        response = app.test_client().get("/api/view-doc/missing")
    assert response.status_code == 404


def test_paid_document_requires_access():
    document = {
        "id": "doc-1",
        "file_type": "image",
        "file_url": "https://res.cloudinary.com/test/image/upload/doc.jpg",
        "description": '{"pricing":{"is_paid":true,"price":10}}',
    }
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": True, "data": document}), \
         patch("routes.api.has_document_access", return_value=False):
        response = app.test_client().get("/api/view-doc/doc-1")
    assert response.status_code == 402


def test_pdf_view_endpoint_exposes_pdf_content_type_for_txt_storage():
    from routes.api import extract_document_pricing

    pricing = extract_document_pricing({"description": '{"pricing":{"is_paid":false}}'})
    assert pricing.get("is_paid") is False


def test_authorize_endpoint_returns_direct_cloud_url():
    document = {
        "id": "doc-auth-1",
        "title": "Machine Learning Notes",
        "file_type": "pdf",
        "file_url": "https://res.cloudinary.com/test/raw/upload/uploads/ml_notes.txt",
        "status": "approved",
    }
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": True, "data": document}), \
         patch("routes.api.has_document_access", return_value=True), \
         patch("routes.api.extract_document_pricing", return_value={"is_paid": False}):
        response = app.test_client().get("/api/documents/doc-auth-1/authorize")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["document_id"] == "doc-auth-1"
    assert data["file_type"] == "application/pdf"
    assert "file_url" in data
    assert "https://res.cloudinary.com" in data["file_url"]
    assert "file_version" in data


def test_authorize_endpoint_handles_unauthorized_paid_document():
    document = {
        "id": "doc-paid-lock",
        "title": "Exam Paper 2026",
        "file_type": "pdf",
        "file_url": "https://res.cloudinary.com/test/raw/upload/uploads/exam.txt",
        "description": '{"pricing":{"is_paid":true,"price":99}}',
    }
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": True, "data": document}), \
         patch("routes.api.has_document_access", return_value=False), \
         patch("routes.api.extract_document_pricing", return_value={"is_paid": True, "price": 99.0}):
        response = app.test_client().get("/api/documents/doc-paid-lock/authorize")
    assert response.status_code == 402
    data = response.get_json()
    assert data["success"] is False
    assert data["error"] == "payment_required"
    assert data["price"] == 99.0


def test_view_doc_redirects_to_cloud_storage_in_production():
    document = {
        "id": "doc-redirect-1",
        "title": "Operating Systems",
        "file_type": "pdf",
        "file_url": "https://res.cloudinary.com/test/raw/upload/uploads/os.txt",
        "status": "approved",
    }
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": True, "data": document}), \
         patch("routes.api.has_document_access", return_value=True), \
         patch("routes.api.extract_document_pricing", return_value={"is_paid": False}), \
         patch.dict(app.config, {"TESTING": False}):
        response = app.test_client().get("/api/view-doc/doc-redirect-1/document.pdf")
    assert response.status_code == 302
    assert "res.cloudinary.com" in response.headers.get("Location", "")


def test_view_doc_with_format_json_returns_metadata():
    document = {
        "id": "doc-json-1",
        "title": "Data Science Guide",
        "file_type": "pdf",
        "file_url": "https://res.cloudinary.com/test/raw/upload/uploads/ds.txt",
        "status": "approved",
    }
    with patch("methods.supabase_helper.get_document_by_id_rich", return_value={"success": True, "data": document}), \
         patch("routes.api.has_document_access", return_value=True), \
         patch("routes.api.extract_document_pricing", return_value={"is_paid": False}):
        response = app.test_client().get("/api/view-doc/doc-json-1/document.pdf?format=json")
    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["document_id"] == "doc-json-1"
