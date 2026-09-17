"""
Unit and integration tests for AbhiHub Notification Reliability Subsystem.
Tests in-app notifications, push subscriptions, VAPID delivery pipeline,
admin authorization, deduplication, URL sanitization, and preferences.
"""

import pytest
from unittest.mock import patch, MagicMock
from flask import Flask, session
from push_api import push_api, init_push_api
from push_notifications import (
    sanitize_url,
    send_notification,
    check_user_push_preference,
    add_subscription,
    remove_subscription_by_endpoint
)
from data.notifications import Notification, PushSubscription


@pytest.fixture
def app():
    app = Flask(__name__)
    app.secret_key = "test-secret-key"
    init_push_api(app)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


# ==================== 1. URL SANITIZATION TESTS ====================

def test_sanitize_url_allowlisted():
    assert sanitize_url("/dashboard") == "/dashboard"
    assert sanitize_url("/resource/123e4567-e89b-12d3-a456-426614174000") == "/resource/123e4567-e89b-12d3-a456-426614174000"
    assert sanitize_url("/chat?user=test") == "/chat?user=test"
    assert sanitize_url("/profile") == "/profile"
    assert sanitize_url("/settings#section-notifications") == "/settings#section-notifications"


def test_sanitize_url_blocks_malicious():
    assert sanitize_url("https://evil.com") == "/dashboard"
    assert sanitize_url("//evil.com") == "/dashboard"
    assert sanitize_url("javascript:alert(1)") == "/dashboard"
    assert sanitize_url("/\\evil.com") == "/dashboard"
    assert sanitize_url(None) == "/dashboard"
    assert sanitize_url("") == "/dashboard"


# ==================== 2. PUSH API ROUTE TESTS ====================

def test_vapid_public_key_route(client):
    with patch("push_api.get_vapid_key", return_value="test-public-key"):
        res = client.get("/api/push/vapid-public-key")
        assert res.status_code == 200
        data = res.get_json()
        assert data["publicKey"] == "test-public-key"


def test_push_subscribe_unauthenticated_rejected(client):
    res = client.post("/api/push/subscribe", json={
        "subscription": {
            "endpoint": "https://push.example.com/sub/123",
            "keys": {"p256dh": "key", "auth": "secret"}
        }
    })
    assert res.status_code == 401
    assert "Authentication required" in res.get_json().get("error", "")


def test_push_subscribe_authenticated_success(client):
    with client.session_transaction() as sess:
        sess["user"] = {
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "student@example.com"
        }

    with patch("push_notifications.save_push_subscription", return_value={"success": True}):
        res = client.post("/api/push/subscribe", json={
            "subscription": {
                "endpoint": "https://push.example.com/sub/123",
                "keys": {"p256dh": "key", "auth": "secret"}
            },
            "platform": "windows",
            "browser": "chrome"
        })
        assert res.status_code == 200
        assert res.get_json().get("success") is True


def test_push_send_unauthorized_for_non_admin(client):
    # Anonymous request
    res = client.post("/api/push/send", json={"title": "Test", "body": "Spam"})
    assert res.status_code == 403

    # Authenticated standard user
    with client.session_transaction() as sess:
        sess["user"] = {
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "regular_student@example.com"
        }
    with patch("push_api.ADMIN_EMAILS", ["admin@abhihub.com"]):
        res = client.post("/api/push/send", json={"title": "Test", "body": "Spam"})
        assert res.status_code == 403


def test_push_send_authorized_for_admin(client):
    with client.session_transaction() as sess:
        sess["user"] = {
            "uid": "admin-uuid",
            "email": "admin@abhihub.com"
        }

    with patch("push_api.ADMIN_EMAILS", ["admin@abhihub.com"]), \
         patch("push_notifications.send_notification_to_all", return_value={"success": True, "sent": 5}):
        res = client.post("/api/push/send", json={"title": "Announcement", "body": "Welcome back!"})
        assert res.status_code == 200
        assert res.get_json().get("sent") == 5


# ==================== 3. USER PREFERENCES API ====================

