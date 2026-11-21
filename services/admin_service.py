"""
services/admin_service.py
Comprehensive business logic, RBAC enforcement, audit logging,
user moderation, storage cleanup, and system management for AbhiHub Admin.
"""

import os
import io
import csv
import re
import json
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from methods.supabase_helper import (
    init_supabase,
    init_supabase_admin,
    validate_uuid,
    recalculate_and_persist_user_rank,
    award_contribution_xp,
    log_notification,
)

log = logging.getLogger('abhihub.admin_service')

# Canonical admin emails list from environment
ADMIN_EMAILS = [
    e.strip().lower()
    for e in (os.getenv('ADMIN_EMAILS') or os.getenv('ADMIN_EMAIL') or '').split(',')
    if e.strip()
]
SUPERADMIN_EMAILS = [
    e.strip().lower()
    for e in (os.getenv('SUPERADMIN_EMAILS') or os.getenv('SUPERADMIN_EMAIL') or '').split(',')
    if e.strip()
] or ADMIN_EMAILS or ['abhihub.02@gmail.com']


def get_db(schema: Optional[str] = 'abhihub'):
    """Retrieve service-role Supabase client, scoped to schema if supported."""
    client = init_supabase_admin() or init_supabase()
    if client and schema:
        try:
            return client.schema(schema)
        except Exception:
            return client
    return client


# ─── RBAC & Anti-Lockout Helpers ─────────────────────────────────────────────

def get_user_role(user: dict) -> str:
    """Return canonical role string ('superadmin', 'admin', 'moderator', 'student', etc.)."""
    if not user or not isinstance(user, dict):
        return 'anonymous'
    email = (user.get('email') or '').lower().strip()
    if email in SUPERADMIN_EMAILS:
        return 'superadmin'
    role = (user.get('role') or '').lower().strip()
    if role in ('superadmin', 'admin', 'moderator'):
        return role
    if email in ADMIN_EMAILS or bool(user.get('is_admin')):
        return 'admin'
    return role or 'student'


def role_rank(role: str) -> int:
    ranks = {'superadmin': 40, 'admin': 30, 'moderator': 20, 'creator': 10, 'teacher': 10, 'student': 5, 'anonymous': 0}
    return ranks.get(role, 5)


def has_min_role(user: dict, min_role: str) -> bool:
    """Check if user role meets or exceeds required minimum role tier."""
    user_role = get_user_role(user)
    return role_rank(user_role) >= role_rank(min_role)


def check_anti_lockout(actor_user: dict, target_user_id: str, action: str) -> Tuple[bool, str]:
    """
    Prevent an admin from:
    1. Demoting, banning, blocking, or deleting themselves.
    2. Modifying or deleting the last superadmin.
    3. Escalating a user to a rank higher than or equal to their own (unless superadmin).
    """
    actor_id = actor_user.get('uid') or actor_user.get('id')
    actor_role = get_user_role(actor_user)

    if actor_id and str(actor_id) == str(target_user_id):
        if action in ('demote', 'block', 'ban', 'suspend', 'deactivate', 'delete', 'soft_delete'):
            return False, f"Anti-Lockout Protection: You cannot {action} your own administrator account."

    db = get_db()
    if db and target_user_id:
        try:
            target_res = db.table('profiles').select('id, email, role').eq('id', target_user_id).limit(1).execute()
            if target_res.data:
                target_user = target_res.data[0]
                target_role = get_user_role(target_user)
                target_rank = role_rank(target_role)
                actor_rank = role_rank(actor_role)

                # Only superadmins can affect other admins or superadmins
                if target_rank >= 30 and actor_role != 'superadmin' and action in ('demote', 'ban', 'block', 'delete', 'suspend'):
                    return False, "Permission Denied: Only a Superadmin can modify other administrators."

                # Verify not deleting or demoting the last superadmin
                if target_role == 'superadmin' and action in ('demote', 'delete', 'ban', 'suspend'):
                    all_admins = db.table('profiles').select('id, email, role').execute()
                    superadmins = [u for u in (all_admins.data or []) if get_user_role(u) == 'superadmin']
                    if len(superadmins) <= 1:
                        return False, "Critical Protection: Cannot remove or demote the last remaining Superadmin."
        except Exception as e:
            log.warning(f"[check_anti_lockout] validation warning: {e}")

    return True, ""


# ─── Persistent Audit Logging ────────────────────────────────────────────────

def record_audit_log(
    admin_id: str,
    admin_email: str,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    old_value: Any = None,
    new_value: Any = None,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """Write an append-only audit record to Supabase admin_audit_logs table."""
    now_iso = datetime.now(timezone.utc).isoformat()
    entry = {
        'timestamp': now_iso,
        'admin_id': str(admin_id) if admin_id else None,
        'admin_email': admin_email or 'system',
        'action': action,
        'target_type': target_type,
        'target_id': str(target_id) if target_id else None,
        'old_value': json.dumps(old_value) if isinstance(old_value, (dict, list)) else (str(old_value) if old_value is not None else None),
        'new_value': json.dumps(new_value) if isinstance(new_value, (dict, list)) else (str(new_value) if new_value is not None else None),
        'reason': reason,
        'ip_address': ip_address or '0.0.0.0',
        'user_agent': (user_agent or '')[:255]
    }
    log.info(f"[AUDIT] {action} by {admin_email} on {target_type}:{target_id}")

    db = get_db()
    if db:
        try:
            db.table('admin_audit_logs').insert(entry).execute()
            return True
        except Exception as e:
            log.warning(f"Could not write audit log to table: {e}")
    return False


def get_audit_logs(
    action: Optional[str] = None,
    admin_id: Optional[str] = None,
    target_type: Optional[str] = None,
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """Fetch paginated audit logs for admin review."""
    db = get_db()
    if not db:
        return {'success': False, 'logs': [], 'total': 0}
    try:
        offset = (max(1, page) - 1) * limit
        q = db.table('admin_audit_logs').select('*', count='exact')
        if action:
            q = q.eq('action', action)
        if admin_id:
            q = q.eq('admin_id', admin_id)
        if target_type:
            q = q.eq('target_type', target_type)
        res = q.order('timestamp', desc=True).range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'logs': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.warning(f"[get_audit_logs] {e}")
        return {'success': False, 'logs': [], 'total': 0, 'error': str(e)}


def export_audit_logs_csv() -> str:
    """Generate CSV string of the most recent 1,000 audit records."""
    logs_res = get_audit_logs(limit=1000)
    rows = logs_res.get('logs', [])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Timestamp', 'Admin Email', 'Admin ID', 'Action', 'Target Type', 'Target ID', 'Reason', 'IP Address'])
    for r in rows:
        writer.writerow([
            r.get('id', ''),
            r.get('timestamp', ''),
            r.get('admin_email', ''),
            r.get('admin_id', ''),
            r.get('action', ''),
            r.get('target_type', ''),
            r.get('target_id', ''),
            r.get('reason', ''),
            r.get('ip_address', '')
        ])
    return output.getvalue()


# ─── User Management & Moderation ───────────────────────────────────────────

def list_users(
    search: Optional[str] = None,
    role: Optional[str] = None,
    status: Optional[str] = None,
    degree: Optional[str] = None,
    sort_by: str = 'recent',
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """List users with filtering, sorting, and pagination."""
    db = get_db()
    if not db:
        return {'success': False, 'users': [], 'total': 0}
    try:
        offset = (max(1, page) - 1) * limit
        q = db.table('profiles').select(
            'id, full_name, email, created_at, role, is_verified, verified_at, verified_by, '
            'reputation_score, abhihub_score, rank_title, access_level, degree, last_active_at, '
            'students_helped, paper_quota_remaining, referral_credits, is_blocked, blocked_reason, '
            'is_banned, banned_reason, account_status',
            count='exact'
        )

        if search:
            clean_s = search.replace('%', '')
            q = q.or_(f"full_name.ilike.%{clean_s}%,email.ilike.%{clean_s}%")
        if role and role.lower() != 'all':
            q = q.eq('role', role.lower())
        if degree and degree.lower() != 'all':
            q = q.ilike('degree', f"%{degree}%")
        if status == 'blocked':
            q = q.eq('is_blocked', True)
        elif status == 'banned':
            q = q.eq('is_banned', True)
        elif status == 'unverified':
            q = q.eq('is_verified', False)

        if sort_by == 'score':
            q = q.order('abhihub_score', desc=True)
        elif sort_by == 'active':
            q = q.order('last_active_at', desc=True)
        else:
            q = q.order('created_at', desc=True)

        res = q.range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'users': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_users] {e}")
        return {'success': False, 'users': [], 'total': 0, 'error': str(e)}


def get_user_detail(user_id: str) -> Dict[str, Any]:
    """Retrieve full detail profile, recent documents, and view history for a user."""
    db = get_db()
    if not db or not user_id:
        return {'success': False, 'error': 'Invalid request'}
    try:
        p_res = db.table('profiles').select('*').eq('id', user_id).limit(1).execute()
        if not p_res.data:
            return {'success': False, 'error': 'User not found'}
        user = p_res.data[0]

        docs_res = db.table('documents').select('id, title, status, view_count, created_at').eq('uploader_id', user_id).order('created_at', desc=True).limit(20).execute()
        views_res = db.table('document_views').select('accessed_at, document_id, documents(title)').eq('user_id', user_id).order('accessed_at', desc=True).limit(20).execute()

        return {
            'success': True,
            'profile': user,
            'documents': docs_res.data or [],
            'recent_views': views_res.data or []
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


def set_user_role(actor_user: dict, target_user_id: str, new_role: str) -> Tuple[bool, str]:
    """Change a user role safely with anti-lockout and privilege validation."""
    valid_roles = {'student', 'teacher', 'moderator', 'admin', 'creator'}
    new_role = (new_role or '').lower().strip()
    if new_role not in valid_roles:
        return False, f"Invalid role. Choose from: {', '.join(valid_roles)}"

    actor_role = get_user_role(actor_user)
    if new_role == 'admin' and actor_role != 'superadmin':
        return False, "Only a Superadmin can promote users to Administrator."

    allowed, reason = check_anti_lockout(actor_user, target_user_id, 'demote' if new_role != 'admin' else 'promote')
    if not allowed:
        return False, reason

    db = get_db()
    if not db:
        return False, "Database client not initialized"

    try:
        prev = db.table('profiles').select('role').eq('id', target_user_id).limit(1).execute()
        old_role = prev.data[0].get('role') if prev.data else 'student'

        res = db.table('profiles').update({'role': new_role}).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found or update failed"

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='update_role',
            target_type='user',
            target_id=target_user_id,
            old_value=old_role,
            new_value=new_role,
            reason=f"Role changed from {old_role} to {new_role}"
        )
        return True, f"User role successfully updated to '{new_role}'"
    except Exception as e:
        return False, str(e)


def set_user_block(actor_user: dict, target_user_id: str, is_blocked: bool, reason: str = '', expiry_days: Optional[int] = None) -> Tuple[bool, str]:
    """Block or unblock a user account."""
    action = 'block' if is_blocked else 'unblock'
    allowed, err = check_anti_lockout(actor_user, target_user_id, action)
    if not allowed:
        return False, err

    db = get_db()
    if not db:
        return False, "Database client not initialized"

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        blocked_until = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat() if (is_blocked and expiry_days) else None

        update_payload = {
            'is_blocked': is_blocked,
            'blocked_reason': reason if is_blocked else None,
            'block_reason': reason if is_blocked else None,
            'blocked_until': blocked_until,
            'updated_at': now_iso
        }
        if is_blocked:
            cur_ver = get_user_token_version(target_user_id) or 1
            update_payload['token_version'] = cur_ver + 1
            _token_version_cache[target_user_id] = {'version': cur_ver + 1, 'time': time.time()}
        res = db.table('profiles').update(update_payload).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found or update failed"

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action=action,
            target_type='user',
            target_id=target_user_id,
            new_value=update_payload,
            reason=reason
        )
        return True, f"User successfully {'blocked' if is_blocked else 'unblocked'}."
    except Exception as e:
        return False, str(e)


def set_user_ban(actor_user: dict, target_user_id: str, is_banned: bool, reason: str = '') -> Tuple[bool, str]:
    """Ban or unban a user account permanently."""
    action = 'ban' if is_banned else 'unban'
    allowed, err = check_anti_lockout(actor_user, target_user_id, action)
    if not allowed:
        return False, err

    db = get_db()
    if not db:
        return False, "Database client not initialized"

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        admin_uid = actor_user.get('uid') or actor_user.get('id')
        update_payload = {
            'is_banned': is_banned,
            'banned_reason': reason if is_banned else None,
            'banned_at': now_iso if is_banned else None,
            'banned_by': admin_uid if is_banned and validate_uuid(admin_uid) else None,
            'account_status': 'banned' if is_banned else 'active',
            'updated_at': now_iso
        }
        if is_banned:
            cur_ver = get_user_token_version(target_user_id) or 1
            update_payload['token_version'] = cur_ver + 1
            _token_version_cache[target_user_id] = {'version': cur_ver + 1, 'time': time.time()}
        res = db.table('profiles').update(update_payload).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found or update failed"

        record_audit_log(
            admin_id=admin_uid,
            admin_email=actor_user.get('email', 'admin'),
            action=action,
            target_type='user',
            target_id=target_user_id,
            new_value=update_payload,
            reason=reason
        )
        return True, f"User successfully {'banned' if is_banned else 'unbanned'}."
    except Exception as e:
        return False, str(e)


def set_user_account_status(actor_user: dict, target_user_id: str, status: str) -> Tuple[bool, str]:
    """Update account status: 'active', 'suspended', 'deactivated'."""
    status = (status or '').lower().strip()
    if status not in ('active', 'suspended', 'deactivated'):
        return False, "Status must be active, suspended, or deactivated."

    allowed, err = check_anti_lockout(actor_user, target_user_id, status)
    if not allowed:
        return False, err

    db = get_db()
    if not db:
        return False, "Database unavailable"

    try:
        res = db.table('profiles').update({'account_status': status, 'updated_at': datetime.now(timezone.utc).isoformat()}).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found"
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action=f"account_status_{status}",
            target_type='user',
            target_id=target_user_id,
            new_value=status
        )
        return True, f"Account status set to '{status}'"
    except Exception as e:
        return False, str(e)


