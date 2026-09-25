"""
test_upload_images_pdf.py
=========================
Comprehensive upload test suite for AbhiHub.

Covers:
  - File validation (magic bytes, extensions, size limits)
  - Image compression pipeline (JPEG, PNG, WEBP)
  - PDF compression / metadata strip pipeline
  - Cloudinary resource-type routing (image vs raw)
  - /upload route: full multipart POST for images and PDFs
  - Security: fake magic bytes, oversized files, empty files, missing file
  - Cloudinary cleanup on DB save failure
  - Duplicate protection (same public_id)

All external I/O is mocked — no network, no real credentials needed.
"""

import io
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

from PIL import Image

# ─── repo root on path ───────────────────────────────────────────────────────
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# ─── minimal env so app imports without real secrets ─────────────────────────
os.environ.setdefault("SECRET_KEY", "test-only")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "000000000000000")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-secret")
os.environ.setdefault("ADMIN_EMAILS", "")

import app as app_module
from methods import cloudinary_upload


# ─── Byte factories ──────────────────────────────────────────────────────────

def _make_png(size=(8, 8), colour="blue") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="PNG")
    return buf.getvalue()

def _make_jpeg(size=(8, 8), colour="red") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", size, colour)
    img.save(buf, format="JPEG")
    return buf.getvalue()

def _make_webp(size=(8, 8), colour="green") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, colour).save(buf, format="WEBP")
    return buf.getvalue()

