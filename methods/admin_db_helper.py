"""
methods/admin_db_helper.py
Compatibility facade exporting admin database operations and services.
"""

from services.admin_service import (
    get_db,
    get_user_role,
    has_min_role,
    check_anti_lockout,
    record_audit_log,
    get_audit_logs,
    list_users,
    get_user_detail,
    set_user_role,
    set_user_block,
    set_user_ban,
    set_user_account_status,
    soft_delete_user,
    restore_user,
    hard_delete_user,
    list_files,
    delete_file_completely,
    bulk_delete_files,
    flag_quarantine_file,
    get_site_settings,
    update_site_setting,
    get_platform_dashboard_kpis
)

__all__ = [
    'get_db',
    'get_user_role',
    'has_min_role',
    'check_anti_lockout',
    'record_audit_log',
    'get_audit_logs',
    'list_users',
    'get_user_detail',
    'set_user_role',
    'set_user_block',
    'set_user_ban',
    'set_user_account_status',
    'soft_delete_user',
    'restore_user',
    'hard_delete_user',
    'list_files',
    'delete_file_completely',
    'bulk_delete_files',
    'flag_quarantine_file',
    'get_site_settings',
    'update_site_setting',
    'get_platform_dashboard_kpis'
]