def soft_delete_user(actor_user: dict, target_user_id: str) -> Tuple[bool, str]:
    """Soft delete user account."""
    allowed, err = check_anti_lockout(actor_user, target_user_id, 'soft_delete')
    if not allowed:
        return False, err

    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = db.table('profiles').update({
            'is_deleted': True,
            'deleted_at': now_iso,
            'updated_at': now_iso
        }).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found"
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='soft_delete_user',
            target_type='user',
            target_id=target_user_id
        )
        return True, "User account soft-deleted successfully"
    except Exception as e:
        return False, str(e)


def restore_user(actor_user: dict, target_user_id: str) -> Tuple[bool, str]:
    """Restore soft deleted user."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        res = db.table('profiles').update({
            'is_deleted': False,
            'deleted_at': None,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('id', target_user_id).execute()
        if not res.data:
            return False, "User not found"
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='restore_user',
            target_type='user',
            target_id=target_user_id
        )
        return True, "User account restored successfully"
    except Exception as e:
        return False, str(e)


def hard_delete_user(actor_user: dict, target_user_id: str) -> Tuple[bool, str]:
    """Permanently delete user profile and cascading references."""
    allowed, err = check_anti_lockout(actor_user, target_user_id, 'delete')
    if not allowed:
        return False, err

    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        # Cascade child records
        for tbl, col in [
            ('document_views', 'user_id'),
            ('document_likes', 'user_id'),
            ('document_bookmarks', 'user_id'),
            ('user_kyc_details', 'user_id'),
            ('creator_wallets', 'user_id'),
            ('user_credit_ledger', 'user_id'),
            ('credit_transactions', 'user_id'),
        ]:
            try:
                db.table(tbl).delete().eq(col, target_user_id).execute()
            except Exception:
                pass

        res = db.table('profiles').delete().eq('id', target_user_id).execute()
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='hard_delete_user',
            target_type='user',
            target_id=target_user_id
        )
        return True, "User profile permanently deleted."
    except Exception as e:
        return False, str(e)


def bulk_user_action(actor_user: dict, action: str, user_ids: List[str], reason: str = '') -> Dict[str, Any]:
    """Execute bulk actions: block, unblock, verify, delete."""
    if not user_ids:
        return {'success': False, 'message': 'No user IDs provided'}

    success_count = 0
    errors = []
    for uid in user_ids:
        if action == 'block':
            ok, msg = set_user_block(actor_user, uid, True, reason)
        elif action == 'unblock':
            ok, msg = set_user_block(actor_user, uid, False, reason)
        elif action == 'verify':
            ok, msg = update_user_verification(actor_user, uid, True)
        elif action == 'delete':
            ok, msg = soft_delete_user(actor_user, uid)
        else:
            return {'success': False, 'message': f'Unknown action {action}'}

        if ok:
            success_count += 1
        else:
            errors.append(f"{uid}: {msg}")

    return {
        'success': True,
        'action': action,
        'affected': success_count,
        'total': len(user_ids),
        'errors': errors
    }


def update_user_verification(actor_user: dict, user_id: str, is_verified: bool) -> Tuple[bool, str]:
    """Mark a user profile as verified or unverified."""
    db = get_db()
    if not db:
        return False, "Database client not initialized"
    try:
        admin_uid = actor_user.get('uid') or actor_user.get('id')
        now_iso = datetime.now(timezone.utc).isoformat()
        update_payload = {
            'is_verified': is_verified,
            'verified_at': now_iso if is_verified else None,
            'verified_by': admin_uid if is_verified and validate_uuid(admin_uid) else None,
            'updated_at': now_iso
        }
        res = db.table('profiles').update(update_payload).eq('id', user_id).execute()
        if not res.data:
            return False, "User not found"

        record_audit_log(
            admin_id=admin_uid,
            admin_email=actor_user.get('email', 'admin'),
            action='verify_user',
            target_type='user',
            target_id=user_id,
            new_value=is_verified
        )
        return True, f"User {'verified' if is_verified else 'unverified'} successfully."
    except Exception as e:
        return False, str(e)


# ─── File & Multi-Provider Storage Management ────────────────────────────────

def list_files(
    search: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """Query uploaded documents with metadata, uploader, size, and status."""
    db = get_db()
    if not db:
        return {'success': False, 'files': [], 'total': 0}
    try:
        offset = (max(1, page) - 1) * limit
        q = db.table('documents').select(
            'id, title, status, uploader_id, file_url, storage_provider, provider_public_id, '
            'file_size_bytes, view_count, like_count, created_at, verification_notes, '
            'profiles!documents_uploader_id_fkey(full_name, email)',
            count='exact'
        )
        if search:
            clean_s = search.replace('%', '')
            q = q.ilike('title', f"%{clean_s}%")
        if status and status.lower() != 'all':
            q = q.eq('status', status.lower())

        res = q.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'files': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_files] {e}")
        return {'success': False, 'files': [], 'total': 0, 'error': str(e)}


def delete_file_completely(doc_id: str, actor_user: dict, reason: str = "Admin manual removal") -> Tuple[bool, str]:
    """
    Permanently deletes a file across:
    1. Cloudinary
    2. Supabase Storage buckets
    3. Firebase Storage
    4. Database relations (views, likes, bookmarks, search documents, reports, documents)
    """
    db = get_db()
    if not db:
        return False, "Database client not initialized"

    try:
        doc_res = db.table('documents').select('*').eq('id', doc_id).limit(1).execute()
        if not doc_res.data:
            return False, "File record not found in database"
        doc = doc_res.data[0]
        file_url = doc.get('file_url') or ''
        provider_public_id = doc.get('provider_public_id')
        storage_provider = doc.get('storage_provider')

        # 1. Cloudinary purge
        cld_id = provider_public_id
        if not cld_id and 'cloudinary.com' in file_url:
            m = re.search(r'/(?:image|raw|video)/upload/(?:v\d+/)?([^?#]+)', file_url)
            if m:
                cld_id = m.group(1)
        if cld_id or storage_provider == 'cloudinary' or 'cloudinary.com' in file_url:
            try:
                from methods.cloudinary_upload import delete_file_from_cloudinary
                if cld_id:
                    res_raw = delete_file_from_cloudinary(cld_id, resource_type='raw')
                    if not res_raw.get('success'):
                        delete_file_from_cloudinary(cld_id, resource_type='image')
            except Exception as cld_err:
                log.warning(f"[delete_file_completely] Cloudinary cleanup notice: {cld_err}")

        # 2. Supabase Storage purge
        try:
            if 'supabase.co/storage/v1/object/public/' in file_url:
                path_part = file_url.split('/storage/v1/object/public/')[-1]
                bucket = path_part.split('/')[0]
                file_key = '/'.join(path_part.split('/')[1:])
                db.storage.from_(bucket).remove([file_key])
            if cld_id:
                for ext in ['', '.pdf', '.txt', '.bin', '.jpg', '.png']:
                    try:
                        db.storage.from_('public').remove([f"cloudinary_fallback/{cld_id}{ext}"])
                    except Exception:
                        pass
        except Exception as sb_err:
            log.debug(f"[delete_file_completely] Supabase storage note: {sb_err}")

        # 3. Firebase Storage purge
        if 'firebasestorage.googleapis.com' in file_url or storage_provider == 'firebase':
            try:
                from methods.storage import delete_file
                blob_name = provider_public_id
                if not blob_name and '/o/' in file_url:
                    import urllib.parse
                    blob_name = urllib.parse.unquote(file_url.split('/o/')[1].split('?')[0])
                if blob_name:
                    delete_file(blob_name)
            except Exception as fb_err:
                log.warning(f"[delete_file_completely] Firebase storage cleanup notice: {fb_err}")

        # 4. Database relations purge
        for tbl, col in [
            ('search_documents', 'file_id'),
            ('document_views', 'document_id'),
            ('document_likes', 'document_id'),
            ('document_bookmarks', 'document_id'),
            ('document_votes', 'document_id'),
            ('document_ratings', 'document_id'),
            ('viewer_failure_reports', 'doc_id')
        ]:
            try:
                db.table(tbl).delete().eq(col, doc_id).execute()
            except Exception:
                pass

        try:
            db.table('material_requests').update({'response_document_id': None}).eq('response_document_id', doc_id).execute()
        except Exception:
            pass

        # 5. Delete document row
        db.table('documents').delete().eq('id', doc_id).execute()

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='delete_file_completely',
            target_type='document',
            target_id=doc_id,
            reason=reason
        )
        return True, "File and associated storage objects permanently removed."
    except Exception as e:
        log.error(f"[delete_file_completely] {e}")
        return False, str(e)


def bulk_delete_files(doc_ids: List[str], actor_user: dict, reason: str = "Admin bulk file removal") -> Dict[str, Any]:
    """Purge multiple files across storage and database."""
    deleted_count = 0
    errors = []
    for doc_id in doc_ids:
        ok, msg = delete_file_completely(doc_id, actor_user, reason)
        if ok:
            deleted_count += 1
        else:
            errors.append(f"{doc_id}: {msg}")
    return {
        'success': True,
        'deleted_count': deleted_count,
        'total': len(doc_ids),
        'errors': errors
    }


def flag_quarantine_file(doc_id: str, actor_user: dict, reason: str) -> Tuple[bool, str]:
    """Flag or quarantine a suspicious document to prevent public downloads."""
    db = get_db()
    if not db:
        return False, "Database client unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        res = db.table('documents').update({
            'status': 'quarantined',
            'verification_notes': f"Quarantined by moderation: {reason}",
            'updated_at': now_iso
        }).eq('id', doc_id).execute()
        if not res.data:
            return False, "Document not found"

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='quarantine_file',
            target_type='document',
            target_id=doc_id,
            reason=reason
        )
        return True, "Document quarantined from public access."
    except Exception as e:
        return False, str(e)


# ─── System & Site Settings ──────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    'maintenance_mode': False,
    'registration_enabled': True,
    'uploads_enabled': True,
    'payouts_enabled': True,
    'ad_monetization_enabled': True,
    'site_announcement': '',
    'min_withdrawal_inr': 100
}


def get_site_settings() -> Dict[str, Any]:
    """Read global site settings with L1 caching."""
    from cache_manager import get_cache
    cache = get_cache()
    cache_key = "admin:site:settings:v1"
    if cache and hasattr(cache, 'l1'):
        try:
            cached = cache.l1.get(cache_key)
            if cached and cached[0] and isinstance(cached[0], dict):
                return cached[0]
        except Exception:
            pass

    db = get_db()
    settings = dict(DEFAULT_SETTINGS)
    if db:
        try:
            res = db.table('admin_site_settings').select('*').execute()
            for row in (res.data or []):
                settings[row['key']] = row.get('value')
        except Exception:
            pass

    if cache and hasattr(cache, 'l1'):
        try:
            cache.l1.set(cache_key, settings, ttl=300)
        except Exception:
            pass
    return settings


def update_site_setting(actor_user: dict, key: str, value: Any) -> Tuple[bool, str]:
    """Update a specific site configuration flag."""
    db = get_db()
    if not db:
        return False, "Database client unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        admin_uid = actor_user.get('uid') or actor_user.get('id')
        db.table('admin_site_settings').upsert({
            'key': key,
            'value': value,
            'updated_by': admin_uid if validate_uuid(admin_uid) else None,
            'updated_at': now_iso
        }).execute()

        from cache_manager import get_cache
        cache = get_cache()
        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.delete("admin:site:settings:v1")
            except Exception:
                pass

        record_audit_log(
            admin_id=admin_uid,
            admin_email=actor_user.get('email', 'admin'),
            action=f"update_setting_{key}",
            target_type='system_setting',
            target_id=key,
            new_value=value
        )
        return True, f"Setting '{key}' successfully updated."
    except Exception as e:
        return False, str(e)


# ─── Platform Dashboard KPIs ────────────────────────────────────────────────

def get_platform_dashboard_kpis() -> Dict[str, Any]:
    """Fetch high-level counters for dashboard stat cards."""
    db = get_db()
    if not db:
        return {'success': False, 'stats': {}}
    try:
        # User counts
        users_res = db.table('profiles').select('id, is_verified, is_blocked, is_banned', count='exact').execute()
        total_users = users_res.count or len(users_res.data or [])
        verified_users = sum(1 for u in (users_res.data or []) if u.get('is_verified'))
        blocked_users = sum(1 for u in (users_res.data or []) if u.get('is_blocked'))
        banned_users = sum(1 for u in (users_res.data or []) if u.get('is_banned'))

        # Document counts
        docs_res = db.table('documents').select('id, status', count='exact').execute()
        total_docs = docs_res.count or len(docs_res.data or [])
        pending_docs = sum(1 for d in (docs_res.data or []) if d.get('status') == 'pending')
        approved_docs = sum(1 for d in (docs_res.data or []) if d.get('status') == 'approved')

        # Viewer failure reports
        reports_res = db.table('viewer_failure_reports').select('id', count='exact').eq('status', 'pending').execute()
        pending_reports = reports_res.count or len(reports_res.data or [])

        # Payout requests
        payouts_res = db.table('creator_payout_requests').select('id, amount').eq('status', 'pending').execute()
        pending_payouts_count = len(payouts_res.data or [])
        pending_payouts_amount = sum(float(p.get('amount', 0)) for p in (payouts_res.data or []))

        return {
            'success': True,
            'stats': {
                'total_users': total_users,
                'verified_users': verified_users,
                'blocked_users': blocked_users,
                'banned_users': banned_users,
                'unverified_users': max(0, total_users - verified_users),
                'total_documents': total_docs,
                'pending_documents': pending_docs,
                'approved_documents': approved_docs,
                'pending_reports': pending_reports,
                'pending_payouts_count': pending_payouts_count,
                'pending_payouts_amount': pending_payouts_amount
            }
        }
    except Exception as e:
        log.error(f"[get_platform_dashboard_kpis] {e}")
        return {'success': False, 'stats': {}, 'error': str(e)}


# ── Phase 2: Enhanced User Moderation, Tokens, Notes & Taxonomy ───────────────

_token_version_cache = {}


def get_user_token_version(user_id: str) -> Optional[int]:
    """Retrieve token_version for user with 30s in-memory caching."""
    if not user_id:
        return None
    cached = _token_version_cache.get(user_id)
    if cached and (time.time() - cached.get('time', 0)) < 30:
        return cached.get('version')
    db = get_db()
    if not db:
        return None
    try:
        res = db.table('profiles').select('token_version').eq('id', user_id).limit(1).execute()
        if res.data:
            ver = res.data[0].get('token_version') or 1
            _token_version_cache[user_id] = {'version': ver, 'time': time.time()}
            return ver
    except Exception:
        pass
    return None


def force_logout_user(actor_user: dict, target_user_id: str) -> Tuple[bool, str]:
    """Revoke all active sessions for a target user by incrementing token_version."""
    allowed, err = check_anti_lockout(actor_user, target_user_id, 'force_logout')
    if not allowed:
        return False, err
    db = get_db()
    if not db:
        return False, "Database client not initialized"
    try:
        cur_ver = get_user_token_version(target_user_id) or 1
        new_ver = cur_ver + 1
        now_iso = datetime.now(timezone.utc).isoformat()
        db.table('profiles').update({'token_version': new_ver, 'updated_at': now_iso}).eq('id', target_user_id).execute()
        _token_version_cache[target_user_id] = {'version': new_ver, 'time': time.time()}
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='force_logout',
            target_type='user',
            target_id=target_user_id,
            old_value={'token_version': cur_ver},
            new_value={'token_version': new_ver},
            reason='Administrative session revocation'
        )
        return True, "User session revoked successfully."
    except Exception as e:
        return False, str(e)


def warn_user(actor_user: dict, target_user_id: str, reason: str) -> Tuple[bool, str]:
    """Issue a formal warning to a user, create an admin note, and record audit."""
    if not reason or not reason.strip():
        return False, "Warning reason is required"
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        add_admin_note(actor_user, target_user_id, f"FORMAL WARNING: {reason.strip()}")
        try:
            log_notification(
                user_email=target_user_id,
                notification_type='warning',
                title='Administrative Warning',
                message=f"You have received a formal warning: {reason.strip()}. Further violations may lead to account suspension.",
                url='/contact'
            )
        except Exception:
            pass
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='warn_user',
            target_type='user',
            target_id=target_user_id,
            reason=reason.strip()
        )
        return True, "Warning delivered to user."
    except Exception as e:
        return False, str(e)


def add_admin_note(actor_user: dict, target_user_id: str, note: str) -> Tuple[bool, str]:
    """Add a permanent administrative note to a user account."""
    if not note or not note.strip():
        return False, "Note text cannot be empty"
    db = get_db()
    if not db:
        return False, "Database client unavailable"
    try:
        admin_id = actor_user.get('uid') or actor_user.get('id')
        admin_email = actor_user.get('email', 'admin')
        db.table('admin_notes').insert({
            'user_id': target_user_id,
            'admin_id': admin_id if validate_uuid(admin_id) else None,
            'admin_email': admin_email,
            'note': note.strip(),
            'created_at': datetime.now(timezone.utc).isoformat()
        }).execute()
        return True, "Note saved."
    except Exception as e:
        return False, str(e)


def get_admin_notes(target_user_id: str) -> List[dict]:
    """Retrieve history of administrative notes for a user."""
    db = get_db()
    if not db or not target_user_id:
        return []
    try:
        res = db.table('admin_notes').select('*').eq('user_id', target_user_id).order('created_at', desc=True).limit(50).execute()
        return res.data or []
    except Exception:
        return []


def adjust_user_wallet(actor_user: dict, target_user_id: str, amount: float, reason: str) -> Tuple[bool, str]:
    """Manually adjust creator wallet with full ledger tracking and mandatory reason."""
    if not has_min_role(actor_user, 'admin'):
        return False, "Permission Denied: Admin or Superadmin role required for wallet adjustments."
    if not reason or not reason.strip():
        return False, "A reason is strictly required for wallet adjustment."
    try:
        amt = float(amount)
        if amt == 0:
            return False, "Adjustment amount cannot be zero."
    except (ValueError, TypeError):
        return False, "Invalid adjustment amount."

    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        admin_id = actor_user.get('uid') or actor_user.get('id')
        admin_email = actor_user.get('email', 'admin')
        now_iso = datetime.now(timezone.utc).isoformat()

        # Insert ledger entry
        db.table('wallet_ledger').insert({
            'creator_id': target_user_id,
            'amount': amt,
            'type': 'adjustment',
            'status': 'completed',
            'order_id': f"ADJ-{int(time.time())}-{str(target_user_id)[:8]}",
            'notes': f"Admin adjustment by {admin_email}: {reason.strip()}",
            'created_at': now_iso
        }).execute()

        # Update wallet balance
        w_res = db.table('creator_wallets').select('*').eq('user_id', target_user_id).limit(1).execute()
        if w_res.data:
            current_bal = float(w_res.data[0].get('current_balance', 0))
            db.table('creator_wallets').update({
                'current_balance': round(current_bal + amt, 2),
                'updated_at': now_iso
            }).eq('user_id', target_user_id).execute()

        record_audit_log(
            admin_id=admin_id,
            admin_email=admin_email,
            action='wallet_adjustment',
            target_type='wallet',
            target_id=target_user_id,
            new_value={'amount': amt, 'reason': reason.strip()},
            reason=reason.strip()
        )
        return True, f"Wallet successfully adjusted by ₹{amt:g}."
    except Exception as e:
        return False, str(e)


def auto_unblock_expired_users() -> int:
    """Scheduled task to automatically lift expired temporary blocks."""
    db = get_db()
    if not db:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        res = db.table('profiles').select('id, email, blocked_until').eq('is_blocked', True).lte('blocked_until', now_iso).execute()
        expired_users = res.data or []
        count = 0
        for u in expired_users:
            uid = u.get('id')
            db.table('profiles').update({
                'is_blocked': False,
                'blocked_until': None,
                'blocked_reason': None,
                'block_reason': None,
                'updated_at': now_iso
            }).eq('id', uid).execute()
            record_audit_log(
                admin_id=None,
                admin_email='system_scheduler',
                action='auto_unblock',
                target_type='user',
                target_id=uid,
                reason='Temporary block period expired'
            )
            try:
                log_notification(
                    user_email=uid,
                    notification_type='account_status',
                    title='Temporary Block Expired',
                    message='Your temporary block has expired and your account access has been restored.',
                    url='/account'
                )
            except Exception:
                pass
            count += 1
        return count
    except Exception as e:
        log.error(f"[auto_unblock_expired_users] Error: {e}")
        return 0


def find_duplicate_files(threshold: float = 0.8) -> List[dict]:
    """Group documents by identical file_hash or title similarity with L1 caching."""
    from cache_manager import get_cache
    cache = get_cache()
    cache_key = f"admin:duplicates:threshold:{threshold}"
    if cache and hasattr(cache, 'l1'):
        try:
            cached = cache.l1.get(cache_key)
            if cached and cached[0] and isinstance(cached[0], list):
                return cached[0]
        except Exception:
            pass

    db = get_db()
    if not db:
        return []
    try:
        res = db.table('documents').select('id, title, file_hash, uploader_id, created_at, status, view_count, is_paid, price').order('created_at', desc=True).limit(500).execute()
        docs = res.data or []
        groups = {}

        # 1. Exact file_hash matches
        hash_map = {}
        for d in docs:
            h = d.get('file_hash')
            if h and len(h) >= 16:
                hash_map.setdefault(h, []).append(d)
        for h, items in hash_map.items():
            if len(items) > 1:
                groups[f"hash_{h[:12]}"] = {
                    'group_id': f"hash_{h[:12]}",
                    'type': 'Exact File Hash',
                    'match_key': h[:16],
                    'count': len(items),
                    'items': items
                }

        # 2. Normalized title matches
        def clean_title(t):
            return re.sub(r'[^a-z0-9]', '', (t or '').lower())

        title_map = {}
        for d in docs:
            nt = clean_title(d.get('title'))
            if len(nt) >= 6:
                title_map.setdefault(nt, []).append(d)
        for nt, items in title_map.items():
            if len(items) > 1 and f"title_{nt[:12]}" not in groups:
                groups[f"title_{nt[:12]}"] = {
                    'group_id': f"title_{nt[:12]}",
                    'type': 'Similar Title',
                    'match_key': items[0].get('title', ''),
                    'count': len(items),
                    'items': items
                }

        out = list(groups.values())
        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.set(cache_key, out, ttl=180)
            except Exception:
                pass
        return out
    except Exception as e:
        log.error(f"[find_duplicate_files] {e}")
        return []


def resolve_duplicate_group(actor_user: dict, keep_doc_id: str, remove_doc_ids: List[str], reason: str = 'Duplicate removal') -> Tuple[bool, str]:
    """Keep one canonical file and soft-delete duplicates."""
    if not keep_doc_id or not remove_doc_ids:
        return False, "keep_doc_id and remove_doc_ids are required"
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        db.table('documents').update({'updated_at': now_iso}).eq('id', keep_doc_id).execute()

        for r_id in remove_doc_ids:
            if r_id != keep_doc_id:
                db.table('documents').update({
                    'status': 'deleted',
                    'is_deleted': True,
                    'deleted_at': now_iso,
                    'deleted_reason': f"Duplicate resolved: kept {keep_doc_id}. {reason}"
                }).eq('id', r_id).execute()

        from cache_manager import get_cache
        cache = get_cache()
        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.delete("admin:duplicates:threshold:0.8")
            except Exception:
                pass

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='resolve_duplicates',
            target_type='document',
            target_id=keep_doc_id,
            new_value={'removed': remove_doc_ids},
            reason=reason
        )
        return True, f"Kept primary document {keep_doc_id} and removed {len(remove_doc_ids)} duplicates."
    except Exception as e:
        return False, str(e)


def _invalidate_taxonomy_cache():
    try:
        from cache_manager import get_cache
        cache = get_cache()
        if cache and hasattr(cache, 'l1'):
            cache.l1.delete("admin:taxonomy:overview:v1")
    except Exception:
        pass


def get_taxonomy_overview() -> dict:
    """Fetch colleges, departments, and subjects for admin management with L1 caching."""
    from cache_manager import get_cache
    cache = get_cache()
    cache_key = "admin:taxonomy:overview:v1"
    if cache and hasattr(cache, 'l1'):
        try:
            cached = cache.l1.get(cache_key)
            if cached and cached[0] and isinstance(cached[0], dict) and cached[0].get('colleges'):
                return cached[0]
        except Exception:
            pass

    db = get_db()
    if not db:
        return {'colleges': [], 'departments': [], 'subjects': []}
    try:
        colleges_raw = db.table('colleges').select('id, name, abbreviation, city').order('name').execute().data or []
        departments_raw = db.table('departments').select('id, name, abbreviation').order('name').execute().data or []
        subjects_raw = db.table('subjects').select('id, name, subject_code, abbreviation').order('name').limit(500).execute().data or []

        colleges = [{'id': c['id'], 'name': c['name'], 'code': c.get('abbreviation') or c.get('city') or '', 'city': c.get('city') or ''} for c in colleges_raw]
        departments = [{'id': d['id'], 'name': d['name'], 'code': d.get('abbreviation') or ''} for d in departments_raw]
        subjects = [{'id': s['id'], 'name': s['name'], 'code': s.get('subject_code') or s.get('abbreviation') or ''} for s in subjects_raw]

        result = {
            'colleges': colleges,
            'departments': departments,
            'subjects': subjects
        }
        if cache and hasattr(cache, 'l1'):
            try:
                cache.l1.set(cache_key, result, ttl=300)
            except Exception:
                pass
        return result
    except Exception as e:
        log.error(f"[get_taxonomy_overview] {e}")
        return {'colleges': [], 'departments': [], 'subjects': []}


def save_taxonomy_item(
    actor_user: dict,
    item_type: str,
    item_id: Optional[str],
    name: str,
    code: str = '',
    city: str = ''
) -> Tuple[bool, str]:
    """Create or update college, department, or subject."""
    db = get_db()
    if not db:
        return False, "Database unavailable"

    item_type = item_type.strip().lower()
    table_map = {
        'college': 'colleges',
        'colleges': 'colleges',
        'department': 'departments',
        'departments': 'departments',
        'subject': 'subjects',
        'subjects': 'subjects'
    }
    table_name = table_map.get(item_type)
    if not table_name:
        return False, f"Invalid taxonomy type '{item_type}'"

    name = name.strip()
    if not name:
        return False, "Name cannot be empty"

    now_iso = datetime.now(timezone.utc).isoformat()
    code_val = code.strip().upper() if code else None

    try:
        if 'college' in item_type:
            canonical_type = 'college'
        elif 'department' in item_type or 'dept' in item_type:
            canonical_type = 'department'
        else:
            canonical_type = 'subject'

        if canonical_type == 'college':
            payload = {
                'name': name,
                'abbreviation': code_val,
                'city': city.strip() or None,
                'updated_at': now_iso
            }
        elif canonical_type == 'department':
            payload = {
                'name': name,
                'abbreviation': code_val,
                'updated_at': now_iso
            }
        else:
            payload = {
                'name': name,
                'subject_code': code_val,
                'abbreviation': code_val,
                'updated_at': now_iso
            }

        if item_id and validate_uuid(item_id):
            db.table(table_name).update(payload).eq('id', item_id).execute()
            action = f"update_{canonical_type}"
            target_id = item_id
        else:
            target_id = str(uuid.uuid4())
            payload['id'] = target_id
            payload['created_at'] = now_iso
            db.table(table_name).insert(payload).execute()
            action = f"create_{canonical_type}"

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action=action,
            target_type=canonical_type,
            target_id=target_id,
            new_value=payload,
            reason=f"Admin saved {canonical_type}: {name}"
        )
        _invalidate_taxonomy_cache()
        return True, f"{canonical_type.capitalize()} saved successfully."
    except Exception as e:
        log.error(f"[save_taxonomy_item] {e}")
        return False, str(e)


def delete_taxonomy_item(
    actor_user: dict,
    item_type: str,
    item_id: str,
    reason: str = ''
) -> Tuple[bool, str]:
    """Delete a college, department, or subject node with safety check."""
    db = get_db()
    if not db:
        return False, "Database unavailable"

    item_type = item_type.strip().lower()
    table_map = {
        'college': 'colleges',
        'colleges': 'colleges',
        'department': 'departments',
        'departments': 'departments',
        'subject': 'subjects',
        'subjects': 'subjects'
    }
    table_name = table_map.get(item_type)
    if not table_name:
        return False, f"Invalid taxonomy type '{item_type}'"

    if not validate_uuid(item_id):
        return False, "Invalid UUID format"

    if 'college' in item_type:
        canonical_type = 'college'
    elif 'department' in item_type or 'dept' in item_type:
        canonical_type = 'department'
    else:
        canonical_type = 'subject'

    try:
        # Check linked documents
        if canonical_type == 'college':
            docs = db.table('documents').select('id', count='exact').eq('college_id', item_id).limit(1).execute()
            if docs.count and docs.count > 0:
                return False, f"Cannot delete: {docs.count} documents are currently linked to this college."
        elif canonical_type == 'subject':
            docs = db.table('documents').select('id', count='exact').eq('subject_id', item_id).limit(1).execute()
            if docs.count and docs.count > 0:
                return False, f"Cannot delete: {docs.count} documents are currently linked to this subject."

        db.table(table_name).delete().eq('id', item_id).execute()
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action=f"delete_{canonical_type}",
            target_type=canonical_type,
            target_id=item_id,
            reason=reason or f"Deleted {canonical_type} node"
        )
        _invalidate_taxonomy_cache()
        return True, f"{canonical_type.capitalize()} deleted successfully."
    except Exception as e:
        log.error(f"[delete_taxonomy_item] {e}")
        return False, str(e)


def get_college_departments(college_id: str) -> List[dict]:
    """Retrieve departments linked to a given college."""
    db = get_db()
    if not db or not validate_uuid(college_id):
        return []
    try:
        res = db.table('college_departments').select('department_id, departments(id, name, abbreviation)').eq('college_id', college_id).execute()
        depts = []
        for row in (res.data or []):
            d = row.get('departments') or {}
            depts.append({
                'id': row.get('department_id'),
                'name': d.get('name') or 'Unknown Department',
                'code': d.get('abbreviation') or ''
            })
        return sorted(depts, key=lambda x: x['name'])
    except Exception as e:
        log.error(f"[get_college_departments] {e}")
        return []


def link_college_department(actor_user: dict, college_id: str, department_id: str) -> Tuple[bool, str]:
    """Link a department to a college."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    if not validate_uuid(college_id) or not validate_uuid(department_id):
        return False, "Invalid ID format"
    try:
        existing = db.table('college_departments').select('department_id').eq('college_id', college_id).eq('department_id', department_id).execute()
        if existing.data:
            return True, "Department already linked to this college."

        db.table('college_departments').insert({
            'college_id': college_id,
            'department_id': department_id
        }).execute()

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action="link_college_department",
            target_type="college_departments",
            target_id=f"{college_id}:{department_id}",
            new_value={'college_id': college_id, 'department_id': department_id},
            reason="Linked department to college"
        )
        _invalidate_taxonomy_cache()
        return True, "Department linked successfully."
    except Exception as e:
        log.error(f"[link_college_department] {e}")
        return False, str(e)


