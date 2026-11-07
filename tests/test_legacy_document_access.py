import os
import io

import pytest
import requests
from PIL import Image, ImageDraw, ImageStat

os.environ.setdefault('SECRET_KEY', 'test-legacy-document-access-key')
os.environ.setdefault('SUPABASE_URL', 'https://mock-supabase.supabase.co')
os.environ.setdefault('SUPABASE_KEY', 'mock-supabase-key')

from app import app
from methods.api_rate_limiter import clear_api_rate_limits
from routes import api as api_routes


@pytest.fixture(autouse=True)
def test_app_state(monkeypatch):
    clear_api_rate_limits()
    app.config['TESTING'] = True
    monkeypatch.setitem(app.config, 'WTF_CSRF_ENABLED', False)
    yield
    clear_api_rate_limits()


def _set_user(client, user):
    with client.session_transaction() as session:
        session['user'] = user


def test_get_file_url_requires_document_id_and_access(monkeypatch):
    client = app.test_client()
    _set_user(client, {'uid': 'reader-1', 'email': 'reader@example.test'})

    response = client.post('/get-file-url', json={'file_path': 'private/other-user.pdf'})
    assert response.status_code == 400

    seen = []

    def denied(doc_id):
        seen.append(doc_id)
        return {'success': False, 'message': 'Payment required'}, 402

    monkeypatch.setattr(api_routes, 'authorize_document_access', denied)
    response = client.post('/get-file-url', json={'doc_id': 'paid-document-123'})
    assert response.status_code == 402
    assert response.get_json()['message'] == 'Payment required'
    assert seen == ['paid-document-123']


def test_get_file_url_returns_authorized_viewer_url(monkeypatch):
    client = app.test_client()
    _set_user(client, {'uid': 'owner-1', 'email': 'owner@example.test'})
    viewer_url = '/api/view-doc/owned-document-123/file?stream=1'
    monkeypatch.setattr(
        api_routes,
        'authorize_document_access',
        lambda doc_id: ({'success': True, 'file_url': viewer_url, 'document_id': doc_id}, 200),
    )

    response = client.post('/get-file-url', json={'doc_id': 'owned-document-123'})
    assert response.status_code == 200
    assert response.get_json()['url'] == viewer_url
    assert 'storage.example.test' not in response.get_json()['url']
    assert response.get_json()['document_id'] == 'owned-document-123'


def test_verify_file_requires_admin(monkeypatch):
    from firebase_admin import storage

    storage_calls = []

    class Blob:
        def exists(self):
            return True

    class Bucket:
        def blob(self, path):
            storage_calls.append(path)
            return Blob()

    monkeypatch.setattr(storage, 'bucket', lambda: Bucket())
    monkeypatch.setattr(api_routes, 'init_supabase', lambda: None)

    anonymous = app.test_client()
    response = anonymous.post('/verify-file', json={'file_path': 'uploads/doc.pdf'})
    assert response.status_code == 401
    assert storage_calls == []

    student = app.test_client()
    _set_user(student, {'uid': 'student-1', 'email': 'student@example.test', 'role': 'student'})
    response = student.post('/verify-file', json={'file_path': 'uploads/doc.pdf'})
    assert response.status_code == 403
    assert storage_calls == []

    admin = app.test_client()
    _set_user(admin, {'uid': 'admin-1', 'email': 'admin@example.test', 'role': 'admin'})
    response = admin.post('/verify-file', json={'file_path': 'uploads/doc.pdf'})
    assert response.status_code == 200
    assert storage_calls == ['uploads/doc.pdf']


def test_pdf_proxy_rejects_unregistered_storage_path(monkeypatch):
    client = app.test_client()
    _set_user(client, {'uid': 'reader-1', 'email': 'reader@example.test'})

    class Query:
        def select(self, _columns):
            return self

        def eq(self, _column, _value):
            return self

        def limit(self, _count):
            return self

        def execute(self):
            return type('Result', (), {'data': []})()

    class Supabase:
        def table(self, _name):
            return Query()

    monkeypatch.setattr(api_routes, 'init_supabase', lambda: Supabase())
    response = client.get('/pdf-proxy/private/another-users.pdf')
    assert response.status_code == 404


def test_pdf_proxy_redirects_registered_file_to_resource_page(monkeypatch):
    client = app.test_client()
    _set_user(client, {'uid': 'reader-1', 'email': 'reader@example.test'})
    queried = []

    class Query:
        def select(self, _columns):
            return self

        def eq(self, column, value):
            queried.append((column, value))
            return self

        def limit(self, _count):
            return self

        def execute(self):
            return type('Result', (), {'data': [{'id': 'doc-123'}]})()

    class Supabase:
        def table(self, name):
            assert name == 'documents'
            return Query()

    monkeypatch.setattr(api_routes, 'init_supabase', lambda: Supabase())
    response = client.get('/pdf-proxy/resources/notes/registered.pdf')
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/resources/doc-123')
    assert queried == [('file_url', 'resources/notes/registered.pdf')]