def test_notification_preferences_get_and_post(client):
    with client.session_transaction() as sess:
        sess["user"] = {
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "user@example.com"
        }

    mock_client = MagicMock()
    mock_select = MagicMock()
    mock_select.execute.return_value.data = [{
        "notif_push_enabled": True,
        "notif_email_enabled": False,
        "notif_uploads_enabled": True,
        "notif_chat_enabled": True,
        "notif_crush_enabled": True
    }]
    mock_client.table.return_value.select.return_value.eq.return_value.limit.return_value = mock_select
    mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock()

    with patch("push_api.init_supabase", return_value=mock_client):
        # GET
        res = client.get("/api/user/notification-preferences")
        assert res.status_code == 200
        assert res.get_json()["preferences"]["push"] is True

        # POST
        res = client.post("/api/user/notification-preferences", json={"uploads": False})
        assert res.status_code == 200
        assert res.get_json()["updated"]["notif_uploads_enabled"] is False


# ==================== 4. DELIVERY, RETRY & DEDUPLICATION ====================

def test_push_deduplication():
    user_id = "test-user-uuid"
    with patch("push_notifications.VAPID_PUBLIC_KEY", "pubkey"), \
         patch("push_notifications.VAPID_PRIVATE_KEY", "privkey"), \
         patch("push_notifications.load_subscriptions", return_value={user_id: [{"subscription": {"endpoint": "ep", "keys": {"p256dh": "k", "auth": "a"}}}]}), \
         patch("push_notifications.webpush") as mock_webpush:
        
        # First send -> executes webpush
        res1 = send_notification(user_id, "Hello", "World", dedupe_key="unique_1")
        assert res1["success"] is True
        assert mock_webpush.call_count == 1

        # Immediate duplicate -> suppressed
        res2 = send_notification(user_id, "Hello", "World", dedupe_key="unique_1")
        assert res2["success"] is True
        assert res2.get("suppressed") is True
        # webpush was not called again
        assert mock_webpush.call_count == 1


def test_stale_token_pruned_on_410():
    from push_notifications import WebPushException
    user_id = "test-user-uuid"

    mock_resp = MagicMock()
    mock_resp.status_code = 410
    exc = WebPushException("Gone", response=mock_resp)

    with patch("push_notifications.VAPID_PUBLIC_KEY", "pubkey"), \
         patch("push_notifications.VAPID_PRIVATE_KEY", "privkey"), \
         patch("push_notifications.load_subscriptions", return_value={user_id: [{"subscription": {"endpoint": "https://push.com/dead", "keys": {"p256dh": "k", "auth": "a"}}}]}), \
         patch("push_notifications.webpush", side_effect=exc), \
         patch("push_notifications.remove_subscription_by_endpoint") as mock_remove:
        
        res = send_notification(user_id, "Title", "Body", dedupe_key="prune_test")
        assert res["expired"] == 1
        mock_remove.assert_called_once_with("https://push.com/dead")


# ==================== 5. OPEN TRACKING & SELF-TEST API ====================

def test_track_notification_opened_route(client):
    with patch("push_notifications.NotificationService.record_notification_opened", return_value=True):
        res = client.post("/api/notifications/123e4567-e89b-12d3-a456-426614174000/open")
        assert res.status_code == 200
        assert res.get_json().get("success") is True


def test_push_test_route_authenticated(client):
    with client.session_transaction() as sess:
        sess["user"] = {
            "uid": "123e4567-e89b-12d3-a456-426614174000",
            "email": "student@example.com"
        }
    with patch("push_notifications.NotificationService.send_notification", return_value={"success": True, "sent": 1}):
        res = client.post("/api/push/test")
        assert res.status_code == 200
        assert res.get_json().get("success") is True


def test_notification_service_custom_adapter():
    from push_notifications import NotificationService, NotificationAdapter
    
    class MockAdapter(NotificationAdapter):
        def __init__(self):
            self.calls = []
        def send(self, subscription_info, payload):
            self.calls.append((subscription_info, payload))
            return {"success": True, "status_code": 201, "expired": False, "retryable": False}

    mock_adapter = MockAdapter()
    service = NotificationService(adapter=mock_adapter)
    
    with patch("push_notifications.load_subscriptions", return_value={"uid-1": [{"subscription": {"endpoint": "https://push.test", "keys": {"p256dh": "k", "auth": "a"}}}]}), \
         patch.object(service, "get_notification_preferences", return_value={"push": True}):
        res = service.send_notification("uid-1", "Test Title", "Test Body", dedupe_key="mock_test")
        assert res["success"] is True
        assert len(mock_adapter.calls) == 1
        assert mock_adapter.calls[0][1]["title"] == "Test Title"