def unlink_college_department(actor_user: dict, college_id: str, department_id: str) -> Tuple[bool, str]:
    """Unlink a department from a college."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    if not validate_uuid(college_id) or not validate_uuid(department_id):
        return False, "Invalid ID format"
    try:
        db.table('college_departments').delete().eq('college_id', college_id).eq('department_id', department_id).execute()

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action="unlink_college_department",
            target_type="college_departments",
            target_id=f"{college_id}:{department_id}",
            reason="Unlinked department from college"
        )
        _invalidate_taxonomy_cache()
        return True, "Department unlinked successfully."
    except Exception as e:
        log.error(f"[unlink_college_department] {e}")
        return False, str(e)


# ─── Module 4: Promotions Service ─────────────────────────────────────────────

def create_promotion(
    actor_user: dict,
    document_id: str,
    slot: str = 'recommended',
    priority: int = 0,
    starts_at: Optional[str] = None,
    ends_at: Optional[str] = None,
    promo_type: str = 'admin',
    amount_paid: float = 0.0
) -> Tuple[bool, str, dict]:
    """Promote a document to a designated slot (homepage_banner, category_top, search_boost, recommended)."""
    db = get_db()
    if not db:
        return False, "Database unavailable", {}

    if not document_id:
        return False, "document_id is required", {}

    if not validate_uuid(document_id):
        return False, f"Invalid Document UUID format: '{document_id}'. A valid UUID is required.", {}

    slot_clean = slot.strip().lower()
    if slot_clean in ('1', 'banner', 'homepage_banner'):
        slot_clean = 'homepage_banner'
    elif slot_clean in ('2', 'category', 'category_top'):
        slot_clean = 'category_top'
    elif slot_clean in ('3', 'search', 'search_boost'):
        slot_clean = 'search_boost'
    else:
        slot_clean = 'recommended'

    now = datetime.now(timezone.utc)
    if not starts_at:
        starts_at = now.isoformat()
    if not ends_at:
        from datetime import timedelta
        ends_at = (now + timedelta(days=14)).isoformat()

    try:
        priority = int(priority)
    except (ValueError, TypeError):
        priority = 0

    record = {
        'document_id': str(document_id),
        'slot': slot_clean,
        'priority': priority,
        'starts_at': starts_at,
        'ends_at': ends_at,
        'type': promo_type,
        'amount_paid': float(amount_paid or 0.0),
        'status': 'active',
        'impressions': 0,
        'clicks': 0,
        'created_by': actor_user.get('uid') if validate_uuid(actor_user.get('uid')) else None,
        'created_at': now.isoformat(),
        'updated_at': now.isoformat()
    }

    try:
        res = db.table('promotions').insert(record).execute()
        created = res.data[0] if res.data else record
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='create_promotion',
            target_type='promotion',
            target_id=created.get('id', str(document_id)),
            new_value=record,
            reason=f"Promoted document {document_id} to slot {slot}"
        )
        return True, "Promotion activated successfully.", created
    except Exception as e:
        log.error(f"[create_promotion] Error: {e}")
        return False, f"Failed creating promotion: {str(e)}", {}


def list_promotions(slot: Optional[str] = None, status: Optional[str] = None, page: int = 1, limit: int = 12) -> Dict[str, Any]:
    """Fetch paginated promotions with slot and status filters."""
    db = get_db()
    if not db:
        return {'success': False, 'promotions': [], 'total': 0}

    offset = (max(1, page) - 1) * limit
    try:
        q = db.table('promotions').select('*', count='exact')
        if slot:
            q = q.eq('slot', slot.strip().lower())
        if status:
            q = q.eq('status', status.strip().lower())

        res = q.order('priority', desc=True).order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        promos = res.data or []

        # Populate document title and category
        doc_ids = [p.get('document_id') for p in promos if p.get('document_id')]
        if doc_ids:
            try:
                docs = db.table('documents').select('id, title, document_category, price, is_paid').in_('id', doc_ids).execute().data or []
                doc_map = {d['id']: d for d in docs}
                for p in promos:
                    d_info = doc_map.get(p.get('document_id'), {})
                    if d_info:
                        d_info['category'] = d_info.get('document_category') or 'Notes'
                    p['document'] = d_info
            except Exception:
                pass

        return {
            'success': True,
            'promotions': promos,
            'total': res.count or len(promos),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_promotions] Error: {e}")
        return {'success': False, 'promotions': [], 'total': 0}


def update_promotion_status(actor_user: dict, promo_id: str, status: str) -> Tuple[bool, str]:
    """Update promotion status (active, paused, expired, deleted)."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        db.table('promotions').update({
            'status': status.strip().lower(),
            'updated_at': now_iso
        }).eq('id', promo_id).execute()

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='update_promotion_status',
            target_type='promotion',
            target_id=promo_id,
            new_value={'status': status}
        )
        return True, f"Promotion status updated to {status}."
    except Exception as e:
        return False, str(e)


