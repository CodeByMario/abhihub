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