def test_paid_preview_authorization_never_returns_full_storage_url(monkeypatch):
    from methods import supabase_helper

    document = {
        'id': 'paid-doc-123',
        'file_url': 'https://storage.example.test/private/full-document.pdf',
        'file_type': 'pdf',
        'title': 'Paid Document',
        'status': 'approved',
        'is_paid': True,
        'price': 20,
    }
    monkeypatch.setattr(
        supabase_helper,
        'get_document_by_id_rich',
        lambda _doc_id: {'success': True, 'data': document},
    )
    monkeypatch.setattr(api_routes, 'has_document_access', lambda *_args: False)

    class CacheLayer:
        def get(self, _key):
            return None, None

        def set(self, *_args, **_kwargs):
            raise AssertionError('preview authorization response should not be cached')

    class Cache:
        l1 = CacheLayer()

    monkeypatch.setattr('cache_manager.get_cache', lambda: Cache())
    response = app.test_client().get('/api/view-doc/paid-doc-123/authorize?preview=1')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['is_preview'] is True
    assert payload['file_url'] == '/api/view-doc/paid-doc-123/file?preview=1'
    assert 'storage.example.test' not in payload['file_url']


def test_unentitled_paid_image_returns_server_blurred_top_fifth_preview(monkeypatch):
    from methods import supabase_helper

    source = Image.new('RGB', (240, 200), (230, 20, 20))
    draw = ImageDraw.Draw(source)
    for y in range(40, 200, 8):
        for x in range(0, 240, 8):
            color = (255, 255, 255) if (x // 8 + y // 8) % 2 else (0, 0, 0)
            draw.rectangle((x, y, x + 7, y + 7), fill=color)
    source_bytes = io.BytesIO()
    source.save(source_bytes, format='JPEG', quality=95)
    original = source_bytes.getvalue()

    document = {
        'id': 'paid-image-123',
        'file_url': 'https://mock-supabase.supabase.co/storage/v1/object/public/docs/paid.jpg',
        'file_type': 'image',
        'title': 'Paid image',
        'status': 'approved',
        'is_paid': True,
        'price': 20,
    }
    monkeypatch.setattr(
        supabase_helper,
        'get_document_by_id_rich',
        lambda _doc_id: {'success': True, 'data': document},
    )
    monkeypatch.setattr(api_routes, 'has_document_access', lambda *_args: False)

    class CacheLayer:
        def get(self, _key):
            return None, False

        def set(self, *_args, **_kwargs):
            return None

        def delete(self, *_args, **_kwargs):
            return None

    class Cache:
        l1 = CacheLayer()

    class Upstream:
        status_code = 200
        ok = True
        headers = {'Content-Type': 'image/jpeg', 'Content-Length': str(len(original))}

        def iter_content(self, chunk_size):
            assert chunk_size == 65536
            yield original

        def close(self):
            return None

    monkeypatch.setattr('cache_manager.get_cache', lambda: Cache())
    monkeypatch.setattr(requests, 'get', lambda *_args, **_kwargs: Upstream())

    client = app.test_client()
    unauthorized = client.get('/api/view-doc/paid-image-123/file')
    assert unauthorized.status_code == 402

    response = client.get('/api/view-doc/paid-image-123/file?preview=1')
    assert response.status_code == 200
    assert response.mimetype == 'image/jpeg'
    assert response.headers['X-AbhiHub-Preview'] == 'top-20-clear-rest-blurred'
    assert response.headers['Content-Disposition'].startswith('inline;')

    preview = Image.open(io.BytesIO(response.data)).convert('RGB')
    assert preview.size == (240, 200)
    assert preview.getpixel((5, 5))[0] > 180
    original_lower = ImageStat.Stat(source.crop((0, 40, 240, 200))).stddev
    preview_lower = ImageStat.Stat(preview.crop((0, 40, 240, 200))).stddev
    assert sum(preview_lower) < sum(original_lower)


def test_entitled_pdf_authorization_returns_short_lived_provider_url(monkeypatch):
    from datetime import timedelta
    from firebase_admin import storage
    from methods import supabase_helper

    document = {
        'id': 'approved-doc-123',
        'uploader_id': 'owner-1',
        'status': 'approved',
        'file_url': 'resources/notes/document.pdf',
        'storage_provider': 'firebase',
        'file_type': 'pdf',
        'title': 'Document',
    }
    monkeypatch.setattr(
        supabase_helper,
        'get_document_by_id_rich',
        lambda _doc_id: {'success': True, 'data': document},
    )
    monkeypatch.setattr(api_routes, 'has_document_access', lambda *_args: True)
    signing = {}

    class Blob:
        def generate_signed_url(self, **kwargs):
            signing.update(kwargs)
            return 'https://storage.googleapis.com/test-bucket/document.pdf?signature=short-lived'

    class Bucket:
        def blob(self, path):
            assert path == 'resources/notes/document.pdf'
            return Blob()

    monkeypatch.setattr(storage, 'bucket', lambda **_kwargs: Bucket())
    response = app.test_client().get('/api/view-doc/approved-doc-123/authorize')
    assert response.status_code == 200
    assert response.get_json()['file_url'].startswith('https://storage.googleapis.com/')
    assert signing['expiration'] == timedelta(minutes=10)
    assert signing['method'] == 'GET'


def test_unapproved_documents_are_hidden_from_non_owner(monkeypatch):
    from methods import supabase_helper

    pending_document = {
        'id': 'pending-doc-123',
        'uploader_id': 'uploader-1',
        'status': 'pending',
        'file_url': 'https://storage.example.test/pending.pdf',
        'file_type': 'pdf',
        'title': 'Unpublished Document',
    }
    monkeypatch.setattr(
        supabase_helper,
        'get_document_by_id_rich',
        lambda _doc_id: {'success': True, 'data': pending_document},
    )
    monkeypatch.setattr(api_routes, 'has_document_access', lambda *_args: True)
    client = app.test_client()

    auth_response = client.get('/api/view-doc/pending-doc-123/authorize')
    file_response = client.get('/api/view-doc/pending-doc-123/file')
    assert auth_response.status_code == 404
    assert file_response.status_code == 404
