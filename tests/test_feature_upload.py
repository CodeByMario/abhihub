import io
from unittest.mock import patch

import pytest

from app import app


@pytest.fixture
def client():
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["user"] = {"uid": "user-1", "email": "user@example.com"}
        yield client


@pytest.mark.parametrize(
    ("name", "payload", "status"),
    [
        ("empty.pdf", b"", 400),
        ("bad.exe", b"MZinvalid", 400),
    ],
)
def test_upload_rejects_empty_and_disallowed_files(client, name, payload, status):
    response = client.post(
        "/upload",
        data={"upload_document": (io.BytesIO(payload), name)},
        content_type="multipart/form-data",
    )
    assert response.status_code == status


def test_pdf_upload_uses_txt_cloudinary_id_and_returns_pdf_metadata(client):
    from methods.cloudinary_upload import upload_file_to_cloudinary
    with patch("methods.cloudinary_upload.cloudinary.uploader.upload", return_value={
        "secure_url": "https://res.cloudinary.com/test/raw/upload/u_1.txt",
        "public_id": "uploads/u_1.txt",
        "resource_type": "raw",
        "bytes": 10,
    }), patch("threading.Thread"):
        result = upload_file_to_cloudinary(io.BytesIO(b"%PDF-1.4 test"), "paper.pdf", "user-1", compress=False)
    assert result["success"]
    assert result["pdf_uploaded_as_txt"] is True
    assert result["public_id"].endswith(".txt")


def test_upload_persists_paid_price(client):
    import json
    from data.pricing import extract_document_pricing
    payload = json.dumps({"text_description": "Notes", "pricing": {
        "is_paid": True, "price": 49.0, "seller_id": "user-1"
    }})
    pricing = extract_document_pricing({"description": payload})
    assert pricing["is_paid"] is True
    assert pricing["price"] == 49.0
