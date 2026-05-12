"""
Push Notification Module for AbhiHub
Uses Web Push with VAPID authentication.
"""

import os
import json
from pywebpush import webpush, WebPushException
from datetime import datetime

# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, rely on system environment variables

# VAPID Configuration
# IMPORTANT: Set these as environment variables in production!
# Never commit private keys to version control.
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS = {
    "sub": os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@abhihub.com')
}

# Subscription storage file path (now deprecated, using Supabase)
SUBSCRIPTIONS_FILE = os.path.join(os.path.dirname(__file__), 'data', 'push_subscriptions.json')

from methods.supabase_helper import (
    get_all_push_subscriptions,
    save_push_subscription,
    remove_push_subscription_by_endpoint
)

def load_subscriptions():
    """Load all push subscriptions from Supabase."""
    return get_all_push_subscriptions()

def save_subscriptions(subscriptions):
    """Deprecated: individual saves handle updates"""
    return True


def add_subscription(user_id, subscription_info):
    """
    Add or update a push subscription for a user.
    """
    if not subscription_info or 'endpoint' not in subscription_info:
        return False
        
    endpoint = subscription_info.get('endpoint')
    keys = subscription_info.get('keys', {})
    p256dh = keys.get('p256dh', '')
    auth = keys.get('auth', '')
    
    res = save_push_subscription(user_id, endpoint, p256dh, auth, device_type='web')
    return res.get('success', False)


def remove_subscription(user_id):
    """Remove a user's push subscription (placeholder - better done by endpoint)"""
    # Assuming user_id refers to email in our new flow
    from methods.supabase_helper import init_supabase
    client = init_supabase()
    if client:
        try:
            p_res = client.table('profiles').select('id').eq('email', user_id).execute()
            if p_res.data:
                u_id = p_res.data[0]['id']
                client.table('push_subscriptions').delete().eq('user_id', u_id).execute()
                return True
        except:
            pass
    return False

def remove_subscription_by_endpoint(endpoint):
    """Remove subscription by endpoint (for expired subscriptions)."""
    return remove_push_subscription_by_endpoint(endpoint)


def send_notification(user_id, title, body, url=None, icon=None, tag=None):
    """
    Send a push notification to a specific user (user_id = UUID from profiles).
    
    Args:
        user_id: Target user UUID (must match key in get_all_push_subscriptions)
        title: Notification title
        body: Notification body text
        url: URL to open on click (optional)
        icon: Icon URL (optional)
        tag: Notification tag for grouping (optional)
    
    Returns:
        dict: Result with success status and message
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return {'success': False, 'error': 'VAPID keys not configured'}
    
    subscriptions = load_subscriptions()  # keyed by UUID
    
    if user_id not in subscriptions:
        return {'success': False, 'error': 'User not subscribed'}
    
    sub_data = subscriptions[user_id]['subscription']
    # Build a proper subscription_info dict for pywebpush
    subscription_info = {
        'endpoint': sub_data['endpoint'],
        'keys': {
            'p256dh': sub_data['keys']['p256dh'],
            'auth': sub_data['keys']['auth']
        }
    }
    
    # Build notification payload
    payload = {
        'title': title,
        'body': body,
        'icon': icon or '/static/images/android-chrome-192x192.png',
        'badge': '/static/images/favicon-32x32.png',
        'url': url or '/dashboard',
        'tag': tag or 'abhihub-notification',
        'timestamp': datetime.utcnow().isoformat()
    }
    
    try:
        webpush(
            subscription_info=subscription_info,
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims=VAPID_CLAIMS
        )
        return {'success': True, 'message': 'Notification sent'}
    
    except WebPushException as e:
        # Handle expired/invalid subscriptions
        if e.response and e.response.status_code in (404, 410):
            endpoint = sub_data.get('endpoint', '')
            remove_subscription_by_endpoint(endpoint)
            return {'success': False, 'error': 'Subscription expired', 'removed': True}
        
        return {'success': False, 'error': str(e)}


def send_notification_to_all(title, body, url=None, icon=None, tag=None):
    """
    Send a push notification to all subscribed users.
    
    Returns:
        dict: Results summary
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return {'success': False, 'error': 'VAPID keys not configured'}
    
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        return {'success': False, 'error': 'No subscriptions'}
    
    results = {'sent': 0, 'failed': 0, 'expired': 0}
    
    for user_id in list(subscriptions.keys()):
        result = send_notification(user_id, title, body, url, icon, tag)
        
        if result.get('success'):
            results['sent'] += 1
        elif result.get('removed'):
            results['expired'] += 1
        else:
            results['failed'] += 1
    
    results['success'] = results['sent'] > 0
    return results



def get_subscription_count():
    """Get the number of active subscriptions."""
    subscriptions = load_subscriptions()
    return len(subscriptions)


def is_user_subscribed(user_id):
    """
    Check if a user (by UUID) is subscribed to push notifications.
    The subscriptions dict is keyed by user UUID.
    """
    subscriptions = load_subscriptions()  # keyed by UUID
    return user_id in subscriptions


def get_all_subscriptions():
    """
    Get all push notification subscriptions with metadata.
    
    Returns:
        dict: All subscriptions with user IDs as keys
    """
    return load_subscriptions()


def send_notification_to_users(user_ids, title, body, url=None, icon=None, tag=None):
    """
    Send push notification to specific list of users.
    
    Args:
        user_ids: List of user IDs to send notification to
        title: Notification title
        body: Notification body text
        url: URL to open on click (optional)
        icon: Icon URL (optional)
        tag: Notification tag for grouping (optional)
    
    Returns:
        dict: Results summary with detailed per-user status
    """
    if not VAPID_PRIVATE_KEY or not VAPID_PUBLIC_KEY:
        return {'success': False, 'error': 'VAPID keys not configured'}
    
    if not user_ids or not isinstance(user_ids, list):
        return {'success': False, 'error': 'Invalid user_ids parameter'}
    
    subscriptions = load_subscriptions()
    results = {'sent': 0, 'failed': 0, 'expired': 0, 'details': []}
    
    for user_id in user_ids:
        if user_id not in subscriptions:
            results['details'].append({
                'user_id': user_id,
                'status': 'failed',
                'error': 'User not subscribed'
            })
            results['failed'] += 1
            continue
        
        result = send_notification(user_id, title, body, url, icon, tag)
        
        if result.get('success'):
            results['sent'] += 1
            results['details'].append({
                'user_id': user_id,
                'status': 'success'
            })
        elif result.get('removed'):
            results['expired'] += 1
            results['details'].append({
                'user_id': user_id,
                'status': 'expired',
                'error': result.get('error', 'Subscription expired')
            })
        else:
            results['failed'] += 1
            results['details'].append({
                'user_id': user_id,
                'status': 'failed',
                'error': result.get('error', 'Unknown error')
            })
    
    results['success'] = results['sent'] > 0
    return results
