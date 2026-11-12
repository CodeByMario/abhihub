import os
import pytest
from dotenv import load_dotenv

# Force load real environment overrides for live database testing
load_dotenv(override=True)

# Import app first so gevent monkey patching runs before any HTTP/SSL sockets are created
from app import app
app.config["TESTING"] = True

import methods.supabase_helper as sb_helper
# Reset any cached module globals with real credentials
sb_helper.SUPABASE_URL = os.getenv("SUPABASE_URL")
sb_helper.SUPABASE_SECRET_API_KEY = os.getenv("SUPABASE_SECRET_API_KEY") or ""
sb_helper.SUPABASE_KEY = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_PUBLIC_API_KEY") or ""
sb_helper.reset_thread_client()

from methods.supabase_helper import (
    init_supabase,
    init_supabase_admin,
    toggle_bookmark,
    toggle_like,
)

SUPABASE_CONFIGURED = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SECRET_API_KEY"))


@pytest.mark.skipif(not SUPABASE_CONFIGURED, reason="Live Supabase credentials not set in environment")
class TestSupabaseDatabaseAccess:

    def test_admin_client_connection(self):
        """Verify server admin client connects with service_role privileges."""
        client = init_supabase_admin()
        assert client is not None, "Failed to initialize Supabase admin client"
        res = client.table("documents").select("id").limit(1).execute()
        assert res.data is not None
        assert isinstance(res.data, list)

    def test_profiles_read_access(self):
        """Verify profiles table query succeeds without RLS block."""
        client = init_supabase_admin()
        res = client.table("profiles").select("id, email").limit(1).execute()
        assert res.data is not None

    def test_bookmarks_toggle_and_rls(self):
        """Verify bookmark insert/delete operates cleanly via service_role without error 42501."""
        client = init_supabase_admin()
        user_res = client.table("profiles").select("email").limit(1).execute()
        doc_res = client.table("documents").select("id").limit(1).execute()

        if not user_res.data or not doc_res.data:
            pytest.skip("Insufficient test data (profiles or documents table empty)")

        user_email = user_res.data[0]["email"]
        doc_id = doc_res.data[0]["id"]

        # 1st toggle: bookmark
        res1 = toggle_bookmark(user_email, doc_id)
        assert res1.get("success") is True, f"toggle_bookmark failed: {res1}"
        assert "is_bookmarked" in res1

        # 2nd toggle: unbookmark
        res2 = toggle_bookmark(user_email, doc_id)
        assert res2.get("success") is True, f"toggle_bookmark undo failed: {res2}"
        assert res2.get("is_bookmarked") != res1.get("is_bookmarked")

    def test_document_votes_toggle_and_rls(self):
        """Verify document_votes insert/delete operates cleanly without RLS 42501."""
        client = init_supabase_admin()
        user_res = client.table("profiles").select("email").limit(1).execute()
        doc_res = client.table("documents").select("id").limit(1).execute()

        if not user_res.data or not doc_res.data:
            pytest.skip("Insufficient test data (profiles or documents table empty)")

        user_email = user_res.data[0]["email"]
        doc_id = doc_res.data[0]["id"]

        # 1st toggle
        res1 = toggle_like(user_email, doc_id)
        assert res1.get("success") is True, f"toggle_like failed: {res1}"
        assert "is_liked" in res1

        # 2nd toggle: undo like
        res2 = toggle_like(user_email, doc_id)
        assert res2.get("success") is True, f"toggle_like undo failed: {res2}"
        assert res2.get("is_liked") != res1.get("is_liked")

    def test_interaction_api_endpoints(self):
        """Verify Flask interaction routes gate bookmarks and likes."""
        from app import app
        app.config["TESTING"] = True
        client = app.test_client()

        # Unauthenticated calls must be blocked
        r_like = client.post("/api/interactions/like", json={"document_id": "test"})
        assert r_like.status_code in (401, 302)

        r_bm = client.post("/api/interactions/bookmark", json={"document_id": "test"})
        assert r_bm.status_code in (401, 302)

    def test_login_and_auth_endpoints(self):
        """Verify login, signup pages and unauthenticated access restrictions."""
        from app import app
        app.config["TESTING"] = True
        client = app.test_client()

        # Public auth routes load cleanly
        assert client.get("/login").status_code == 200
        assert client.get("/signup").status_code == 200

        # Unauthenticated session redirected from protected dashboard
        res_dash = client.get("/dashboard")
        assert res_dash.status_code in (301, 302, 307, 308, 401)

    def test_file_and_document_endpoints(self):
        """Verify file access and document pricing endpoints."""
        from app import app
        import uuid
        app.config["TESTING"] = True
        client = app.test_client()

        # Check with existing document or fallback UUID
        client_admin = init_supabase_admin()
        doc_res = client_admin.table("documents").select("id").limit(1).execute()
        target_doc_id = doc_res.data[0]["id"] if doc_res.data else str(uuid.uuid4())

        r_access = client.get(f"/api/document/{target_doc_id}/access")
        assert r_access.status_code == 200
        assert r_access.get_json().get("success") is True

        r_pricing = client.get(f"/api/document/{target_doc_id}/pricing")
        assert r_pricing.status_code in (200, 404)
        assert "success" in r_pricing.get_json()

    def test_points_and_passbook_endpoints(self):
        """Verify points/passbook/wallet requires authentication."""
        from app import app
        import uuid
        app.config["TESTING"] = True
        client = app.test_client()

        # Unauthenticated calls rejected
        assert client.get("/api/user/passbook").status_code in (401, 302)
        assert client.get("/api/creator/wallet").status_code in (401, 302)
        assert client.get("/api/creator/earnings").status_code in (401, 302)

        # Authenticated session succeeds
        valid_uuid = str(uuid.uuid4())
        with client.session_transaction() as sess:
            sess["user"] = {"id": valid_uuid, "uid": valid_uuid, "email": "techie667@gmail.com"}

        res_wallet = client.get("/api/creator/wallet")
        assert res_wallet.status_code == 200
        assert res_wallet.get_json().get("success") is True

    def test_payment_endpoints(self):
        """Verify payment initiation, verification, and status endpoints."""
        from app import app
        app.config["TESTING"] = True
        client = app.test_client()

        # Unauthenticated payment attempts rejected with 401/302
        assert client.post("/api/create-order", json={"amount": 100}).status_code in (401, 302)
        assert client.post("/api/payment/status", json={"order_id": "ord_1"}).status_code in (401, 302)
        assert client.post("/api/verify-payment", json={"razorpay_order_id": "ord_1"}).status_code in (401, 302)
        assert client.post("/api/payment/phonepe/initiate", json={"amount": 100}).status_code in (401, 302)

    def test_pdf_upload_as_txt_pipeline(self):
        """Verify PDF local rename and upload to cloud storage with .txt extension."""
        import io
        from unittest.mock import patch
        from methods import cloudinary_upload

        fake_pdf = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 1\n0000000000 65535 f\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
        fake_response = {
            "success": True,
            "url": "http://res.cloudinary.com/test/lecture.txt",
            "secure_url": "https://res.cloudinary.com/test/lecture.txt",
            "public_id": "uploads/lecture.txt",
            "resource_type": "raw",
            "format": "txt",
            "bytes": len(fake_pdf)
        }

        with patch.object(cloudinary_upload.cloudinary.uploader, "upload", return_value=fake_response) as mock_upload, \
             patch("threading.Thread"):
            res = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(fake_pdf), "lecture.pdf", "user_123", compress=False
            )

        assert res["success"] is True
        assert res["pdf_uploaded_as_txt"] is True
        assert res["uploaded_extension"] == "txt"
        assert mock_upload.call_args.kwargs["resource_type"] == "raw"
        assert mock_upload.call_args.kwargs["public_id"].endswith(".txt")

    def test_image_upload_direct_pipeline(self):
        """Verify image direct compression, rename, and upload as image."""
        import io
        from PIL import Image
        from unittest.mock import patch
        from methods import cloudinary_upload

        img_buf = io.BytesIO()
        Image.new("RGB", (10, 10), "red").save(img_buf, format="PNG")
        fake_png = img_buf.getvalue()

        fake_response = {
            "success": True,
            "url": "http://res.cloudinary.com/test/photo.png",
            "secure_url": "https://res.cloudinary.com/test/photo.png",
            "public_id": "uploads/photo",
            "resource_type": "image",
            "format": "png",
            "bytes": len(fake_png)
        }

        with patch.object(cloudinary_upload.cloudinary.uploader, "upload", return_value=fake_response) as mock_upload, \
             patch("threading.Thread"):
            res = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(fake_png), "diagram.png", "user_123", compress=False
            )

        assert res["success"] is True
        assert mock_upload.call_args.kwargs["resource_type"] == "image"
        assert mock_upload.call_args.kwargs["type"] == "authenticated"
        assert "user_123" in mock_upload.call_args.kwargs["public_id"]


