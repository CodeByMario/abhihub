import os
import logging
from functools import wraps
from datetime import datetime, timezone
from flask import (
    Blueprint, session, request, redirect, url_for, jsonify, abort,
    render_template, make_response, current_app
)

auth_bp = Blueprint('auth', __name__)

ADMIN_EMAILS = [
    e.strip().lower()
    for e in (os.getenv('ADMIN_EMAILS') or os.getenv('ADMIN_EMAIL') or '').split(',')
    if e.strip()
]


def is_safe_redirect_url(target):
    """Ensure redirect targets are relative same-site paths to prevent Open Redirect vulnerabilities."""
    if not target or not isinstance(target, str):
        return False
    return target.startswith('/') and not target.startswith('//') and '\\' not in target and '://' not in target


def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            if request.path.startswith('/api/') or request.path.startswith('/store-room/api/'):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def is_admin_user(user: dict) -> bool:
    """Check if session user has administrative privileges."""
    if not user or not isinstance(user, dict):
        return False
    user_email = (user.get('email') or '').lower().strip()
    user_role = (user.get('role') or '').lower().strip()
    if user_role == 'admin' or bool(user.get('is_admin')):
        return True
    active_admin_emails = ADMIN_EMAILS or ['abhihub.02@gmail.com']
    return bool(user_email and user_email in active_admin_emails)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = session.get('user')
        if not user:
            if request.path.startswith('/api/') or request.path.startswith('/store-room/api/'):
                return jsonify({'success': False, 'message': 'Unauthorized'}), 401
            return redirect(url_for('auth.login'))

        if not is_admin_user(user):
            if request.path.startswith('/api/') or request.path.startswith('/store-room/api/'):
                return jsonify({'success': False, 'message': 'Forbidden: Admin access required'}), 403
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def log_admin_action(action: str, target: str = None, details: dict = None):
    """Structured audit logging for all administrative modifications."""
    try:
        user = session.get('user', {})
        admin_email = user.get('email', 'unknown')
        admin_id = user.get('uid') or user.get('id', 'unknown')
        client_ip = request.headers.get('X-Forwarded-For', request.remote_addr or '').split(',')[0].strip()
        timestamp = datetime.now(timezone.utc).isoformat()
        entry = {
            'timestamp': timestamp,
            'admin_id': admin_id,
            'admin_email': admin_email,
            'action': action,
            'target': target,
            'ip': client_ip,
            'details': details or {}
        }
        logging.info(f"[ADMIN_AUDIT] {entry}")
    except Exception as e:
        logging.warning(f"Failed to record admin audit log: {e}")


@auth_bp.route('/auth-callback')
def auth_callback():
    """Handle OAuth callback from Supabase"""
    try:
        next_url = request.args.get('next', '')
        dest = next_url if is_safe_redirect_url(next_url) else url_for('app_pages.app_shell')
        if 'user' in session:
            return redirect(dest)
        else:
            return render_template('site/login.html')
    except Exception as e:
        logging.debug(f"Auth callback failed: {e}")
        return redirect(url_for('auth.login'))


@auth_bp.route('/login')
def login():
    if 'user' in session:
        next_url = request.args.get('next', '')
        dest = next_url if is_safe_redirect_url(next_url) else url_for('app_pages.app_shell')
        return redirect(dest)
    else:
        return render_template('site/login.html')


@auth_bp.route('/signup')
def signup():
    if 'user' in session:
        return redirect(url_for('app_pages.app_shell'))
    else:
        return render_template('site/signup.html')


@auth_bp.route('/register')
def register():
    """Register page (alias for signup)"""
    return redirect(url_for('auth.signup'))


@auth_bp.route('/reset-password')
def reset_password():
    if 'user' in session:
        return redirect(url_for('app_pages.app_shell'))
    else:
        return render_template('forgot_password.html')


@auth_bp.route('/reset-password-confirm')
def reset_password_confirm():
    """Handle password reset confirmation from Supabase email link"""
    try:
        return render_template('reset_password_form.html')
    except Exception as e:
        logging.debug(f"Password reset confirm failed: {e}")
        return redirect(url_for('auth.reset_password'))


@auth_bp.route('/logout', methods=['GET', 'POST'])
def logout():
    session_id = session.get('session_id')
    if session_id:
        try:
            from data.profiles import UserSession
            UserSession.log_logout(session_id)
        except Exception as e:
            logging.warning(f"Failed to log session logout: {e}")
    session.clear()
    response = make_response(render_template('logout_clear.html'))
    response.set_cookie(current_app.config.get('SESSION_COOKIE_NAME', 'session'), '', expires=0, path='/')
    return response
