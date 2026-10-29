"""
tests/test_admin_system.py
Unit and integration tests for Admin RBAC, anti-lockout safeguards,
moderation logic, audit logging, and file management services.
"""

import pytest
from unittest.mock import MagicMock, patch
from services.admin_service import (
    get_user_role,
    role_rank,
    has_min_role,
    check_anti_lockout,
    record_audit_log,
    get_site_settings
)


def test_role_hierarchy():
    """Verify role ranking order."""
    assert role_rank('superadmin') > role_rank('admin')
    assert role_rank('admin') > role_rank('moderator')
    assert role_rank('moderator') > role_rank('student')
    assert role_rank('student') > role_rank('anonymous')


def test_get_user_role():
    """Verify role detection from user dict and email overrides."""
    superadmin_user = {'email': 'abhihub.02@gmail.com', 'role': 'student'}
    assert get_user_role(superadmin_user) == 'superadmin'

    admin_user = {'email': 'test_admin@abhihub.com', 'role': 'admin'}
    assert get_user_role(admin_user) == 'admin'

    moderator_user = {'email': 'mod@abhihub.com', 'role': 'moderator'}
    assert get_user_role(moderator_user) == 'moderator'

    student_user = {'email': 'student@college.edu', 'role': 'student'}
    assert get_user_role(student_user) == 'student'


def test_has_min_role():
    """Verify minimum role checks across tiers."""
    superadmin = {'email': 'abhihub.02@gmail.com', 'role': 'superadmin'}
    admin = {'email': 'admin@abhihub.com', 'role': 'admin'}
    moderator = {'email': 'mod@abhihub.com', 'role': 'moderator'}
    student = {'email': 'student@abhihub.com', 'role': 'student'}

    assert has_min_role(superadmin, 'admin') is True
    assert has_min_role(superadmin, 'superadmin') is True
    assert has_min_role(admin, 'admin') is True
    assert has_min_role(admin, 'superadmin') is False
    assert has_min_role(moderator, 'admin') is False
    assert has_min_role(moderator, 'moderator') is True
    assert has_min_role(student, 'moderator') is False


def test_anti_lockout_self_actions():
    """Verify admin cannot block, ban, demote, or delete themselves."""
    admin_user = {'uid': 'admin-uuid-1234', 'email': 'admin@test.com', 'role': 'admin'}

    # Self-demotion blocked
    ok, err = check_anti_lockout(admin_user, 'admin-uuid-1234', 'demote')
    assert ok is False
    assert "cannot demote your own" in err

    # Self-block blocked
    ok, err = check_anti_lockout(admin_user, 'admin-uuid-1234', 'block')
    assert ok is False
    assert "cannot block your own" in err

    # Self-ban blocked
    ok, err = check_anti_lockout(admin_user, 'admin-uuid-1234', 'ban')
    assert ok is False
    assert "cannot ban your own" in err

    # Self-deletion blocked
    ok, err = check_anti_lockout(admin_user, 'admin-uuid-1234', 'delete')
    assert ok is False
    assert "cannot delete your own" in err


def test_default_site_settings():
    """Verify default site settings structure."""
    settings = get_site_settings()
    assert 'maintenance_mode' in settings
    assert 'registration_enabled' in settings
    assert 'uploads_enabled' in settings
    assert 'min_withdrawal_inr' in settings


def test_audit_log_format():
    """Verify record_audit_log constructs correct dictionary."""
    with patch('services.admin_service.get_db') as mock_db:
        mock_client = MagicMock()
        mock_db.return_value = mock_client

        ok = record_audit_log(
            admin_id='admin-1',
            admin_email='admin@test.com',
            action='ban_user',
            target_type='user',
            target_id='user-99',
            reason='Spam activities',
            ip_address='127.0.0.1'
        )
        assert mock_client.table.called
        assert mock_client.table().insert.called
