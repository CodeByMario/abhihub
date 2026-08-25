"""Offline contract tests for Firebase and Cloudinary upload paths.

Every provider SDK call is mocked: these tests never read real credentials,
upload user data, or change Firebase, Cloudinary, or Supabase.
"""

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import app as application_module
from PIL import Image
from methods import cloudinary_upload, storage as firebase_storage


def _png_bytes():
    """Return a Pillow-generated valid PNG for multipart form validation."""
    output = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(output, format="PNG")
    return output.getvalue()


PNG_BYTES = _png_bytes()
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


class FirebaseUploadTests(unittest.TestCase):
    def test_storage_helper_uploads_pdf_and_image_without_network(self):
        """Firebase helper sends both supported file types to the requested blob."""
        bucket = MagicMock()
        blob = MagicMock()
        blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"
        bucket.blob.return_value = blob

        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                os.chdir(tmp_dir)
                for filename, content, destination in (
                    ("paper.pdf", PDF_BYTES, "Documents/tests/paper.pdf"),
                    ("diagram.png", PNG_BYTES, "Documents/tests/diagram.png"),
                ):
                    with open(filename, "wb") as file_handle:
                        file_handle.write(content)
                    with patch.object(firebase_storage, "_get_bucket", return_value=bucket):
                        firebase_storage.upload_file(filename, destination)
            finally:
                os.chdir(original_cwd)

        self.assertEqual(bucket.blob.call_count, 2)
        self.assertEqual(blob.upload_from_filename.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in blob.upload_from_filename.call_args_list],
            ["paper.pdf", "diagram.png"],
        )

    def test_signature_form_accepts_valid_image_and_uses_firebase(self):
        """The Firebase-backed multipart form accepts and stores a valid PNG."""
        blob = MagicMock()
        blob.public_url = "https://storage.googleapis.com/example/signature.png"
        bucket = MagicMock()
        bucket.blob.return_value = blob

        application_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with patch("firebase_admin.storage.bucket", return_value=bucket), \
             patch.object(application_module.csrf, "protect"):
            response = application_module.app.test_client().post(
                "/api/memorywall/upload-signature",
                data={"signature": (io.BytesIO(PNG_BYTES), "signature.png", "image/png")},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])
        blob.upload_from_file.assert_called_once()
        blob.make_public.assert_called_once()

    def test_signature_form_rejects_pdf(self):
        """The image-only Firebase form must not accept PDFs."""
        application_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        with patch.object(application_module.csrf, "protect"):
            response = application_module.app.test_client().post(
                "/api/memorywall/upload-signature",
                data={"signature": (io.BytesIO(PDF_BYTES), "paper.pdf", "application/pdf")},
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)


class CloudinaryUploadTests(unittest.TestCase):
    def test_helper_uploads_pdf_as_raw_and_image_as_image(self):
        """Cloudinary helper selects the correct provider resource type."""
        fake_response = {
            "url": "http://example.invalid/file",
            "secure_url": "https://res.cloudinary.com/example/file",
            "public_id": "uploads/test-file",
            "resource_type": "raw",
            "format": "pdf",
            "bytes": 100,
        }
        with patch.object(cloudinary_upload.cloudinary.uploader, "upload", return_value=fake_response) as upload_mock:
            pdf_result = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(PDF_BYTES), "paper.pdf", "test-user", compress=False
            )
            image_result = cloudinary_upload.upload_file_to_cloudinary(
                io.BytesIO(PNG_BYTES), "diagram.png", "test-user", compress=False
            )

        self.assertTrue(pdf_result["success"])
        self.assertTrue(image_result["success"])
        self.assertEqual(upload_mock.call_args_list[0].kwargs["resource_type"], "raw")
        self.assertEqual(upload_mock.call_args_list[1].kwargs["resource_type"], "image")

    def test_upload_form_accepts_pdf_and_image_and_records_cloudinary_url(self):
        """Authenticated multipart document form stores Cloudinary upload metadata."""
        application_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = application_module.app.test_client()
        with client.session_transaction() as session:
            session["user"] = {"uid": "test-user", "email": "test@example.com", "name": "Test User"}

        for filename, content, expected_type in (
            ("paper.pdf", PDF_BYTES, "pdf"),
            ("diagram.png", PNG_BYTES, "image"),
        ):
            with self.subTest(filename=filename):
                upload_result = {
                    "success": True,
                    "secure_url": "https://res.cloudinary.com/example/uploaded-file",
                    "public_id": f"uploads/{filename}",
                    "bytes": len(content),
                    "resource_type": "raw" if expected_type == "pdf" else "image",
                }
                save_result = {"success": True, "data": {"id": "test-document-id"}}
                with patch("methods.cloudinary_upload.upload_file_to_cloudinary", return_value=upload_result), \
                     patch("methods.supabase_helper.save_file_record", return_value=save_result) as save_mock, \
                     patch("methods.supabase_helper.track_user_event"), \
                     patch("methods.supabase_helper.recalculate_and_persist_user_rank", return_value={"score": 0}), \
                     patch.object(application_module, "_grant_upload_credits"), \
                     patch.object(application_module, "_get_quota", return_value={"credits": 0}), \
                     patch.object(application_module, "_trigger_indexnow"), \
                     patch.object(application_module.csrf, "protect"), \
                     patch.object(application_module.cache, "invalidate_files"), \
                     patch.object(application_module.cache, "invalidate_dropdowns"), \
                     patch.object(application_module.cache, "bump_version"):
                    response = client.post(
                        "/upload",
                        data={
                            "upload_document": (io.BytesIO(content), filename),
                            "subject": "Algorithms",
                            "subject_id": "subject-id",
                            "type": "notes",
                            "document_type": "notes",
                            "Year": "2026",
                        },
                        content_type="multipart/form-data",
                    )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.get_json()["success"])
                self.assertEqual(save_mock.call_args.kwargs["file_url"], upload_result["secure_url"])
                self.assertEqual(save_mock.call_args.kwargs["file_type"], expected_type)


