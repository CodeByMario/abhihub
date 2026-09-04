# Push Notification API Routes
# Add this file's routes to your Flask app using: from push_api import init_push_api

import os
import logging
from flask import Blueprint, jsonify, request, session

push_api = Blueprint('push_api', __name__)

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
    """Subscribe to push notifications."""
    try:
        from push_notifications import add_subscription
        data = request.get_json() or {}
        subscription = data.get('subscription')
        device_type = data.get('device_type')
        
        if not subscription:
            return jsonify({'error': 'No subscription data'}), 400
        
        if not device_type:
            ua = (request.headers.get('User-Agent') or '').lower()
            if any(m in ua for m in ['mobile', 'android', 'iphone']):
                device_type = 'mobile'
            elif any(t in ua for t in ['tablet', 'ipad']):
                device_type = 'tablet'
            else:
                device_type = 'desktop'

        # Use uid as user_id (UUID), email for save_push_subscription lookup
        user = session.get('user', {})
        user_email = user.get('email', 'anonymous')
        success = add_subscription(user_email, subscription, device_type=device_type)
        
        if success:
            return jsonify({'success': True})
        return jsonify({'error': 'Failed to save'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@push_api.route('/api/push/unsubscribe', methods=['DELETE'])
def unsubscribe():
    """Unsubscribe from push notifications."""
    try:
        from push_notifications import remove_subscription
        user = session.get('user', {})
        user_id = user.get('email', user.get('uid', 'anonymous'))
        success = remove_subscription(user_id)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@push_api.route('/api/push/status')
def status():
    """Get subscription status for current user (looks up by UUID)."""
    try:
        from push_notifications import is_user_subscribed
        from methods.supabase_helper import init_supabase
        user = session.get('user', {})
        user_email = user.get('email', '')
        user_uid = user.get('uid', '')
        
        # Resolve UUID from email if uid not present
        uuid = user_uid
        if not uuid and user_email:
            client = init_supabase()
            if client:
                p_res = client.table('profiles').select('id').eq('email', user_email).execute()
                if p_res.data:
                    uuid = p_res.data[0]['id']
        
        subscribed = is_user_subscribed(uuid) if uuid else False
        return jsonify({'enabled': True, 'subscribed': subscribed})
    except Exception as e:
        logging.error(f"push_api: toggle subscription error: {e}")
        return jsonify({'enabled': False, 'subscribed': False})

@push_api.route('/api/push/send', methods=['POST'])
def send():
    """Send push notification to all subscribers."""
    try:
        from push_notifications import send_notification_to_all
        data = request.get_json()
        title = data.get('title', 'AbhiHub')
        body = data.get('body', '')
        url = data.get('url', '/dashboard')
        
        result = send_notification_to_all(title, body, url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def init_push_api(app):
    """Initialize push API routes on the Flask app."""
    app.register_blueprint(push_api)