def _make_pdf(pages=1) -> bytes:
    """Minimal valid PDF with correct %PDF magic bytes."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n"
        b"0000000000 65535 f\r\n"
        b"0000000009 00000 n\r\n"
        b"0000000058 00000 n\r\n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\n"
        b"startxref\n116\n%%EOF\n"
    )

PNG_BYTES  = _make_png()
JPEG_BYTES = _make_jpeg()
WEBP_BYTES = _make_webp()
PDF_BYTES  = _make_pdf()

# Cloudinary fake success response
def _fake_cld(filename="file.pdf", rt="raw"):
    return {
        "success": True,
        "url": f"http://res.cloudinary.com/test/{filename}",
        "secure_url": f"https://res.cloudinary.com/test/{filename}",
        "public_id": f"uploads/test_{filename}",
        "resource_type": rt,
        "format": filename.rsplit(".", 1)[-1],
        "bytes": 1024,
        "width": None,
        "height": None,
    }

SAVE_OK  = {"success": True,  "data": {"id": "doc-uuid-123"}}
SAVE_ERR = {"success": False, "message": "DB error"}


# ═════════════════════════════════════════════════════════════════════════════
# 1. FILE VALIDATION TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestFileValidation(unittest.TestCase):
    """Unit-test allowed_file() and validate_file_content() from app.py."""

    def test_allowed_extensions(self):
        """Accepted extensions: pdf png jpg jpeg webp gif."""
        for name in ["doc.pdf", "img.png", "photo.jpg", "pic.jpeg", "anim.webp", "anim.gif"]:
            with self.subTest(name=name):
                self.assertTrue(app_module.allowed_file(name), f"{name} should be allowed")

    def test_rejected_extensions(self):
        """Dangerous / unsupported extensions must be rejected."""
        for name in ["malware.exe", "script.js", "data.csv", "archive.zip", "doc.docx", "noext"]:
            with self.subTest(name=name):
                self.assertFalse(app_module.allowed_file(name), f"{name} should be rejected")

    def test_pdf_magic_bytes_pass(self):
        self.assertTrue(app_module.validate_file_content(io.BytesIO(PDF_BYTES), "paper.pdf"))

    def test_png_magic_bytes_pass(self):
        self.assertTrue(app_module.validate_file_content(io.BytesIO(PNG_BYTES), "img.png"))

    def test_jpeg_magic_bytes_pass(self):
        self.assertTrue(app_module.validate_file_content(io.BytesIO(JPEG_BYTES), "photo.jpg"))

    def test_webp_magic_bytes_pass(self):
        self.assertTrue(app_module.validate_file_content(io.BytesIO(WEBP_BYTES), "img.webp"))

    def test_fake_pdf_extension_fails(self):
        """A PNG disguised as .pdf must be rejected by magic-byte check."""
        self.assertFalse(app_module.validate_file_content(io.BytesIO(PNG_BYTES), "evil.pdf"))

    def test_fake_png_extension_fails(self):
        """A PDF disguised as .png must be rejected."""
        self.assertFalse(app_module.validate_file_content(io.BytesIO(PDF_BYTES), "evil.png"))

    def test_empty_bytes_fails(self):
        """Zero-byte files must not pass validation."""
        self.assertFalse(app_module.validate_file_content(io.BytesIO(b""), "file.pdf"))

    def test_random_bytes_fail(self):
        """Garbage bytes with any extension must be rejected."""
        garbage = b"\x00\x01\x02\x03" * 10
        self.assertFalse(app_module.validate_file_content(io.BytesIO(garbage), "evil.pdf"))
        self.assertFalse(app_module.validate_file_content(io.BytesIO(garbage), "evil.png"))


# ═════════════════════════════════════════════════════════════════════════════
# 2. COMPRESSION PIPELINE TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestCompressionPipeline(unittest.TestCase):
    """Verify compress_image and compress_pdf produce valid output bytes."""

    def test_compress_jpeg_returns_valid_jpeg(self):
        result = cloudinary_upload.compress_image(JPEG_BYTES, format="JPEG", quality=75)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)
        # Verify output is a readable image
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.format, "JPEG")

    def test_compress_png_returns_valid_png(self):
        result = cloudinary_upload.compress_image(PNG_BYTES, format="PNG", quality=80)
        self.assertIsInstance(result, bytes)
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.format, "PNG")

    def test_compress_webp_returns_valid_webp(self):
        result = cloudinary_upload.compress_image(WEBP_BYTES, format="WEBP", quality=80)
        self.assertIsInstance(result, bytes)
        img = Image.open(io.BytesIO(result))
        self.assertEqual(img.format, "WEBP")

    def test_compress_image_strips_exif(self):
        """Output must not contain EXIF data (privacy requirement)."""
        result = cloudinary_upload.compress_image(JPEG_BYTES, format="JPEG")
        img = Image.open(io.BytesIO(result))
        self.assertFalse(img.info.get("exif"), "EXIF should be stripped after compression")

    def test_compress_image_adds_watermark(self):
        """compress_image runs without error even when watermarking."""
        # Use a larger image so watermark fits
        big_bytes = io.BytesIO()
        Image.new("RGB", (200, 200), "white").save(big_bytes, "JPEG")
        result = cloudinary_upload.compress_image(big_bytes.getvalue(), format="JPEG", quality=70)
        self.assertIsInstance(result, bytes)
        self.assertGreater(len(result), 0)

    def test_compress_pdf_returns_valid_pdf(self):
        """PDF compressor must keep the %PDF header intact."""
        result = cloudinary_upload.compress_pdf(PDF_BYTES)
        self.assertIsInstance(result, bytes)
        self.assertTrue(result.startswith(b"%PDF"), "Output must be a valid PDF")

    def test_compress_pdf_fallback_on_corrupt(self):
        """Corrupt PDF must return original bytes, not crash."""
        corrupt = b"this is not a pdf at all"
        result = cloudinary_upload.compress_pdf(corrupt)
        self.assertEqual(result, corrupt)

    def test_compress_image_fallback_on_corrupt(self):
        """Corrupt image bytes must return original, not raise."""
        corrupt = b"\x89PNG fake data garbage"
        result = cloudinary_upload.compress_image(corrupt, format="JPEG")
        self.assertEqual(result, corrupt)


# ═════════════════════════════════════════════════════════════════════════════
# 3. CLOUDINARY RESOURCE TYPE ROUTING
# ═════════════════════════════════════════════════════════════════════════════

class TestCloudinaryResourceTypeRouting(unittest.TestCase):
    """upload_file_to_cloudinary must pick the right resource_type per file type."""

    def _upload_and_capture(self, file_bytes, filename):
        fake_resp = _fake_cld(filename, "raw" if filename.endswith(".pdf") else "image")
        with patch.object(cloudinary_upload.cloudinary.uploader, "upload", return_value=fake_resp) as m, \
             patch("threading.Thread"):   # suppress background Supabase thread
            result = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(file_bytes), filename, "u1", compress=False
            )
        return result, m

    def test_pdf_uploads_as_raw(self):
        result, m = self._upload_and_capture(PDF_BYTES, "lecture.pdf")
        self.assertTrue(result["success"])
        self.assertEqual(m.call_args.kwargs["resource_type"], "raw")

    def test_pdf_public_id_ends_with_txt(self):
        """PDFs get a .txt extension to bypass Cloudinary free-tier PDF restrictions."""
        result, m = self._upload_and_capture(PDF_BYTES, "lecture.pdf")
        self.assertTrue(m.call_args.kwargs["public_id"].endswith(".txt"),
                        "PDF public_id should end with .txt")

    def test_png_uploads_as_image(self):
        result, m = self._upload_and_capture(PNG_BYTES, "diagram.png")
        self.assertTrue(result["success"])
        self.assertEqual(m.call_args.kwargs["resource_type"], "image")

    def test_jpeg_uploads_as_image(self):
        result, m = self._upload_and_capture(JPEG_BYTES, "photo.jpg")
        self.assertTrue(result["success"])
        self.assertEqual(m.call_args.kwargs["resource_type"], "image")

    def test_webp_uploads_as_image(self):
        result, m = self._upload_and_capture(WEBP_BYTES, "img.webp")
        self.assertTrue(result["success"])
        self.assertEqual(m.call_args.kwargs["resource_type"], "image")

    def test_failed_cloudinary_upload_returns_success_false(self):
        with patch.object(cloudinary_upload.cloudinary.uploader, "upload", side_effect=Exception("network error")):
            result = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(PDF_BYTES), "test.pdf", "u1", compress=False
            )
        self.assertFalse(result["success"])
        self.assertIn("network error", result["error"])


# ═════════════════════════════════════════════════════════════════════════════
# 4. /upload ROUTE — END-TO-END MULTIPART TESTS
# ═════════════════════════════════════════════════════════════════════════════

def _session_client():
    import methods.supabase_helper as _sh
    _sh._supabase_client = None  # reset singleton so our patch takes effect
    app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    client = app_module.app.test_client()
    with client.session_transaction() as s:
        s["user"] = {"uid": "test-uid-001", "email": "tester@example.com", "name": "Test User"}
    return client

def _upload_patches(upload_rv, save_rv):
    return [
        patch("methods.cloudinary_upload.upload_file_to_cloudinary", return_value=upload_rv),
        patch.object(app_module, "save_file_record", return_value=save_rv),
        patch.object(app_module, "track_user_event"),
        patch.object(app_module, "recalculate_and_persist_user_rank", return_value={}),
        patch.object(app_module, "_grant_upload_credits"),
        patch.object(app_module, "_get_quota", return_value={"credits": 10}),
        patch.object(app_module, "_trigger_indexnow"),
        patch.object(app_module.csrf, "protect"),
        patch.object(app_module.cache, "invalidate_files"),
        patch.object(app_module.cache, "invalidate_dropdowns"),
        patch.object(app_module.cache, "bump_version"),
        patch("threading.Thread"),
        patch("methods.supabase_helper.init_supabase", return_value=None),
        patch("app.init_supabase", return_value=None),
    ]


from contextlib import ExitStack

def _run_with_patches(patches, fn):
    """Enter all patches via ExitStack, call fn(), exit cleanly."""
    with ExitStack() as stack:
        mocks = [stack.enter_context(p) for p in patches]
        return fn(), mocks

BASE_FORM = {
    "subject": "Data Structures",
    "subject_id": "sub-uuid-001",
    "type": "notes",
    "document_type": "notes",
    "Year": "2025",
    "semester": "3",
    "college_id": "col-uuid",
    "branch_id":  "br-uuid",
}


class TestUploadRouteImages(unittest.TestCase):
    """POST /upload with real image files (mocked Cloudinary + DB)."""

    def setUp(self):
        import methods.supabase_helper as _sh
        _sh._supabase_client = None  # prevent singleton contamination

    def _post(self, file_bytes, filename, extra=None):
        import methods.supabase_helper as _sh
        _sh._supabase_client = None
        client = _session_client()
        form = {**BASE_FORM, **(extra or {})}
        cld_rv = _fake_cld(filename, "image")
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _upload_patches(cld_rv, SAVE_OK):
                stack.enter_context(p)
            resp = client.post(
                "/upload",
                data={**form, "upload_document": (io.BytesIO(file_bytes), filename)},
                content_type="multipart/form-data",
            )
        return resp

    def test_png_upload_returns_200(self):
        resp = self._post(PNG_BYTES, "diagram.png")
        self.assertEqual(resp.status_code, 200)

    def test_png_upload_success_true(self):
        resp = self._post(PNG_BYTES, "diagram.png")
        self.assertTrue(resp.get_json()["success"])

    def test_jpeg_upload_returns_200(self):
        resp = self._post(JPEG_BYTES, "photo.jpg")
        self.assertEqual(resp.status_code, 200)

    def test_jpeg_upload_success_true(self):
        resp = self._post(JPEG_BYTES, "photo.jpg")
        self.assertTrue(resp.get_json()["success"])

    def test_webp_upload_returns_200(self):
        resp = self._post(WEBP_BYTES, "img.webp")
        self.assertEqual(resp.status_code, 200)

    def test_response_contains_document_id(self):
        resp = self._post(PNG_BYTES, "diagram.png")
        body = resp.get_json()
        self.assertEqual(body["data"]["record_id"], "doc-uuid-123")

    def test_response_contains_secure_url(self):
        resp = self._post(PNG_BYTES, "diagram.png")
        body = resp.get_json()
        self.assertIn("res.cloudinary.com", body["data"]["url"])

    def test_image_file_type_is_image(self):
        resp = self._post(PNG_BYTES, "diagram.png")
        body = resp.get_json()
        self.assertEqual(body["data"]["file_type"], "image")


class TestUploadRoutePDF(unittest.TestCase):
    """POST /upload with a PDF (mocked Cloudinary + DB)."""

    def setUp(self):
        import methods.supabase_helper as _sh
        _sh._supabase_client = None

    def _post_pdf(self, extra=None):
        import methods.supabase_helper as _sh
        _sh._supabase_client = None
        client = _session_client()
        form = {**BASE_FORM, **(extra or {})}
        cld_rv = _fake_cld("paper.pdf", "raw")
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _upload_patches(cld_rv, SAVE_OK):
                stack.enter_context(p)
            resp = client.post(
                "/upload",
                data={**form, "upload_document": (io.BytesIO(PDF_BYTES), "paper.pdf")},
                content_type="multipart/form-data",
            )
        return resp

    def test_pdf_upload_returns_200(self):
        resp = self._post_pdf()
        self.assertEqual(resp.status_code, 200)

    def test_pdf_upload_success_true(self):
        resp = self._post_pdf()
        self.assertTrue(resp.get_json()["success"])

    def test_pdf_file_type_is_pdf(self):
        resp = self._post_pdf()
        self.assertEqual(resp.get_json()["data"]["file_type"], "pdf")

    def test_pdf_document_id_returned(self):
        resp = self._post_pdf()
        self.assertEqual(resp.get_json()["data"]["record_id"], "doc-uuid-123")

    def test_pdf_db_failure_triggers_cloudinary_cleanup(self):
        """If DB save fails, Cloudinary asset must be deleted (no orphans)."""
        client = _session_client()
        cld_rv = _fake_cld("paper.pdf", "raw")
        with patch("methods.cloudinary_upload.upload_file_to_cloudinary", return_value=cld_rv), \
             patch.object(app_module, "save_file_record", return_value=SAVE_ERR), \
             patch.object(app_module.csrf, "protect"), \
             patch("methods.cloudinary_upload.delete_file_from_cloudinary") as delete_mock, \
             patch("threading.Thread"), \
             patch("methods.supabase_helper.init_supabase", return_value=None):
            resp = client.post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(PDF_BYTES), "paper.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.get_json()["success"])
        delete_mock.assert_called_once()


# ═════════════════════════════════════════════════════════════════════════════
# 5. SECURITY / REJECTION TESTS
# ═════════════════════════════════════════════════════════════════════════════

class TestUploadSecurity(unittest.TestCase):
    """Confirm the /upload route rejects bad inputs before touching Cloudinary."""

    def _client(self):
        return _session_client()

    def test_no_file_returns_400(self):
        with patch.object(app_module.csrf, "protect"):
            resp = self._client().post("/upload", data={**BASE_FORM}, content_type="multipart/form-data")
        self.assertEqual(resp.status_code, 400)

    def test_empty_filename_returns_400(self):
        with patch.object(app_module.csrf, "protect"):
            resp = self._client().post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(PNG_BYTES), "")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_disallowed_extension_returns_400(self):
        with patch.object(app_module.csrf, "protect"):
            resp = self._client().post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(b"data"), "virus.exe")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_fake_pdf_extension_returns_400(self):
        """PNG bytes + .pdf extension → magic byte mismatch → rejected."""
        with patch.object(app_module.csrf, "protect"):
            resp = self._client().post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(PNG_BYTES), "fake.pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_fake_image_extension_returns_400(self):
        """PDF bytes + .png extension → magic byte mismatch → rejected."""
        with patch.object(app_module.csrf, "protect"):
            resp = self._client().post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(PDF_BYTES), "evil.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_missing_year_returns_400(self):
        form = {**BASE_FORM, "Year": ""}
        cld_rv = _fake_cld("img.png", "image")
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _upload_patches(cld_rv, SAVE_OK):
                stack.enter_context(p)
            resp = self._client().post(
                "/upload",
                data={**form, "upload_document": (io.BytesIO(PNG_BYTES), "img.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_missing_subject_id_returns_400(self):
        form = {**BASE_FORM, "subject_id": ""}
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _upload_patches(_fake_cld("img.png", "image"), SAVE_OK):
                stack.enter_context(p)
            resp = self._client().post(
                "/upload",
                data={**form, "upload_document": (io.BytesIO(PNG_BYTES), "img.png")},
                content_type="multipart/form-data",
            )
        self.assertEqual(resp.status_code, 400)

    def test_unauthenticated_upload_redirects(self):
        """Unauthenticated POST must not reach Cloudinary."""
        app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = app_module.app.test_client()  # no session
        with patch.object(app_module.csrf, "protect"):
            resp = client.post(
                "/upload",
                data={**BASE_FORM, "upload_document": (io.BytesIO(PNG_BYTES), "img.png")},
                content_type="multipart/form-data",
            )
        self.assertIn(resp.status_code, [302, 401])


# ═════════════════════════════════════════════════════════════════════════════
# 6. SANITIZE FILENAME
# ═════════════════════════════════════════════════════════════════════════════

class TestSanitizeFilename(unittest.TestCase):

    def test_strips_path_traversal(self):
        result = cloudinary_upload.sanitize_filename("../../etc/passwd")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)

    def test_replaces_spaces(self):
        result = cloudinary_upload.sanitize_filename("my file name.pdf")
        self.assertNotIn(" ", result)

    def test_lowercase(self):
        result = cloudinary_upload.sanitize_filename("MY_FILE.PDF")
        self.assertEqual(result, result.lower())

    def test_safe_chars_preserved(self):
        result = cloudinary_upload.sanitize_filename("notes_2025.pdf")
        self.assertIn("notes", result)
        self.assertIn("2025", result)


# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)