def auto_expire_promotions() -> int:
    """Job task to deactivate promotions past their ends_at date."""
    db = get_db()
    if not db:
        return 0
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        res = db.table('promotions').update({
            'status': 'expired',
            'updated_at': now_iso
        }).eq('status', 'active').lt('ends_at', now_iso).execute()
        return len(res.data or [])
    except Exception as e:
        log.warning(f"[auto_expire_promotions] Error: {e}")
        return 0


def get_active_search_boosts() -> Dict[str, int]:
    """Return map of document_id -> priority boost for search ranking."""
    db = get_db()
    if not db:
        return {}
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        res = db.table('promotions').select('document_id, priority').eq('slot', 'search_boost').eq('status', 'active').gt('ends_at', now_iso).execute()
        return {r['document_id']: int(r.get('priority', 5)) for r in (res.data or [])}
    except Exception:
        return {}


# ─── Module 1: Comprehensive Dashboard Analytics ─────────────────────────────

def get_admin_dashboard_metrics(days: int = 30, bypass_cache: bool = False) -> Dict[str, Any]:
    """Calculate executive KPI stat cards, charts, and attention items with caching."""
    import time
    from cache_manager import get_cache, TTL
    cache = get_cache()
    cache_key = f"admin:dashboard:metrics:{days}"

    if cache and not bypass_cache:
        try:
            cached_data = cache.get_cached(cache_key, level=cache.L1)
            if cached_data and isinstance(cached_data, dict) and cached_data.get('success'):
                out = dict(cached_data)
                out['is_cached'] = True
                return out
        except Exception as c_err:
            log.warning(f"[Dashboard Cache] Read failed: {c_err}")

    db = get_db()
    if not db:
        return {'success': False, 'error': 'Database unavailable'}

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    since_date = (now - timedelta(days=days)).isoformat()
    now_ts = time.time()
    now_iso = now.isoformat()

    try:
        # 1. User metrics
        total_users_res = db.table('profiles').select('id', count='exact').execute()
        total_users = total_users_res.count or 0
        new_users_res = db.table('profiles').select('id', count='exact').gte('created_at', since_date).execute()
        new_users = new_users_res.count or 0

        # 2. File & Moderation metrics
        total_files_res = db.table('documents').select('id', count='exact').execute()
        total_files = total_files_res.count or 0
        new_files_res = db.table('documents').select('id', count='exact').gte('created_at', since_date).execute()
        new_files = new_files_res.count or 0
        pending_files_res = db.table('documents').select('id', count='exact').eq('status', 'pending').execute()
        pending_files = pending_files_res.count or 0

        # 3. Financials (completed orders)
        tx_res = db.table('credit_transactions').select('amount, status, created_at').gte('created_at', since_date).execute()
        transactions = tx_res.data or []
        completed_tx = [t for t in transactions if t.get('status') == 'completed']
        gmv = sum(float(t.get('amount') or 0) for t in completed_tx)
        commission = round(gmv * 0.30, 2)

        refund_tx = [t for t in transactions if t.get('status') == 'refunded']
        refunds_total = sum(float(t.get('amount') or 0) for t in refund_tx)

        # 4. Attention Queues
        payouts_res = db.table('creator_payout_requests').select('id', count='exact').eq('status', 'pending').execute()
        pending_payouts = payouts_res.count or 0

        manual_res = db.table('credit_transactions').select('id', count='exact').eq('status', 'submitted').execute()
        pending_manual = manual_res.count or 0

        reports_res = db.table('viewer_failure_reports').select('id', count='exact').eq('status', 'open').execute()
        open_reports = reports_res.count or 0

        # 5. Timeseries data for revenue and uploads
        days_map = {}
        for i in range(min(days, 30)):
            d_str = (now - timedelta(days=i)).strftime('%Y-%m-%d')
            days_map[d_str] = {'revenue': 0.0, 'uploads': 0, 'signups': 0}

        for t in completed_tx:
            dt_key = (t.get('created_at') or '')[:10]
            if dt_key in days_map:
                days_map[dt_key]['revenue'] += float(t.get('amount') or 0)

        # 6. Conversion Funnel
        views_res = db.table('document_views').select('id', count='exact').gte('accessed_at', since_date).execute()
        total_views = views_res.count or max(1, len(completed_tx) * 12)
        total_previews = int(total_views * 0.45)
        total_purchases = len(completed_tx)

        sorted_days = sorted(days_map.items())
        chart_labels = [k[5:] for k, v in sorted_days]
        chart_revenue = [round(v['revenue'], 2) for k, v in sorted_days]

        result = {
            'success': True,
            'cached_at': now_iso,
            'cached_timestamp': now_ts,
            'is_cached': False,
            'kpis': {
                'total_users': total_users,
                'new_users': new_users,
                'total_files': total_files,
                'new_files': new_files,
                'pending_files': pending_files,
                'gmv': round(gmv, 2),
                'commission': commission,
                'refunds': round(refunds_total, 2),
                'pending_payouts': pending_payouts,
                'pending_manual': pending_manual,
                'open_reports': open_reports
            },
            'charts': {
                'labels': chart_labels,
                'revenue': chart_revenue,
                'funnel': {
                    'views': total_views,
                    'previews': total_previews,
                    'purchases': total_purchases
                }
            }
        }

        if cache:
            try:
                cache.set_cached(cache_key, result, ttl=TTL.MEDIUM)
            except Exception as c_err:
                log.warning(f"[Dashboard Cache] Write failed: {c_err}")

        return result
    except Exception as e:
        log.error(f"[get_admin_dashboard_metrics] Error: {e}")
        return {'success': False, 'error': str(e)}


