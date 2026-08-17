"""
Server-side Google Analytics 4 tracking for AbhiHub.
Provides endpoints for pageview logging, user profile sync, error tracking, and file access tracking.
Also logs to Supabase for backup/analytics.

Measurement ID: G-EH5BGS9BEG
"""

import logging
import time
from datetime import datetime
from flask import request, jsonify, session

# GA4 Measurement ID
GA4_MEASUREMENT_ID = "G-EH5BGS9BEG"

# ============================================================================
# Helper: Build user profile data from session + Supabase
# ============================================================================

def get_user_profile_data():
    """
    Collect comprehensive user profile data for GA4 user_properties.
    Returns dict with: uid, email, name, mobile, branch, college, year_of_study, role
    """
    user = session.get('user', {})
    user_id = user.get('uid', '')
    email = user.get('email', '')
    name = user.get('name', '')
    
    profile = {
        'uid': user_id,
        'email': email,
        'name': name,
        'mobile': '',
        'branch': '',
        'college': '',
        'year_of_study': '',
        'role': 'anonymous',
        'isAuthenticated': False
    }
    
    if not user_id:
        return profile
    
    profile['isAuthenticated'] = True
    profile['role'] = user.get('provider', 'email')
    
    # Fetch extended profile from Supabase
    try:
        from methods.supabase_helper import get_student_profile
        result = get_student_profile(user_id)
        if result.get('success') and result.get('data'):
            data = result['data']
            profile['college'] = data.get('college_name', '')
            profile['branch'] = data.get('branch_name', '')
            profile['year_of_study'] = data.get('pursuing_year', '')
            profile['mobile'] = data.get('mobile_number', '') or data.get('student_moblie_number', '')
    except Exception as e:
        logging.warning(f"[Analytics] Failed to fetch student profile: {e}")
    
    # Fallback: try profiles table directly
    if not profile['college'] or not profile['branch']:
        try:
            from data.profiles import Profile
            p = Profile.get_by_id(user_id)
            if p:
                if not profile['college'] and p.get('college_id'):
                    from methods.supabase_helper import get_college_by_id
                    col = get_college_by_id(p['college_id'])
                    if col.get('success'):
                        profile['college'] = col['data'].get('name', '')
                if not profile['branch'] and p.get('department_id'):
                    from methods.supabase_helper import get_department_by_id
                    dept = get_department_by_id(p['department_id'])
                    if dept.get('success'):
                        profile['branch'] = dept['data'].get('name', '')
        except Exception as e:
            logging.warning(f"[Analytics] Fallback profile fetch failed: {e}")
    
    return profile


def get_full_profile_json():
    """
    Return the full user profile as a JSON-safe dict for embedding in templates.
    """
    profile = get_user_profile_data()
    return {
        'userId': profile['uid'] or 'anonymous',
        'email': profile['email'] or '',
        'name': profile['name'] or '',
        'mobile': profile['mobile'] or '',
        'branch': profile['branch'] or '',
        'college': profile['college'] or '',
        'yearOfStudy': profile['year_of_study'] or '',
        'role': profile['role'] or 'anonymous',
        'isAuthenticated': profile['isAuthenticated']
    }


# ============================================================================
# API Endpoints
# ============================================================================

