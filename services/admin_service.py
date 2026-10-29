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
    limit: int = 50
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
    limit: int = 50
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
            'blocked_until': blocked_until,
            'updated_at': now_iso
        }
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
            'updated_at': now_iso
        }
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
    limit: int = 50
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
    """Read global site settings."""
    db = get_db()
    settings = dict(DEFAULT_SETTINGS)
    if db:
        try:
            res = db.table('admin_site_settings').select('*').execute()
            for row in (res.data or []):
                settings[row['key']] = row.get('value')
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