# ─── Module 8: Search & Trending Insights ─────────────────────────────────────

def get_search_and_trending_insights(days: int = 30) -> Dict[str, Any]:
    """Retrieve top searches, zero-result searches, and trending files."""
    db = get_db()
    if not db:
        return {'top_searches': [], 'zero_result_searches': [], 'trending_files': []}

    from datetime import timedelta
    now = datetime.now(timezone.utc)
    since_date = (now - timedelta(days=days)).isoformat()

    top_searches = []
    zero_searches = []
    trending_files = []

    try:
        # Search analytics
        q_res = db.table('search_analytics').select('query, results_count, created_at').gte('created_at', since_date).limit(500).execute()
        rows = q_res.data or []

        counts = {}
        for r in rows:
            q = (r.get('query') or '').strip().lower()
            if not q:
                continue
            res_cnt = int(r.get('results_count') or 0)
            if q not in counts:
                counts[q] = {'query': q, 'count': 0, 'zero_results': 0}
            counts[q]['count'] += 1
            if res_cnt == 0:
                counts[q]['zero_results'] += 1

        sorted_queries = sorted(counts.values(), key=lambda x: x['count'], reverse=True)
        top_searches = sorted_queries[:20]
        zero_searches = [sq for sq in sorted_queries if sq['zero_results'] > 0][:20]
    except Exception as e:
        log.warning(f"[get_search_and_trending_insights] Search analytics query note: {e}")

    try:
        # Trending documents (high views & likes)
        doc_res = db.table('documents').select('id, title, document_category, price, is_paid, view_count, like_count, created_at').eq('status', 'approved').order('view_count', desc=True).limit(20).execute()
        for d in (doc_res.data or []):
            d['category'] = d.get('document_category') or 'Notes'
            trending_files.append(d)
    except Exception as e:
        log.warning(f"[get_search_and_trending_insights] Trending files note: {e}")

    funnel_data = get_abandoned_funnel_insights(days=days)

    return {
        'success': True,
        'top_searches': top_searches,
        'zero_result_searches': zero_searches,
        'trending_files': trending_files,
        'funnel_stats': funnel_data.get('funnel_stats', {}),
        'incomplete_actions': funnel_data.get('incomplete_actions', [])
    }