class StorageAccessAndDownloadTests(unittest.TestCase):
    """Verify each provider can be accessed and streamed back to the viewer."""

    def test_each_provider_streams_one_pdf_and_one_image(self):
        """Exercise Firebase and Cloudinary reads/downloads one file at a time."""
        application_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        client = application_module.app.test_client()
        download_dir = Path(__file__).resolve().parent.parent / "temp" / "test"
        download_dir.mkdir(parents=True, exist_ok=True)

        cases = (
            ("firebase", "pdf", "Documents/tests/paper.pdf", PDF_BYTES, "application/pdf"),
            ("firebase", "image", "Documents/tests/diagram.png", PNG_BYTES, "image/png"),
            ("cloudinary", "pdf", "https://res.cloudinary.com/example/raw/upload/paper.pdf", PDF_BYTES, "application/pdf"),
            ("cloudinary", "image", "https://res.cloudinary.com/example/image/upload/diagram.png", PNG_BYTES, "image/png"),
        )

        for provider, file_type, reference, content, content_type in cases:
            with self.subTest(provider=provider, file_type=file_type):
                document = {
                    "storage_provider": provider,
                    "file_url": reference,
                    "file_type": file_type,
                }
                upstream = MagicMock()
                upstream.status_code = 200
                upstream.ok = True
                upstream.headers = {
                    "Content-Type": content_type,
                    "Content-Length": str(len(content)),
                }
                upstream.iter_content.return_value = [content]

                if provider == "firebase":
                    bucket = MagicMock()
                    bucket.blob.return_value.generate_signed_url.return_value = (
                        "https://storage.googleapis.com/example/signed-file"
                    )
                with patch(
                    "methods.supabase_helper.get_document_by_id_rich",
                    return_value={"success": True, "data": document},
                ), patch.object(application_module.requests, "get", return_value=upstream) as request_mock:
                    if provider == "firebase":
                        with patch.object(application_module, "firebase_storage_available", True), \
                             patch.object(application_module.storage, "bucket", return_value=bucket), \
                             patch.object(application_module.cache.l1, "get", return_value=(None, 0)), \
                             patch.object(application_module.cache.l1, "set"):
                            response = client.get("/api/view-doc/test-document-id/document")
                    else:
                        response = client.get("/api/view-doc/test-document-id/document")

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data, content)
                self.assertEqual(response.headers["Content-Type"], content_type)
                self.assertEqual(response.headers["Content-Disposition"], "inline")
                request_mock.assert_called_once()

                suffix = "pdf" if file_type == "pdf" else "png"
                download_path = download_dir / f"{provider}_{file_type}.{suffix}"
                download_path.write_bytes(response.data)
                self.assertEqual(download_path.read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
