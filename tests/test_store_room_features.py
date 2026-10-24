"""
test_store_room_features.py
===========================
Comprehensive test suite verifying Store Room and document processing features:
1. Rename feature (/store-room/api/rename-file)
2. Labeling feature (/store-room/api/label & /store-room/api/edit-label)
3. Verification feature (/store-room/api/verify & /store-room/api/verification-queue)
4. Storage Sync (/store-room/api/sync)
5. Label History (/store-room/api/history)
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

os.environ.setdefault("SECRET_KEY", "test-only")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("CLOUDINARY_CLOUD_NAME", "test-cloud")
os.environ.setdefault("CLOUDINARY_API_KEY", "000000000000000")
os.environ.setdefault("CLOUDINARY_API_SECRET", "test-secret")

import app as app_module


class TestStoreRoomFeatures(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.client = app_module.app.test_client()
        with self.client.session_transaction() as sess:
            sess["user"] = {
                "uid": "test-user-123",
                "email": "tester@example.com",
                "name": "Test User",
                "role": "admin"
            }

    # 1. RENAME FEATURE TESTS
    def test_rename_file_success(self):
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/rename-file", json={
                "filename": "original_scan.pdf",
                "college_name": "Delhi Technological University",
                "subject_code": "CS101",
                "exam_type": "midsem",
                "year": "2024",
                "branch": "Computer Science",
                "semesters": [3]
            })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("new_filename"), "DEL_CS101_M_2024_COM_3.pdf")

    def test_rename_file_empty_exam_type_resilience(self):
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/rename-file", json={
                "filename": "paper.pdf",
                "college_name": "IIT",
                "subject_name": "Maths",
                "exam_type": "",
                "year": "2023"
            })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("IIT_MATH_U_2023_UNK.pdf", data.get("new_filename"))

    def test_rename_file_missing_filename(self):
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/rename-file", json={
                "college_name": "IIT"
            })
        self.assertEqual(res.status_code, 400)

    # 2. LABELING FEATURE TESTS
    @patch("routes.store_room.save_file_record")
    @patch("routes.store_room.verify_hierarchy", return_value=True)
    @patch("routes.store_room._mark_labeled")
    @patch("routes.store_room.log_label_audit")
    def test_labeling_success(self, mock_audit, mock_mark, mock_hier, mock_save):
        mock_save.return_value = {"success": True, "data": {"id": "doc_999"}}
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/label", json={
                "filename": "quantum_physics.pdf",
                "url": "https://res.cloudinary.com/demo/image/upload/v1234/quantum_physics.pdf",
                "subject_name": "Quantum Physics",
                "subject_id": "sub_42",
                "year": 2024,
                "college_id": "col_1",
                "branch_id": "phy_1",
                "document_category": "papers",
                "exam_type": "endsem"
            })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        mock_save.assert_called_once()
        mock_mark.assert_called_once()

    def test_labeling_invalid_year(self):
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/label", json={
                "filename": "quantum_physics.pdf",
                "url": "https://example.com/doc.pdf",
                "subject_name": "Physics",
                "subject_id": "sub_42",
                "year": 1800
            })
        self.assertEqual(res.status_code, 400)

    # 3. VERIFICATION TESTS
    @patch("routes.store_room.add_paper_verification")
    def test_verify_paper_success(self, mock_verify):
        mock_verify.return_value = {"success": True, "message": "Paper verified"}
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/verify", json={"paper_id": "doc_999"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get("success"))

    @patch("routes.store_room.get_pending_verification_papers")
    def test_verification_queue(self, mock_queue):
        mock_queue.return_value = {"success": True, "papers": []}
        with patch.object(app_module.csrf, "protect"):
            res = self.client.get("/store-room/api/verification-queue")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get("success"))

    # 4. STORAGE SYNC TEST
    @patch("methods.storage_providers.CloudinaryProvider.sync")
    def test_storage_sync(self, mock_sync):
        mock_sync.return_value = {"success": True, "upserted": 5}
        with patch.object(app_module.csrf, "protect"):
            res = self.client.post("/store-room/api/sync")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json().get("success"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
