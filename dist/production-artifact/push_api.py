# Push Notification & Preferences API Routes
# Blueprint registered in app.py via init_push_api(app)

import os
import time
import logging
from flask import Blueprint, jsonify, request, session
from methods.supabase_helper import init_supabase, validate_uuid

push_api = Blueprint('push_api', __name__)

ADMIN_EMAILS = [e.strip().lower() for e in (os.getenv('ADMIN_EMAILS') or os.getenv('ADMIN_EMAIL') or '').split(',') if e.strip()]


def get_vapid_key():
    """Get VAPID public key from environment."""
    from dotenv import load_dotenv
    load_dotenv()
    return os.environ.get('VAPID_PUBLIC_KEY', '')


@push_api.route('/api/push/vapid-public-key')
def vapid_public_key():
    """Return VAPID public key for push subscriptions."""
    key = get_vapid_key()
    if not key:
        return jsonify({'error': 'VAPID key not configured'}), 503
    return jsonify({'publicKey': key})


@push_api.route('/api/push/subscribe', methods=['POST'])
def subscribe():
    """Subscribe current authenticated user to push notifications."""
    try:
        user = session.get('user', {})
        user_id = user.get('uid') or user.get('id')
        user_email = user.get('email')

        if not user_id and not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        from push_notifications import add_subscription
        data = request.get_json() or {}
        subscription = data.get('subscription')
        device_type = data.get('device_type')
        platform = data.get('platform')
        browser = data.get('browser')
        permission_state = data.get('permission_state', 'granted')

        if not subscription or not isinstance(subscription, dict):
            return jsonify({'error': 'Invalid subscription payload'}), 400

        # Auto-detect device/platform if not provided
        if not device_type or not platform:
            ua = (request.headers.get('User-Agent') or '').lower()
            if any(m in ua for m in ['iphone', 'ipad', 'ipod']):
                platform = platform or 'ios'
                device_type = device_type or ('tablet' if 'ipad' in ua else 'mobile')
            elif 'android' in ua:
                platform = platform or 'android'
                device_type = device_type or 'mobile'
            elif 'macintosh' in ua or 'mac os' in ua:
                platform = platform or 'macos'
                device_type = device_type or 'desktop'
            elif 'windows' in ua:
                platform = platform or 'windows'
                device_type = device_type or 'desktop'
            else:
                platform = platform or 'unknown'
                device_type = device_type or 'desktop'

        target_identifier = user_id or user_email
        success = add_subscription(
            target_identifier,
            subscription,
            device_type=device_type,
            platform=platform,
            browser=browser,
            permission_state=permission_state
        )

        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to save subscription'}), 500

    except Exception as e:
        logging.error(f"[PUSH_API] subscribe error: {e}")
        return jsonify({'error': str(e)}), 500


@push_api.route('/api/push/unsubscribe', methods=['POST', 'DELETE'])
def unsubscribe():
    """Unsubscribe a device from push notifications."""
    try:
        user = session.get('user', {})
        user_id = user.get('uid') or user.get('id')
        user_email = user.get('email')

        if not user_id and not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        from push_notifications import remove_subscription, remove_subscription_by_endpoint

        data = request.get_json() or {}
        endpoint = data.get('endpoint')

        if endpoint:
            success = remove_subscription_by_endpoint(endpoint)
        else:
            success = remove_subscription(user_id or user_email)

        return jsonify({'success': success})
    except Exception as e:
        logging.error(f"[PUSH_API] unsubscribe error: {e}")
        return jsonify({'error': str(e)}), 500


@push_api.route('/api/push/status')
def status():
    """Get subscription status for current authenticated user."""
    try:
        user = session.get('user', {})
        user_id = user.get('uid') or user.get('id')
        user_email = user.get('email')

        if not user_id and not user_email:
            return jsonify({'enabled': False, 'subscribed': False, 'authenticated': False})

        from push_notifications import is_user_subscribed
        client = init_supabase()

        uuid = user_id
        if not uuid and user_email and client:
            p_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if p_res.data:
                uuid = p_res.data[0]['id']

        subscribed = is_user_subscribed(uuid) if uuid else False
        return jsonify({'enabled': True, 'subscribed': subscribed, 'authenticated': True})
    except Exception as e:
        logging.error(f"[PUSH_API] status error: {e}")
        return jsonify({'enabled': False, 'subscribed': False, 'authenticated': False})


@push_api.route('/api/push/send', methods=['POST'])
def send():
    """
    Send broadcast push notification to all subscribers.
    Restricted strictly to authenticated admins.
    """
    try:
        user = session.get('user', {})
        user_email = (user.get('email') or '').lower()

        # Check Admin authorization
        if not user_email or (ADMIN_EMAILS and user_email not in ADMIN_EMAILS):
            return jsonify({'error': 'Unauthorized: Admin privileges required'}), 403

        from push_notifications import send_notification_to_all
        data = request.get_json() or {}
        title = data.get('title', 'AbhiHub Announcement')
        body = data.get('body', '')
        url = data.get('url', '/dashboard')
        icon = data.get('icon')

        if not body:
            return jsonify({'error': 'Notification body is required'}), 400

        result = send_notification_to_all(title, body, url=url, icon=icon)
        return jsonify(result)
    except Exception as e:
        logging.error(f"[PUSH_API] broadcast send error: {e}")
        return jsonify({'error': str(e)}), 500


