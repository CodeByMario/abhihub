import logging
from unittest.mock import Mock

import requests
import pytest

from app import app
from methods import get_user_uploaded_files as uploaded_files_module
from methods.upload_notifier import send_upload_notification
from methods.ai_provider import OpenRouterAdapter, ProviderError
from routes.webhooks import _async_compress_and_update


def test_proxy_failure_does_not_log_signed_url(monkeypatch, caplog):
    signed_url = (
        "https://res.cloudinary.com/abhihub/private/document.pdf"
        "?signature=do-not-log-this"
    )

    def fail_request(url, **kwargs):
        raise RuntimeError(f"upstream request failed for {url}")

    monkeypatch.setattr(requests, "get", fail_request)
    app.config["TESTING"] = True
    client = app.test_client()
    with client.session_transaction() as session:
        session["user"] = {"uid": "audit-test-user"}

    with caplog.at_level(logging.ERROR):
        response = client.get("/api/proxy-file", query_string={"url": signed_url})

    assert response.status_code == 502
    assert "do-not-log-this" not in caplog.text
    assert "res.cloudinary.com" in caplog.text
    assert "RuntimeError" in caplog.text


def test_post_upload_worker_does_not_log_exception_url(monkeypatch, caplog):
    signed_url = (
        "https://res.cloudinary.com/abhihub/private/document.pdf"
        "?signature=do-not-log-this"
    )

    def fail_request(url, **kwargs):
        raise RuntimeError(f"upstream request failed for {url}")

    monkeypatch.setattr(requests, "get", fail_request)

    with caplog.at_level(logging.ERROR):
        _async_compress_and_update("public-id", signed_url, "image", "document.pdf")

    assert "do-not-log-this" not in caplog.text
    assert "RuntimeError" in caplog.text


@pytest.mark.parametrize("delivery_succeeds", [True, False])
def test_upload_notification_logs_omit_email_and_filename(
    monkeypatch, caplog, delivery_succeeds
):
    import push_notifications

    private_email = "private_student@example.test"
    private_filename = "private_transcript.pdf"
    monkeypatch.setattr(
        push_notifications,
        "send_notification",
        lambda *args, **kwargs: {
            "success": delivery_succeeds,
            "error": f"{private_email} {private_filename}",
        },
    )

    result = send_upload_notification(
        "private-user-id",
        private_email,
        private_filename,
        "private subject",
        "Notes",
    )

    assert result is delivery_succeeds
    assert private_email not in caplog.text
    assert private_filename not in caplog.text


def test_user_file_lookup_omits_email_and_exception_from_logs(monkeypatch, caplog):
    private_email = "private_student@example.test"
    client = Mock()
    client.table.return_value.select.return_value.eq.return_value.execute.side_effect = (
        RuntimeError(f"database rejected lookup for {private_email}")
    )
    monkeypatch.setattr(uploaded_files_module, "init_supabase", lambda: client)

    result = uploaded_files_module.get_user_uploaded_files(private_email)

    assert result == {
        "success": False,
        "message": "Error fetching user files",
        "data": [],
    }
    assert private_email not in caplog.text
    assert "database rejected lookup" not in caplog.text


def test_ai_provider_failure_does_not_log_response_body_or_prompt(monkeypatch, caplog):
    private_prompt = "private student document text"
    private_provider_detail = "provider echoed private request body"
    response = Mock(status_code=400, ok=False, text=private_provider_detail)
    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)
    provider = OpenRouterAdapter(api_key="test-provider-key", models=["test-model"])

    with caplog.at_level(logging.WARNING), pytest.raises(ProviderError):
        provider.complete([{"role": "user", "content": private_prompt}])

    assert private_prompt not in caplog.text
    assert private_provider_detail not in caplog.text
    assert "test-provider-key" not in caplog.text