def register_analytics_routes(app):
    """Register all analytics-related routes on the Flask app.
    
    Rate limits: 100 requests per minute per IP for all analytics endpoints
    to prevent abuse while allowing legitimate traffic.
    """
    
    # Simple in-memory rate limiting (adequate for single-instance deployment)
    # For multi-instance, use Redis-backed rate limiting
    _analytics_rate_limit = {}
    _RATE_LIMIT_MAX = 100  # requests per window
    _RATE_LIMIT_WINDOW = 60  # seconds
    
    def _check_rate_limit(ip_address):
        """Return True if request is allowed, False if rate limited."""
        now = time.time()
        if ip_address not in _analytics_rate_limit:
            _analytics_rate_limit[ip_address] = []
        
        # Clean old entries
        _analytics_rate_limit[ip_address] = [
            t for t in _analytics_rate_limit[ip_address] 
            if now - t < _RATE_LIMIT_WINDOW
        ]
        
        if len(_analytics_rate_limit[ip_address]) >= _RATE_LIMIT_MAX:
            return False
        
        _analytics_rate_limit[ip_address].append(now)
        return True
    
    def _validate_input(value, field_name, max_length=255, allow_empty=True):
        """Validate and sanitize input strings."""
        if value is None:
            if allow_empty:
                return ''
            return None
        
        if not isinstance(value, str):
            try:
                value = str(value)
            except Exception:
                return None
        
        # Truncate to max length
        if len(value) > max_length:
            value = value[:max_length]
        
        return value
    
    @app.route('/api/analytics/pageview', methods=['POST'])
    def analytics_pageview():
        """Server-side pageview logging with rate limiting."""
        # Rate limit check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not _check_rate_limit(ip):
            logging.warning(f"[Analytics] Rate limited: {ip}")
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        try:
            data = request.get_json(silent=True) or {}
            user = session.get('user', {})
            user_id = user.get('uid', '')
            user_email = user.get('email', '')
            
            page_data = {
                'page_path': _validate_input(data.get('page_path', request.path), 'page_path', 500),
                'page_title': _validate_input(data.get('page_title', request.url), 'page_title', 500),
                'page_location': _validate_input(data.get('page_location', request.url), 'page_location', 500),
                'page_category': _validate_input(data.get('page_category', 'general'), 'page_category', 100),
                'referrer': _validate_input(data.get('referrer', request.referrer or ''), 'referrer', 500),
                'session_id': _validate_input(data.get('session_id', ''), 'session_id', 200),
                'user_id': user_id,
                'user_email': user_email,
                'ip_address': request.headers.get('X-Forwarded-For', request.remote_addr),
                'user_agent': request.headers.get('User-Agent', ''),
                'device_type': _detect_device(request.headers.get('User-Agent', '')),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Log to Supabase for backup analytics
            _log_pageview_to_supabase(page_data)
            
            return jsonify({'success': True, 'message': 'Pageview logged'}), 200
        except Exception as e:
            logging.error(f"[Analytics] Pageview error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/analytics/user-properties', methods=['GET'])
    def analytics_user_properties():
        """Returns the current user's profile data as JSON with rate limiting."""
        # Rate limit check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not _check_rate_limit(ip):
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        try:
            profile = get_full_profile_json()
            return jsonify({
                'success': True,
                'userProperties': profile
            }), 200
        except Exception as e:
            logging.error(f"[Analytics] User properties error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/analytics/error', methods=['POST'])
    def analytics_error():
        """Server-side error tracking with rate limiting."""
        # Rate limit check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not _check_rate_limit(ip):
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        try:
            data = request.get_json(silent=True) or {}
            user = session.get('user', {})
            
            error_data = {
                'error_type': _validate_input(data.get('error_type', 'unknown'), 'error_type', 100),
                'error_message': _validate_input(data.get('error_message', ''), 'error_message', 2000),
                'severity': _validate_input(data.get('severity', 'warning'), 'severity', 50),
                'page_path': _validate_input(data.get('page_path', request.path), 'page_path', 500),
                'user_id': user.get('uid', ''),
                'user_email': user.get('email', ''),
                'ip_address': request.headers.get('X-Forwarded-For', request.remote_addr),
                'user_agent': request.headers.get('User-Agent', ''),
                'stack_trace': _validate_input(data.get('stack_trace', ''), 'stack_trace', 5000),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Log to Supabase
            _log_error_to_supabase(error_data)
            
            # Also log to Flask logger for server-side visibility
            severity = error_data['severity']
            if severity == 'critical':
                logging.error(f"[GA4 Error] {error_data['error_type']}: {error_data['error_message']}")
            elif severity == 'error':
                logging.error(f"[GA4 Error] {error_data['error_type']}: {error_data['error_message']}")
            else:
                logging.warning(f"[GA4 Error] {error_data['error_type']}: {error_data['error_message']}")
            
            return jsonify({'success': True, 'message': 'Error logged'}), 200
        except Exception as e:
            logging.error(f"[Analytics] Error logging failed: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/analytics/file-access', methods=['POST'])
    def analytics_file_access():
        """Track file access with duration, with rate limiting."""
        # Rate limit check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not _check_rate_limit(ip):
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        try:
            data = request.get_json(silent=True) or {}
            user = session.get('user', {})
            
            file_data = {
                'document_id': _validate_input(data.get('document_id', ''), 'document_id', 100),
                'file_name': _validate_input(data.get('file_name', ''), 'file_name', 500),
                'file_type': _validate_input(data.get('file_type', ''), 'file_type', 50),
                'subject': _validate_input(data.get('subject', ''), 'subject', 500),
                'college': _validate_input(data.get('college', ''), 'college', 500),
                'branch': _validate_input(data.get('branch', ''), 'branch', 500),
                'year': _validate_input(data.get('year', ''), 'year', 50),
                'user_id': user.get('uid', ''),
                'user_email': user.get('email', ''),
                'ip_address': request.headers.get('X-Forwarded-For', request.remote_addr),
                'user_agent': request.headers.get('User-Agent', ''),
                'device_type': _detect_device(request.headers.get('User-Agent', '')),
                'time_spent_seconds': min(max(int(data.get('time_spent_seconds', 0)), 0), 86400),  # 0-24h
                'action': _validate_input(data.get('action', 'view'), 'action', 50),
                'session_id': _validate_input(data.get('session_id', ''), 'session_id', 200),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Log to Supabase
            _log_file_access_to_supabase(file_data)
            
            return jsonify({'success': True, 'message': 'File access logged'}), 200
        except Exception as e:
            logging.error(f"[Analytics] File access error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500
    
    @app.route('/api/analytics/session-end', methods=['POST'])
    def analytics_session_end():
        """Track session end with total duration, with rate limiting."""
        # Rate limit check
        ip = request.headers.get('X-Forwarded-For', request.remote_addr)
        if not _check_rate_limit(ip):
            return jsonify({'success': False, 'message': 'Rate limited'}), 429
        
        try:
            data = request.get_json(silent=True) or {}
            user = session.get('user', {})
            
            session_data = {
                'user_id': user.get('uid', ''),
                'user_email': user.get('email', ''),
                'session_id': _validate_input(data.get('session_id', ''), 'session_id', 200),
                'session_duration_seconds': min(max(int(data.get('session_duration_seconds', 0)), 0), 86400),
                'page_views': min(max(int(data.get('page_views', 0)), 0), 10000),
                'file_views': min(max(int(data.get('file_views', 0)), 0), 10000),
                'downloads': min(max(int(data.get('downloads', 0)), 0), 10000),
                'searches': min(max(int(data.get('searches', 0)), 0), 10000),
                'engagement_quality': _validate_input(data.get('engagement_quality', 'unknown'), 'engagement_quality', 50),
                'exit_page': _validate_input(data.get('exit_page', request.path), 'exit_page', 500),
                'timestamp': datetime.utcnow().isoformat() + 'Z'
            }
            
            # Log to Supabase
            _log_session_to_supabase(session_data)
            
            return jsonify({'success': True, 'message': 'Session ended'}), 200
        except Exception as e:
            logging.error(f"[Analytics] Session end error: {e}")
            return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# Supabase Logging Helpers
# ============================================================================

def _log_pageview_to_supabase(data):
    """Log pageview to Supabase document_views table."""
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if not client:
            return
        
        client.table('document_views').insert({
            'document_id': data.get('page_path', ''),
            'user_id': data.get('user_id', ''),
            'ip_address': data.get('ip_address', ''),
            'device_type': data.get('device_type', ''),
            'view_type': 'pageview',
            'metadata': {
                'page_title': data.get('page_title', ''),
                'page_category': data.get('page_category', ''),
                'referrer': data.get('referrer', ''),
                'session_id': data.get('session_id', ''),
            }
        }).execute()
    except Exception as e:
        logging.warning(f"[Analytics] Supabase pageview log failed: {e}")


def _log_error_to_supabase(data):
    """Log error to Supabase security_audit_logs table."""
    try:
        from methods.supabase_helper import log_security_audit_event
        log_security_audit_event(
            user_email=data.get('user_email', ''),
            event_type=f"analytics_error_{data.get('error_type', 'unknown')}",
            ip_address=data.get('ip_address', ''),
            user_agent=data.get('user_agent', ''),
            metadata={
                'error_message': data.get('error_message', ''),
                'severity': data.get('severity', 'warning'),
                'page_path': data.get('page_path', ''),
                'stack_trace': data.get('stack_trace', ''),
            }
        )
    except Exception as e:
        logging.warning(f"[Analytics] Supabase error log failed: {e}")


def _log_file_access_to_supabase(data):
    """Log file access to Supabase."""
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if not client:
            return
        
        client.table('document_views').insert({
            'document_id': data.get('document_id', ''),
            'user_id': data.get('user_id', ''),
            'ip_address': data.get('ip_address', ''),
            'device_type': data.get('device_type', ''),
            'view_type': data.get('action', 'view'),
            'time_spent_seconds': data.get('time_spent_seconds', 0),
            'metadata': {
                'file_name': data.get('file_name', ''),
                'file_type': data.get('file_type', ''),
                'subject': data.get('subject', ''),
                'college': data.get('college', ''),
                'branch': data.get('branch', ''),
                'year': data.get('year', ''),
                'session_id': data.get('session_id', ''),
            }
        }).execute()
    except Exception as e:
        logging.warning(f"[Analytics] Supabase file access log failed: {e}")


def _log_session_to_supabase(data):
    """Log session end to Supabase."""
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if not client:
            return
        
        client.table('user_sessions').insert({
            'user_id': data.get('user_id', ''),
            'ip_address': '',
            'user_agent': '',
            'device_type': '',
            'session_data': data,
            'duration_minutes': round(data.get('session_duration_seconds', 0) / 60, 2),
        }).execute()
    except Exception as e:
        logging.warning(f"[Analytics] Supabase session log failed: {e}")


def _detect_device(user_agent):
    """Detect device type from user agent string."""
    ua = (user_agent or '').lower()
    if 'mobile' in ua or 'android' in ua or 'iphone' in ua or 'ipod' in ua:
        return 'mobile'
    if 'tablet' in ua or 'ipad' in ua:
        return 'tablet'
    return 'desktop'