@push_api.route('/api/push/test', methods=['POST'])
def send_test_notification():
    """
    Send a test notification to the authenticated user's registered devices.
    """
    try:
        user = session.get('user', {})
        user_id = user.get('uid') or user.get('id')
        user_email = user.get('email')

        if not user_id and not user_email:
            return jsonify({'error': 'Authentication required'}), 401

        client = init_supabase()
        uuid = user_id
        if not uuid and user_email and client:
            p_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if p_res.data:
                uuid = p_res.data[0]['id']

        if not uuid:
            return jsonify({'error': 'User not found'}), 404

        from push_notifications import NotificationService
        service = NotificationService.get_instance()
        res = service.send_notification(
            user_id=uuid,
            title='AbhiHub Test Notification',
            body='Notifications are working perfectly on this device! 🔔',
            url='/settings',
            category='system',
            dedupe_key=f'test:{uuid}:{int(time.time())}'
        )
        return jsonify(res)
    except Exception as e:
        logging.error(f"[PUSH_API] test send error: {e}")
        return jsonify({'error': str(e)}), 500


@push_api.route('/api/user/notification-preferences', methods=['GET', 'POST'])
def user_notification_preferences():
    """
    Get or update user notification preferences stored in Supabase profiles.
    """
    user = session.get('user', {})
    user_id = user.get('uid') or user.get('id')
    user_email = user.get('email')

    if not user_id and not user_email:
        return jsonify({'error': 'Authentication required'}), 401

    client = init_supabase()
    try:
        # Resolve UUID
        uuid = user_id
        if not uuid and user_email and client:
            p_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
            if p_res.data:
                uuid = p_res.data[0]['id']

        if not uuid:
            return jsonify({'error': 'User profile not found'}), 404

        from push_notifications import NotificationService
        service = NotificationService.get_instance()

        if request.method == 'GET':
            if client:
                res = client.table('profiles').select(
                    'notif_push_enabled, notif_email_enabled, notif_uploads_enabled, notif_chat_enabled, notif_crush_enabled'
                ).eq('id', uuid).limit(1).execute()
                prefs = {
                    'push': True,
                    'email': False,
                    'uploads': True,
                    'chat': True,
                    'crush': True
                }
                if res.data:
                    row = res.data[0]
                    prefs['push'] = row.get('notif_push_enabled') if row.get('notif_push_enabled') is not None else True
                    prefs['email'] = row.get('notif_email_enabled') if row.get('notif_email_enabled') is not None else False
                    prefs['uploads'] = row.get('notif_uploads_enabled') if row.get('notif_uploads_enabled') is not None else True
                    prefs['chat'] = row.get('notif_chat_enabled') if row.get('notif_chat_enabled') is not None else True
                    prefs['crush'] = row.get('notif_crush_enabled') if row.get('notif_crush_enabled') is not None else True
                return jsonify({'success': True, 'preferences': prefs})

            prefs = service.get_notification_preferences(uuid)
            return jsonify({'success': True, 'preferences': prefs})

        # POST: update preferences
        payload = request.get_json() or {}
        update_data = {}
        if 'push' in payload:
            update_data['notif_push_enabled'] = bool(payload['push'])
        if 'email' in payload:
            update_data['notif_email_enabled'] = bool(payload['email'])
        if 'uploads' in payload:
            update_data['notif_uploads_enabled'] = bool(payload['uploads'])
        if 'chat' in payload:
            update_data['notif_chat_enabled'] = bool(payload['chat'])
        if 'crush' in payload:
            update_data['notif_crush_enabled'] = bool(payload['crush'])

        if client and update_data:
            client.table('profiles').update(update_data).eq('id', uuid).execute()
            return jsonify({'success': True, 'updated': update_data})

        success = service.update_notification_preferences(uuid, payload)
        if success:
            return jsonify({'success': True, 'updated': payload})
        return jsonify({'error': 'Failed to update preferences'}), 500

    except Exception as e:
        logging.error(f"[PUSH_API] preference error: {e}")
        return jsonify({'error': str(e)}), 500



@push_api.route('/api/notifications/<notif_id>/open', methods=['POST'])
def track_notification_opened(notif_id):
    """
    Record that a notification was opened/clicked by user.
    """
    user = session.get('user', {})
    user_id = user.get('uid') or user.get('id')
    from push_notifications import NotificationService
    success = NotificationService.get_instance().record_notification_opened(notif_id, user_id=user_id)
    return jsonify({'success': success})


def init_push_api(app):
    """Initialize push API routes on the Flask app."""
    app.register_blueprint(push_api)