def get_abandoned_funnel_insights(days: int = 30) -> Dict[str, Any]:
    """Aggregates uncompleted/abandoned feature funnels (Upload, Search, Channel, Request) across users."""
    db = get_db()
    if not db:
        return {'funnel_stats': {}, 'incomplete_actions': []}

    from datetime import timedelta
    since_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    funnel_stats = {
        'upload': {'initiated': 0, 'completed': 0, 'abandoned': 0},
        'search': {'initiated': 0, 'completed': 0, 'abandoned': 0},
        'create_channel': {'initiated': 0, 'completed': 0, 'abandoned': 0},
    }
    incomplete_actions = []

    try:
        res = db.table('security_audit_logs').select(
            'id, user_id, event, metadata, detected_at'
        ).gte('detected_at', since_date).order('detected_at', desc=True).limit(300).execute()

        raw_events = res.data or []
        user_ids = list({r.get('user_id') for r in raw_events if r.get('user_id')})

        # Fetch profile info for identified users
        profiles_map = {}
        if user_ids:
            try:
                p_res = db.table('profiles').select('id, full_name, email, role').in_('id', user_ids[:100]).execute()
                for p in (p_res.data or []):
                    profiles_map[p['id']] = p
            except Exception:
                pass

        for row in raw_events:
            meta = row.get('metadata') or {}
            if meta.get('category') != 'feature_usage' and not meta.get('feature'):
                continue

            feature = str(meta.get('feature') or 'general').strip().lower()
            action = str(meta.get('action') or 'interact').strip().lower()
            uid = row.get('user_id')
            prof = profiles_map.get(uid) or {}

            if feature not in funnel_stats:
                funnel_stats[feature] = {'initiated': 0, 'completed': 0, 'abandoned': 0}

            if action == 'initiate':
                funnel_stats[feature]['initiated'] += 1
            elif action == 'completed':
                funnel_stats[feature]['completed'] += 1
            elif action in ('abandoned', 'drop_off', 'incomplete'):
                funnel_stats[feature]['abandoned'] += 1
                step_str = meta.get('step') or meta.get('params', {}).get('step') or 'Initiated and Left'
                incomplete_actions.append({
                    'id': row.get('id'),
                    'user_id': uid,
                    'user_name': prof.get('full_name') or (prof.get('email', '').split('@')[0] if prof.get('email') else 'Guest / Anonymous'),
                    'user_email': prof.get('email') or '—',
                    'role': prof.get('role') or 'student',
                    'feature': feature.replace('_', ' ').title(),
                    'step': step_str.replace('_', ' ').title(),
                    'reason': meta.get('reason') or 'Navigated away without completing',
                    'duration_seconds': meta.get('duration_seconds') or meta.get('params', {}).get('duration_seconds') or '—',
                    'detected_at': row.get('detected_at'),
                    'metadata': meta.get('params') or {}
                })
    except Exception as e:
        log.warning(f"[get_abandoned_funnel_insights] Error: {e}")

    for feat, stats in funnel_stats.items():
        init = stats['initiated']
        ab = stats['abandoned']
        stats['drop_off_pct'] = round((ab / init * 100), 1) if init > 0 else 0

    return {
        'funnel_stats': funnel_stats,
        'incomplete_actions': incomplete_actions
    }


# ─── Module 10: Reviews Moderation ───────────────────────────────────────────

def list_reviews(
    status: Optional[str] = None,
    rating: Optional[int] = None,
    search: Optional[str] = None,
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """Fetch paginated reviews and ratings from app feedback and document reviews."""
    db = get_db()
    if not db:
        return {'success': False, 'reviews': [], 'total': 0}

    offset = (max(1, page) - 1) * limit
    try:
        # 1. Query document_reviews
        q = db.table('document_reviews').select('*', count='exact')
        if status:
            q = q.eq('status', status.strip().lower())
        if rating is not None:
            q = q.eq('rating', int(rating))
        if search:
            s = search.strip()
            q = q.ilike('review_text', f"%{s}%")

        res = q.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        reviews = res.data or []

        # 2. If no document_reviews found, query user app feedback & ratings
        total_count = res.count or len(reviews)
        if not reviews:
            try:
                q_fb = db.table('app_feedback').select('*', count='exact')
                if status:
                    q_fb = q_fb.eq('status', status.strip().lower())
                if rating is not None:
                    q_fb = q_fb.eq('rating', int(rating))
                if search:
                    s = search.strip()
                    q_fb = q_fb.ilike('message', f"%{s}%")

                res_fb = q_fb.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
                fb_data = res_fb.data or []
                for f in fb_data:
                    reviews.append({
                        'id': f.get('id'),
                        'document_id': None,
                        'document_title': f"Platform Feedback ({f.get('college') or 'General'})",
                        'user_id': f.get('user_id'),
                        'user_name': f.get('name') or 'Student',
                        'user_email': f.get('branch') or '',
                        'rating': f.get('rating') or 5,
                        'review_text': f.get('message') or '',
                        'verified_purchase': False,
                        'status': f.get('status') or 'approved',
                        'flagged_as_fake': False,
                        'created_at': f.get('created_at'),
                        'source': 'app_feedback'
                    })
                total_count = res_fb.count or len(reviews)
            except Exception as ex_fb:
                log.warning(f"[list_reviews] app_feedback query note: {ex_fb}")

        # Populate document and user info for document reviews
        doc_ids = list(set([r.get('document_id') for r in reviews if r.get('document_id')]))
        user_ids = list(set([r.get('user_id') for r in reviews if r.get('user_id')]))

        doc_map = {}
        user_map = {}
        if doc_ids:
            try:
                docs = db.table('documents').select('id, title').in_('id', doc_ids).execute().data or []
                doc_map = {d['id']: d.get('title') for d in docs}
            except Exception:
                pass

        if user_ids:
            try:
                users = db.table('profiles').select('id, full_name, email').in_('id', user_ids).execute().data or []
                user_map = {u['id']: u for u in users}
            except Exception:
                pass

        for r in reviews:
            if r.get('document_id'):
                r['document_title'] = doc_map.get(r.get('document_id'), 'Document')
            if r.get('user_id') and r.get('user_id') in user_map:
                u = user_map.get(r.get('user_id'), {})
                r['user_name'] = u.get('full_name') or r.get('user_name') or 'Student'
                r['user_email'] = u.get('email') or r.get('user_email') or ''

        return {
            'success': True,
            'reviews': reviews,
            'total': total_count,
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_reviews] Error: {e}")
        return {'success': False, 'reviews': [], 'total': 0}


def update_review_status(actor_user: dict, review_id: str, status: str, flagged_fake: Optional[bool] = None) -> Tuple[bool, str]:
    """Moderate review status (approved, hidden, rejected) across document reviews and feedback."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {'status': status.strip().lower(), 'updated_at': now_iso}
        if flagged_fake is not None:
            payload['flagged_as_fake'] = bool(flagged_fake)

        updated = False
        try:
            res_doc = db.table('document_reviews').update(payload).eq('id', review_id).execute()
            if res_doc and res_doc.data:
                updated = True
        except Exception:
            pass

        if not updated:
            try:
                db.table('app_feedback').update({'status': status.strip().lower()}).eq('id', review_id).execute()
            except Exception:
                pass

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='update_review_status',
            target_type='review',
            target_id=review_id,
            new_value=payload
        )
        return True, f"Review updated to status '{status}'."
    except Exception as e:
        return False, str(e)


def delete_review(actor_user: dict, review_id: str, reason: str = '') -> Tuple[bool, str]:
    """Permanently delete a review or feedback record."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        try:
            db.table('document_reviews').delete().eq('id', review_id).execute()
        except Exception:
            pass
        try:
            db.table('app_feedback').delete().eq('id', review_id).execute()
        except Exception:
            pass

        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='delete_review',
            target_type='review',
            target_id=review_id,
            reason=reason or 'Administrative review deletion'
        )
        return True, "Review permanently removed."
    except Exception as e:
        return False, str(e)


# ─── Module 9: Support & Reports Service ──────────────────────────────────────

def list_support_tickets(status: Optional[str] = None, priority: Optional[str] = None, page: int = 1, limit: int = 50) -> Dict[str, Any]:
    """Fetch paginated customer support tickets."""
    db = get_db()
    if not db:
        return {'success': False, 'tickets': [], 'total': 0}

    offset = (max(1, page) - 1) * limit
    try:
        q = db.table('support_tickets').select('*', count='exact')
        if status:
            q = q.eq('status', status.strip().lower())
        if priority:
            q = q.eq('priority', priority.strip().lower())

        res = q.order('created_at', desc=True).range(offset, offset + limit - 1).execute()
        tickets = res.data or []

        user_ids = list(set([t.get('user_id') for t in tickets if t.get('user_id')]))
        if user_ids:
            try:
                users = db.table('profiles').select('id, full_name, email').in_('id', user_ids).execute().data or []
                user_map = {u['id']: u for u in users}
                for t in tickets:
                    u = user_map.get(t.get('user_id'), {})
                    t['user_name'] = u.get('full_name') or 'User'
                    t['user_email'] = u.get('email') or ''
            except Exception:
                pass

        return {
            'success': True,
            'tickets': tickets,
            'total': res.count or len(tickets),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_support_tickets] Error: {e}")
        return {'success': False, 'tickets': [], 'total': 0}


def update_ticket_status(actor_user: dict, ticket_id: str, status: str, resolution_notes: str = '') -> Tuple[bool, str]:
    """Update support ticket status and resolution notes."""
    db = get_db()
    if not db:
        return False, "Database unavailable"
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            'status': status.strip().lower(),
            'resolution_notes': resolution_notes.strip() or None,
            'updated_at': now_iso
        }
        if status.strip().lower() in ('resolved', 'closed'):
            payload['resolved_at'] = now_iso
            payload['assigned_to'] = actor_user.get('uid') if validate_uuid(actor_user.get('uid')) else None

        db.table('support_tickets').update(payload).eq('id', ticket_id).execute()
        record_audit_log(
            admin_id=actor_user.get('uid'),
            admin_email=actor_user.get('email', 'admin'),
            action='update_ticket_status',
            target_type='ticket',
            target_id=ticket_id,
            new_value=payload,
            reason=resolution_notes or f"Updated ticket to {status}"
        )
        return True, f"Ticket marked as {status}."
    except Exception as e:
        return False, str(e)


# ─── Module 12: Security & Audit Service ──────────────────────────────────────

def list_audit_logs(
    search: Optional[str] = None,
    action: Optional[str] = None,
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """Fetch paginated immutable audit log events."""
    db = get_db()
    if not db:
        return {'success': False, 'logs': [], 'total': 0}

    offset = (max(1, page) - 1) * limit
    try:
        q = db.table('admin_audit_logs').select('*', count='exact')
        if action:
            q = q.eq('action', action.strip())
        if search:
            s = search.strip()
            q = q.or_(f"admin_email.ilike.%{s}%,target_id.ilike.%{s}%,reason.ilike.%{s}%")

        res = q.order('timestamp', desc=True).range(offset, offset + limit - 1).execute()
        return {
            'success': True,
            'logs': res.data or [],
            'total': res.count or len(res.data or []),
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.error(f"[list_audit_logs] Error: {e}")
        return {'success': False, 'logs': [], 'total': 0}


# ─── Module 13: User Experience Snapshot & Access Diagnostic ─────────────────

def get_user_experience_snapshot(user_id: str) -> Dict[str, Any]:
    """Retrieve full User Experience snapshot: roles, library, uploads, bookmarks, wallet, payments, and view capabilities."""
    db = get_db()
    if not db or not validate_uuid(user_id):
        return {'success': False, 'error': 'Invalid user ID or database unavailable'}

    try:
        # 1. Profile & Role info
        prof_res = db.table('profiles').select(
            'id, full_name, email, role, college_id, department_id, degree, '
            'is_blocked, blocked_reason, blocked_until, is_banned, banned_reason, '
            'paper_quota_remaining, referral_credits, access_level, rank_title, '
            'abhihub_score, reputation_score, created_at'
        ).eq('id', user_id).limit(1).execute()

        if not prof_res.data:
            return {'success': False, 'error': 'User not found'}
        user = prof_res.data[0]

        # College & Department name lookup
        college_name = user.get('degree') or 'General'
        if user.get('college_id') and validate_uuid(user.get('college_id')):
            try:
                col_res = db.table('colleges').select('name').eq('id', user.get('college_id')).limit(1).execute()
                if col_res.data:
                    college_name = col_res.data[0].get('name') or college_name
            except Exception:
                pass

        branch_name = user.get('degree') or 'General'
        if user.get('department_id') and validate_uuid(user.get('department_id')):
            try:
                dept_res = db.table('departments').select('name').eq('id', user.get('department_id')).limit(1).execute()
                if dept_res.data:
                    branch_name = dept_res.data[0].get('name') or branch_name
            except Exception:
                pass

        # 2. Uploads breakdown
        docs_res = db.table('documents').select('id, title, status, created_at, view_count, is_paid, price').eq('uploader_id', user_id).order('created_at', desc=True).execute()
        uploads = docs_res.data or []
        upload_status_counts = {}
        for doc in uploads:
            st = doc.get('status') or 'unknown'
            upload_status_counts[st] = upload_status_counts.get(st, 0) + 1

        # 3. Bookmarks
        bm_res = db.table('bookmarks').select('document_id, created_at, documents(id, title)').eq('user_id', user_id).order('created_at', desc=True).limit(20).execute()
        bookmarks = []
        for b in (bm_res.data or []):
            d_info = b.get('documents') or {}
            bookmarks.append({
                'document_id': b.get('document_id'),
                'title': d_info.get('title') or 'Saved Note',
                'created_at': b.get('created_at')
            })

        # 4. Library (purchased + unlocked notes)
        library = []
        try:
            tx_res = db.table('credit_transactions').select('id, order_id, status, amount, admin_notes, created_at').eq('user_id', user_id).eq('status', 'completed').execute()
            doc_ids_seen = set()
            for tx in (tx_res.data or []):
                notes = tx.get('admin_notes') or ''
                doc_id_match = re.search(r'(?:doc_id=|Document-)([a-f0-9\-]{36})', notes, re.I)
                if doc_id_match:
                    did = doc_id_match.group(1)
                    if did not in doc_ids_seen:
                        doc_ids_seen.add(did)
                        library.append({
                            'document_id': did,
                            'order_id': tx.get('order_id'),
                            'amount': tx.get('amount'),
                            'unlocked_at': tx.get('created_at')
                        })
        except Exception as e:
            log.warning(f"[experience_snapshot] Library fetch note: {e}")

        # 5. Creator Wallet balance
        wallet_balance = 0.0
        pending_balance = 0.0
        try:
            w_res = db.table('creator_wallets').select('withdrawable_balance, pending_balance').eq('user_id', user_id).limit(1).execute()
            if w_res.data:
                wallet_balance = float(w_res.data[0].get('withdrawable_balance') or 0.0)
                pending_balance = float(w_res.data[0].get('pending_balance') or 0.0)
        except Exception:
            pass

        # 6. Pending / Failed payments and Manual UTR status
        payments = []
        try:
            p_res = db.table('credit_transactions').select('id, order_id, utr, status, amount, created_at, admin_notes').eq('user_id', user_id).order('created_at', desc=True).limit(15).execute()
            for p in (p_res.data or []):
                payments.append({
                    'id': p.get('id'),
                    'order_id': p.get('order_id'),
                    'utr': p.get('utr'),
                    'status': p.get('status'),
                    'amount': p.get('amount'),
                    'created_at': p.get('created_at'),
                    'notes': p.get('admin_notes') or ''
                })
        except Exception:
            pass

        # 7. What this user sees (Feature checklist)
        is_banned = bool(user.get('is_banned'))
        is_blocked = bool(user.get('is_blocked'))
        blocked_until = user.get('blocked_until')
        now_iso = datetime.now(timezone.utc).isoformat()
        is_actively_blocked = is_blocked and (not blocked_until or blocked_until > now_iso)
        role = (user.get('role') or 'student').lower()
        quota = int(user.get('paper_quota_remaining') or 0)

        # Ad density calculation
        from methods.scoring_engine import get_ad_decision
        ad_decision = get_ad_decision(user_id=user_id, email=user.get('email'))
        see_ads = bool(ad_decision.get('show_ads', True))
        ad_density = ad_decision.get('density', 'high')

        checklist = {
            'can_preview': not is_banned and not is_actively_blocked,
            'can_download': not is_banned and not is_actively_blocked and (quota > 0 or len(library) > 0 or role in ('admin', 'superadmin')),
            'can_buy': not is_banned and not is_actively_blocked,
            'can_upload': not is_banned and not is_actively_blocked and role != 'banned',
            'see_ads': see_ads,
            'ad_density': ad_density
        }

        return {
            'success': True,
            'user': {
                'id': user_id,
                'name': user.get('full_name') or 'Anonymous',
                'email': user.get('email'),
                'role': role,
                'permissions': ['read', 'download', 'upload'] if not is_banned else ['none'],
                'college': college_name,
                'branch': user.get('branch_name') or '—',
                'semester': user.get('semester') or '—',
                'streak_xp': {
                    'reputation_score': user.get('reputation_score') or 0,
                    'abhihub_score': user.get('abhihub_score') or 0,
                    'rank_title': user.get('rank_title') or 'Beginner',
                    'access_level': user.get('access_level') or 'explorer'
                },
                'blocks': {
                    'is_banned': is_banned,
                    'banned_reason': user.get('banned_reason'),
                    'is_blocked': is_actively_blocked,
                    'blocked_reason': user.get('blocked_reason'),
                    'blocked_until': blocked_until
                },
                'quota_remaining': quota
            },
            'checklist': checklist,
            'library': library,
            'library_count': len(library),
            'uploads_count': len(uploads),
            'upload_status_counts': upload_status_counts,
            'bookmarks_count': len(bookmarks),
            'bookmarks': bookmarks,
            'wallet': {
                'withdrawable_balance': wallet_balance,
                'pending_balance': pending_balance
            },
            'payments': payments
        }
    except Exception as e:
        log.error(f"[get_user_experience_snapshot] {e}")
        return {'success': False, 'error': str(e)}


def diagnose_document_access(user_id: str, document_id: str) -> Dict[str, Any]:
    """Diagnose why a given user can or cannot access note X across all security/permission checks."""
    db = get_db()
    if not db or not validate_uuid(user_id) or not validate_uuid(document_id):
        return {'success': False, 'error': 'Invalid user or document UUID'}

    checks = []
    overall_access = True

    try:
        # Check 1: Document existence & active status
        doc_res = db.table('documents').select('id, title, status, is_paid, price, uploader_id').eq('id', document_id).limit(1).execute()
        if not doc_res.data:
            return {
                'success': True,
                'accessible': False,
                'checks': [{
                    'name': 'Document Exists',
                    'passed': False,
                    'message': 'Document not found in database or invalid document ID.'
                }],
                'summary': 'Document does not exist.'
            }

        doc = doc_res.data[0]
        doc_status = (doc.get('status') or '').lower()
        doc_active = (doc_status == 'approved')
        checks.append({
            'name': 'Document Status Check',
            'passed': doc_active,
            'message': f"Document status is '{doc_status}' (not approved)" if not doc_active else "Document is approved and published."
        })
        if not doc_active:
            overall_access = False

        # Check 2: User Account Standing
        prof_res = db.table('profiles').select('id, role, is_banned, is_blocked, blocked_until, paper_quota_remaining').eq('id', user_id).limit(1).execute()
        if not prof_res.data:
            return {'success': False, 'error': 'User profile not found'}
        user = prof_res.data[0]

        is_banned = bool(user.get('is_banned'))
        is_blocked = bool(user.get('is_blocked'))
        blocked_until = user.get('blocked_until')
        now_iso = datetime.now(timezone.utc).isoformat()
        is_actively_blocked = is_blocked and (not blocked_until or blocked_until > now_iso)
        user_ok = not is_banned and not is_actively_blocked

        checks.append({
            'name': 'User Account Standing',
            'passed': user_ok,
            'message': "Account is suspended or blocked." if not user_ok else "Account is in good standing."
        })
        if not user_ok:
            overall_access = False

        # Check 3: Role Override Check
        role = (user.get('role') or 'student').lower()
        has_role_override = role in ('admin', 'superadmin') or str(doc.get('uploader_id')) == str(user_id)
        checks.append({
            'name': 'Ownership / Role Privileges',
            'passed': True,
            'message': "User is document author or admin (privilege override)." if has_role_override else "Standard student permissions apply."
        })

        # Check 4: Purchase / Unlocked Check
        is_paid = bool(doc.get('is_paid'))
        is_purchased = False
        if is_paid and not has_role_override:
            tx_res = db.table('credit_transactions').select('id').eq('user_id', user_id).eq('status', 'completed').ilike('admin_notes', f"%{document_id}%").limit(1).execute()
            if tx_res.data:
                is_purchased = True

            checks.append({
                'name': 'Paid Document Purchase Verification',
                'passed': is_purchased,
                'message': "Purchased and verified in transaction ledger." if is_purchased else f"Document is premium (₹{doc.get('price', 0)}) and user has not completed a purchase."
            })
            if not is_purchased:
                overall_access = False
        else:
            checks.append({
                'name': 'Pricing / Payment Status',
                'passed': True,
                'message': "Document is Free or user possesses privilege override."
            })

        # Check 5: Quota & Download Availability
        quota = int(user.get('paper_quota_remaining') or 0)
        has_quota = quota > 0 or has_role_override or is_purchased
        checks.append({
            'name': 'Paper Quota Availability',
            'passed': has_quota,
            'message': f"User has {quota} views remaining." if has_quota else "User has 0 paper views remaining and must earn or buy credits."
        })
        if not has_quota:
            overall_access = False

        if not overall_access:
            failed = [c['name'] for c in checks if not c['passed']]
            summary = f"Access denied due to: {', '.join(failed)}."
        else:
            summary = "All checks passed. The user can view and read this document."

        return {
            'success': True,
            'accessible': overall_access,
            'document': {
                'id': doc.get('id'),
                'title': doc.get('title'),
                'is_paid': is_paid,
                'price': doc.get('price', 0),
                'status': doc_status
            },
            'checks': checks,
            'summary': summary
        }
    except Exception as e:
        log.error(f"[diagnose_document_access] {e}")
        return {'success': False, 'error': str(e)}


# ─── Level 2: Read-Only "View as User" & Level 3: Activity Timeline ────────────

def mask_ip_address(ip: Optional[str]) -> str:
    """Partially mask IPv4 or IPv6 addresses to protect user privacy."""
    if not ip or ip in ('127.0.0.1', '::1', 'localhost'):
        return '127.0.0.xxx'
    ip_clean = str(ip).strip()
    if '.' in ip_clean:
        parts = ip_clean.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.{parts[2]}.xxx"
    elif ':' in ip_clean:
        parts = ip_clean.split(':')
        if len(parts) >= 3:
            return f"{parts[0]}:{parts[1]}:{parts[2]}:*:*:*:*"
    return "xxx.xxx.xxx.xxx"


def start_view_as_session(
    admin_user: dict,
    target_user_id: str,
    reason: str,
    ip: Optional[str] = None,
    ua: Optional[str] = None
) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Initiate a time-boxed, read-only View-As session.

    Enforces:
    - Admin or Superadmin role only (Moderators rejected).
    - Valid non-empty justification reason required.
    - Cannot target administrators or superadmins.
    - Cannot target oneself.
    - 30-minute session expiration.
    - Audit log entry recorded on session creation.
    """
    try:
        # Check 1: Role check
        admin_role = (admin_user.get('role') or '').lower().strip()
        if role_rank(admin_role) < role_rank('admin'):
            return False, "Moderator role is not permitted to initiate View-As sessions.", None, None

        # Check 2: Reason validation
        clean_reason = str(reason or '').strip()
        if not clean_reason:
            return False, "A valid operational reason is required to start a View-As session.", None, None

        # Check 3: Self-impersonation check
        admin_uid = str(admin_user.get('uid') or admin_user.get('id') or '')
        if admin_uid and str(target_user_id) == admin_uid:
            return False, "Cannot initiate View-As on yourself.", None, None

        # Check 4: Fetch target user
        client = init_supabase_admin() or init_supabase()
        if not client:
            return False, "Database connection unavailable.", None, None

        res = client.table('profiles').select('*').eq('id', target_user_id).limit(1).execute()
        if not res.data:
            return False, "Target user profile not found.", None, None

        target_profile = res.data[0]
        target_role = (target_profile.get('role') or target_profile.get('access_level') or 'student').lower().strip()
        if role_rank(target_role) >= role_rank('admin') or target_role in ('admin', 'superadmin'):
            return False, "Cannot impersonate administrators or superadmins.", None, None

        target_name = (
            target_profile.get('student_name')
            or target_profile.get('name')
            or target_profile.get('email', 'User')
        )

        now = datetime.now(timezone.utc)
        expires = now + timedelta(minutes=30)
        view_as_data = {
            'user_id': str(target_user_id),
            'user_name': target_name,
            'admin_id': admin_uid,
            'admin_email': admin_user.get('email', 'admin'),
            'started_at': now.isoformat(),
            'expires_at': expires.isoformat(),
            'reason': clean_reason,
            'pages_visited': []
        }

        # Mask sensitive user data before setting into session user
        sanitized_user = {
            'uid': str(target_user_id),
            'id': str(target_user_id),
            'email': target_profile.get('email', ''),
            'name': target_name,
            'student_name': target_name,
            'role': target_role,
            'college_id': target_profile.get('college_id'),
            'department_id': target_profile.get('department_id'),
            'degree': target_profile.get('degree'),
            'paper_quota_remaining': target_profile.get('paper_quota_remaining', 0),
            'is_view_as': True
        }

        # Write audit log
        record_audit_log(
            admin_id=admin_uid,
            admin_email=admin_user.get('email', 'admin'),
            action='view_as_start',
            target_type='user',
            target_id=str(target_user_id),
            old_value=None,
            new_value={'target_name': target_name, 'expires_at': expires.isoformat()},
            reason=clean_reason,
            ip_address=ip,
            user_agent=ua
        )

        return True, "View-As session initiated successfully.", view_as_data, sanitized_user
    except Exception as e:
        log.error(f"[start_view_as_session] Error: {e}")
        return False, f"Failed to initiate View-As session: {str(e)}", None, None


def stop_view_as_session(
    admin_user: dict,
    target_user_id: str,
    pages_visited: Optional[List[str]] = None,
    ip: Optional[str] = None,
    ua: Optional[str] = None
) -> Tuple[bool, str]:
    """Conclude a View-As session and write audit log of visited pages."""
    try:
        admin_uid = str(admin_user.get('uid') or admin_user.get('id') or '')
        record_audit_log(
            admin_id=admin_uid,
            admin_email=admin_user.get('email', 'admin'),
            action='view_as_stop',
            target_type='user',
            target_id=str(target_user_id),
            old_value=None,
            new_value={'pages_visited': pages_visited or []},
            reason="Admin ended View-As session",
            ip_address=ip,
            user_agent=ua
        )
        return True, "View-As session concluded successfully."
    except Exception as e:
        log.error(f"[stop_view_as_session] Error: {e}")
        return False, str(e)


def log_user_activity(
    user_id: str,
    event_type: str,
    entity_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    device: Optional[str] = None
) -> bool:
    """Log user activity with partial IP masking and metadata sanitation."""
    try:
        if not user_id or not event_type:
            return False

        # Sanitize metadata to avoid storing credentials or personal communications
        clean_meta = {}
        if isinstance(metadata, dict):
            sensitive_keys = {'password', 'hash', 'token', 'secret', 'authorization', 'cookie', 'session', 'pan', 'upi', 'bank', 'message'}
            for k, v in metadata.items():
                if any(s in str(k).lower() for s in sensitive_keys):
                    continue
                if isinstance(v, str):
                    clean_meta[k] = v[:200]
                elif isinstance(v, (int, float, bool)):
                    clean_meta[k] = v

        masked_ip = mask_ip_address(ip)
        clean_device = str(device or 'unknown')[:120]

        entry = {
            'user_id': str(user_id),
            'event_type': str(event_type)[:64],
            'entity_id': str(entity_id)[:128] if entity_id else None,
            'metadata': clean_meta,
            'device': clean_device,
            'ip': masked_ip,
            'created_at': datetime.now(timezone.utc).isoformat()
        }

        client = init_supabase_admin() or init_supabase()
        if client:
            client.table('user_activity_events').insert(entry).execute()
            return True
    except Exception as e:
        log.debug(f"[log_user_activity] Ignored: {e}")
    return False


def get_user_activity_timeline(
    user_id: str,
    event_type: Optional[str] = None,
    page: int = 1,
    limit: int = 12
) -> Dict[str, Any]:
    """Fetch paginated activity timeline and device summary for a user across all activity channels."""
    try:
        client = init_supabase_admin() or init_supabase()
        if not client:
            return {'success': True, 'events': [], 'device_summary': {}, 'total': 0, 'page': page}

        events = []

        # 1. Telemetry & Direct Activity Events (if table exists)
        try:
            query = client.table('user_activity_events').select('*').eq('user_id', user_id)
            if event_type:
                query = query.eq('event_type', event_type)
            res = query.order('created_at', desc=True).limit(limit * 3).execute()
            for ev in (res.data or []):
                events.append({
                    'id': ev.get('id'),
                    'event_type': ev.get('event_type'),
                    'action': (ev.get('event_type') or 'Activity').replace('_', ' ').title(),
                    'entity_id': ev.get('entity_id') or '—',
                    'device': ev.get('device') or 'Desktop',
                    'ip': ev.get('ip') or '—',
                    'metadata': ev.get('metadata') or {},
                    'created_at': ev.get('created_at')
                })
        except Exception:
            pass

        # 2. Document Views (Resource access)
        if not event_type or event_type in ('document_view', 'view'):
            try:
                v_res = client.table('document_views').select(
                    'id, document_id, accessed_at, ip_address, device_type, documents(title, document_category, subjects(name, subject_code))'
                ).eq('user_id', user_id).order('accessed_at', desc=True).limit(50).execute()
                for v in (v_res.data or []):
                    doc = v.get('documents') or {}
                    d_title = doc.get('title') or v.get('document_id')
                    d_cat = (doc.get('document_category') or 'document').upper()
                    subj = (doc.get('subjects') or {}).get('name') if isinstance(doc.get('subjects'), dict) else ''
                    events.append({
                        'id': v.get('id'),
                        'event_type': 'document_view',
                        'action': f"Viewed {d_cat}: {subj or d_title}",
                        'entity_id': d_title,
                        'device': v.get('device_type') or 'Desktop Browser',
                        'ip': v.get('ip_address') or '—',
                        'metadata': {'document_id': v.get('document_id'), 'title': d_title, 'category': d_cat, 'subject': subj},
                        'created_at': v.get('accessed_at')
                    })
            except Exception as e:
                log.warning(f"[Timeline] Views error: {e}")

        # 3. Document Uploads
        if not event_type or event_type in ('upload', 'document_upload'):
            try:
                u_res = client.table('documents').select(
                    'id, title, document_category, created_at, status, price'
                ).eq('uploader_id', user_id).order('created_at', desc=True).limit(50).execute()
                for u in (u_res.data or []):
                    events.append({
                        'id': u.get('id'),
                        'event_type': 'document_upload',
                        'action': f"Uploaded {u.get('document_category') or 'file'}: {u.get('title')}",
                        'entity_id': u.get('title'),
                        'device': 'Web Portal',
                        'ip': '—',
                        'metadata': {'status': u.get('status'), 'price': u.get('price')},
                        'created_at': u.get('created_at')
                    })
            except Exception as e:
                log.warning(f"[Timeline] Uploads error: {e}")

        # 4. Credit & Payment Transactions
        if not event_type or event_type in ('transaction', 'payment'):
            try:
                t_res = client.table('credit_transactions').select(
                    'id, amount, status, created_at, order_id, utr'
                ).eq('user_id', user_id).order('created_at', desc=True).limit(50).execute()
                for t in (t_res.data or []):
                    events.append({
                        'id': t.get('id'),
                        'event_type': 'payment',
                        'action': f"Payment/Credit: ₹{t.get('amount')} [{t.get('status')}]",
                        'entity_id': t.get('order_id') or 'Order',
                        'device': 'Payment Gateway',
                        'ip': '—',
                        'metadata': {'amount': t.get('amount'), 'status': t.get('status'), 'utr': t.get('utr')},
                        'created_at': t.get('created_at')
                    })
            except Exception as e:
                log.warning(f"[Timeline] Transactions error: {e}")

        # 5. Account Registration & Onboarding
        if not event_type or event_type in ('login', 'account_created'):
            try:
                p_res = client.table('profiles').select('created_at, email, full_name, role, last_active_at').eq('id', user_id).limit(1).execute()
                if p_res.data:
                    p = p_res.data[0]
                    if p.get('created_at'):
                        events.append({
                            'id': f"reg-{user_id}",
                            'event_type': 'account_created',
                            'action': f"Registered Account ({p.get('role', 'student')})",
                            'entity_id': p.get('email') or 'User Account',
                            'device': 'Web',
                            'ip': '—',
                            'metadata': {'email': p.get('email'), 'role': p.get('role'), 'name': p.get('full_name')},
                            'created_at': p.get('created_at')
                        })
            except Exception as e:
                log.warning(f"[Timeline] Registration error: {e}")

        # 6. Incomplete / Abandoned Actions from security_audit_logs
        if not event_type or event_type in ('abandoned', 'incomplete', 'drop_off'):
            try:
                ab_res = client.table('security_audit_logs').select(
                    'id, event, metadata, detected_at'
                ).eq('user_id', user_id).order('detected_at', desc=True).limit(30).execute()
                for r in (ab_res.data or []):
                    meta = r.get('metadata') or {}
                    action = meta.get('action')
                    if meta.get('category') == 'feature_usage' and action in ('abandoned', 'drop_off', 'incomplete'):
                        feat = str(meta.get('feature') or 'Feature').replace('_', ' ').title()
                        step = meta.get('step') or 'Initiated but discarded'
                        reason = meta.get('reason') or 'Left before completion'
                        events.append({
                            'id': r.get('id'),
                            'event_type': 'abandoned',
                            'action': f"⚠️ Abandoned {feat}: {step}",
                            'entity_id': feat,
                            'device': 'Web',
                            'ip': '—',
                            'metadata': {'feature': feat, 'step': step, 'reason': reason},
                            'created_at': r.get('detected_at')
                        })
            except Exception as e:
                log.warning(f"[Timeline] Abandoned logs note: {e}")

        # Sort all chronologically descending
        events.sort(key=lambda x: str(x.get('created_at') or ''), reverse=True)
        total = len(events)
        offset = (page - 1) * limit
        paginated_events = events[offset:offset + limit]

        device_summary = {}
        for ev in events:
            dev = ev.get('device') or 'Unknown'
            device_summary[dev] = device_summary.get(dev, 0) + 1

        return {
            'success': True,
            'events': paginated_events,
            'device_summary': device_summary,
            'total': total,
            'page': page,
            'limit': limit
        }
    except Exception as e:
        log.warning(f"[get_user_activity_timeline] Error: {e}")
        return {'success': True, 'events': [], 'device_summary': {}, 'total': 0, 'page': page, 'error': str(e)}


def purge_old_user_activity_events(days: int = 90) -> int:
    """Purge user activity records older than retention threshold (default 90 days)."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        client = init_supabase_admin() or init_supabase()
        if not client:
            return 0
        res = client.table('user_activity_events').delete().lt('created_at', cutoff).execute()
        count = len(res.data) if res and res.data else 0
        log.info(f"[purge_old_user_activity_events] Purged {count} events older than {days} days.")
        return count
    except Exception as e:
        log.warning(f"[purge_old_user_activity_events] Purge error: {e}")
        return 0

