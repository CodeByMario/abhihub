"""
Push Notification Module for AbhiHub
Uses Web Push with VAPID authentication, Supabase persistence,
preference checks, deduplication, and safe error handling.
"""

import os
import json
import logging
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

try:
    from pywebpush import webpush, WebPushException
except ImportError:
    class WebPushException(Exception):
        def __init__(self, message, response=None):
            super().__init__(message)
            self.response = response

    def webpush(*args, **kwargs):
        raise WebPushException("pywebpush not installed in environment")


# Load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# VAPID Configuration
VAPID_PUBLIC_KEY = os.environ.get('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.environ.get('VAPID_PRIVATE_KEY', '')
VAPID_CLAIMS = {
    "sub": os.environ.get('VAPID_CLAIMS_EMAIL', 'mailto:admin@abhihub.com')
}

from methods.supabase_helper import (
    init_supabase,
    get_all_push_subscriptions,
    save_push_subscription,
    remove_push_subscription_by_endpoint
)

# In-memory deduplication cache: { dedupe_key: timestamp }
_DEDUPE_CACHE: Dict[str, float] = {}
_DEDUPE_WINDOW_SECONDS = 30  # Suppress exact duplicates within 30s

ALLOWLISTED_PREFIXES = (
    '/dashboard',
    '/profile',
    '/resource',
    '/chat',
    '/settings',
    '/notifications',
    '/pyqs',
    '/notes'
)


def sanitize_url(url: Optional[str]) -> str:
    """Ensure URL is safe and relative within allowlisted paths."""
    if not url or not isinstance(url, str):
        return '/dashboard'
    url = url.strip()
    if not url.startswith('/') or url.startswith('//') or '\\' in url:
        return '/dashboard'
    # Check if URL starts with any allowlisted prefix
    for prefix in ALLOWLISTED_PREFIXES:
        if url == prefix or url.startswith(prefix + '/') or url.startswith(prefix + '?') or url.startswith(prefix + '#'):
            return url
    return '/dashboard'


def load_subscriptions() -> Dict:
    """Load all push subscriptions from Supabase (grouped by user_id list)."""
    return get_all_push_subscriptions()


class NotificationAdapter:
    """Base interface for notification delivery providers."""
    def send(self, subscription_info: dict, payload: dict) -> dict:
        raise NotImplementedError


class WebPushAdapter(NotificationAdapter):
    """Web Push provider implementation using VAPID and pywebpush."""
    def __init__(self, public_key: Optional[str] = None, private_key: Optional[str] = None, claims: Optional[dict] = None):
        self._public_key = public_key
        self._private_key = private_key
        self._claims = claims

    @property
    def public_key(self) -> str:
        return self._public_key or VAPID_PUBLIC_KEY

    @property
    def private_key(self) -> str:
        return self._private_key or VAPID_PRIVATE_KEY

    @property
    def claims(self) -> dict:
        return self._claims or VAPID_CLAIMS

    def is_configured(self) -> bool:
        return bool(self.public_key and self.private_key)

    def send(self, subscription_info: dict, payload: dict) -> dict:
        if not self.is_configured():
            return {'success': False, 'error': 'VAPID keys not configured', 'expired': False, 'retryable': False}

        endpoint = subscription_info.get('endpoint', '')
        keys = subscription_info.get('keys', {})
        if not endpoint or not keys.get('p256dh') or not keys.get('auth'):
            return {'success': False, 'error': 'Invalid subscription info', 'expired': False, 'retryable': False}

        formatted_sub = {
            'endpoint': endpoint,
            'keys': {
                'p256dh': keys.get('p256dh', ''),
                'auth': keys.get('auth', '')
            }
        }

        try:
            webpush(
                subscription_info=formatted_sub,
                data=json.dumps(payload),
                vapid_private_key=self.private_key,
                vapid_claims=self.claims,
                timeout=5
            )
            return {'success': True, 'status_code': 201, 'expired': False, 'retryable': False}
        except WebPushException as e:
            status_code = getattr(getattr(e, 'response', None), 'status_code', None)
            is_expired = status_code in (404, 410)
            is_retryable = bool(status_code and status_code >= 500)
            return {
                'success': False,
                'status_code': status_code,
                'expired': is_expired,
                'retryable': is_retryable,
                'error': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'status_code': None,
                'expired': False,
                'retryable': True,
                'error': str(e)
            }


class NotificationService:
    """
    Provider-independent notification service managing subscription lifecycle,
    preference checks, deduplication, retry handling, and delivery records.
    """
    _instance = None

    def __init__(self, adapter: Optional[NotificationAdapter] = None):
        self.adapter = adapter or WebPushAdapter()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls(WebPushAdapter())
        return cls._instance

    def register_device_or_subscription(
        self,
        user_id_or_email: str,
        subscription_info: dict,
        device_type: Optional[str] = None,
        platform: Optional[str] = None,
        browser: Optional[str] = None,
        permission_state: str = "granted"
    ) -> bool:
        if not subscription_info or 'endpoint' not in subscription_info:
            return False

        endpoint = subscription_info.get('endpoint', '').strip()
        if not endpoint:
            return False

        keys = subscription_info.get('keys', {})
        p256dh = keys.get('p256dh', '')
        auth = keys.get('auth', '')

        res = save_push_subscription(
            user_id_or_email,
            endpoint,
            p256dh,
            auth,
            device_type=device_type or 'web',
            platform=platform or 'unknown',
            browser=browser or 'unknown',
            permission_state=permission_state or 'granted'
        )
        return res.get('success', False)

    def remove_device_or_subscription(
        self,
        user_id_or_email: Optional[str] = None,
        endpoint: Optional[str] = None
    ) -> bool:
        if endpoint:
            return remove_subscription_by_endpoint(endpoint)
        if user_id_or_email:
            client = init_supabase()
            if not client:
                return False
            try:
                from methods.supabase_helper import validate_uuid
                if validate_uuid(user_id_or_email):
                    client.table('push_subscriptions').delete().eq('user_id', user_id_or_email).execute()
                    return True
                else:
                    p_res = client.table('profiles').select('id').eq('email', user_id_or_email).execute()
                    if p_res.data:
                        u_id = p_res.data[0]['id']
                        client.table('push_subscriptions').delete().eq('user_id', u_id).execute()
                        return True
            except Exception as e:
                logging.warning(f"[NOTIFICATION_SERVICE] Error removing subscription: {e}")
        return False

    def get_notification_preferences(self, user_id: str) -> dict:
        client = init_supabase()
        defaults = {
            'push': True,
            'email': False,
            'uploads': True,
            'chat': True,
            'crush': True,
            'quiet_hours_enabled': False,
            'quiet_hours_start': '22:00',
            'quiet_hours_end': '07:00'
        }
        if not client:
            return defaults
        try:
            res = client.table('profiles').select(
                'notif_push_enabled, notif_email_enabled, notif_uploads_enabled, notif_chat_enabled, notif_crush_enabled, notif_quiet_hours_enabled, notif_quiet_hours_start, notif_quiet_hours_end'
            ).eq('id', user_id).limit(1).execute()
            if res.data:
                row = res.data[0]
                return {
                    'push': row.get('notif_push_enabled') if row.get('notif_push_enabled') is not None else True,
                    'email': row.get('notif_email_enabled') if row.get('notif_email_enabled') is not None else False,
                    'uploads': row.get('notif_uploads_enabled') if row.get('notif_uploads_enabled') is not None else True,
                    'chat': row.get('notif_chat_enabled') if row.get('notif_chat_enabled') is not None else True,
                    'crush': row.get('notif_crush_enabled') if row.get('notif_crush_enabled') is not None else True,
                    'quiet_hours_enabled': row.get('notif_quiet_hours_enabled') if row.get('notif_quiet_hours_enabled') is not None else False,
                    'quiet_hours_start': row.get('notif_quiet_hours_start') or '22:00',
                    'quiet_hours_end': row.get('notif_quiet_hours_end') or '07:00'
                }
            return defaults
        except Exception as e:
            logging.warning(f"[NOTIFICATION_SERVICE] Error getting preferences: {e}")
            return defaults

    def update_notification_preferences(self, user_id: str, preferences: dict) -> bool:
        client = init_supabase()
        if not client:
            return False
        update_data = {}
        if 'push' in preferences:
            update_data['notif_push_enabled'] = bool(preferences['push'])
        if 'email' in preferences:
            update_data['notif_email_enabled'] = bool(preferences['email'])
        if 'uploads' in preferences:
            update_data['notif_uploads_enabled'] = bool(preferences['uploads'])
        if 'chat' in preferences:
            update_data['notif_chat_enabled'] = bool(preferences['chat'])
        if 'crush' in preferences:
            update_data['notif_crush_enabled'] = bool(preferences['crush'])
        if 'quiet_hours_enabled' in preferences:
            update_data['notif_quiet_hours_enabled'] = bool(preferences['quiet_hours_enabled'])
        if 'quiet_hours_start' in preferences:
            update_data['notif_quiet_hours_start'] = str(preferences['quiet_hours_start'])
        if 'quiet_hours_end' in preferences:
            update_data['notif_quiet_hours_end'] = str(preferences['quiet_hours_end'])

        if not update_data:
            return True
        try:
            client.table('profiles').update(update_data).eq('id', user_id).execute()
            return True
        except Exception as e:
            logging.warning(f"[NOTIFICATION_SERVICE] Error updating preferences: {e}")
            return False

    def record_delivery_attempt(self, endpoint: str, status: str, failure_code: Optional[str] = None):
        """Update subscription lifecycle timestamps and status without exposing sensitive payloads."""
        client = init_supabase()
        if not client or not endpoint:
            return
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            data = {'last_seen_at': now_iso}
            if status == 'success':
                data['last_success_at'] = now_iso
                data['failure_code'] = None
            elif status == 'failed':
                data['last_failure_at'] = now_iso
                data['failure_code'] = failure_code[:50] if failure_code else 'send_failure'
            client.table('push_subscriptions').update(data).eq('endpoint', endpoint).execute()
        except Exception as e:
            logging.debug(f"[NOTIFICATION_SERVICE] delivery attempt logging non-critical error: {e}")

    def record_notification_opened(self, notification_id: str, user_id: Optional[str] = None) -> bool:
        """Mark notification as opened/read when user clicks a notification action."""
        client = init_supabase()
        if not client or not notification_id:
            return False
        try:
            from methods.supabase_helper import validate_uuid
            if not validate_uuid(notification_id):
                return False
            query = client.table('notifications').update({'is_read': True}).eq('id', notification_id)
            if user_id and validate_uuid(user_id):
                query = query.eq('user_id', user_id)
            query.execute()
            return True
        except Exception as e:
            logging.warning(f"[NOTIFICATION_SERVICE] Error marking notification opened: {e}")
            return False

    def send_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        tag: Optional[str] = None,
        category: Optional[str] = None,
        dedupe_key: Optional[str] = None,
        notification_id: Optional[str] = None
    ) -> Dict:
        """
        Send a notification to all devices registered under user_id (UUID).
        Includes deduplication, preference checks, retries, and stale token pruning.
        """
        # 1. Deduplication Check
        effective_dedupe_key = dedupe_key or f"{user_id}:{tag or 'default'}:{title}"
        now = time.time()
        if effective_dedupe_key in _DEDUPE_CACHE:
            if now - _DEDUPE_CACHE[effective_dedupe_key] < _DEDUPE_WINDOW_SECONDS:
                logging.info(f"[NOTIFICATION_SERVICE] Suppressed duplicate notification for {user_id[:8] if user_id else 'unknown'}")
                return {'success': True, 'suppressed': True, 'reason': 'deduplicated'}
        _DEDUPE_CACHE[effective_dedupe_key] = now

        # Prune old dedupe cache entries
        if len(_DEDUPE_CACHE) > 1000:
            cutoff = now - _DEDUPE_WINDOW_SECONDS
            for k in list(_DEDUPE_CACHE.keys()):
                if _DEDUPE_CACHE[k] < cutoff:
                    del _DEDUPE_CACHE[k]

        # 2. Preference Check
        prefs = self.get_notification_preferences(user_id)
        if not prefs.get('push', True):
            logging.info(f"[NOTIFICATION_SERVICE] User {user_id[:8] if user_id else 'unknown'} disabled push notifications")
            return {'success': True, 'suppressed': True, 'reason': 'user_preference_disabled'}
        if category and not prefs.get(category, True):
            logging.info(f"[NOTIFICATION_SERVICE] User opted out of category '{category}'")
            return {'success': True, 'suppressed': True, 'reason': 'category_preference_disabled'}

        subscriptions = load_subscriptions()
        if user_id not in subscriptions or not subscriptions[user_id]:
            return {'success': False, 'error': 'User not subscribed'}

        sub_list = subscriptions[user_id]
        if not isinstance(sub_list, list):
            sub_list = [sub_list]

        safe_url = sanitize_url(url)

        payload = {
            'title': title,
            'body': body,
            'icon': icon or '/static/images/android-chrome-192x192.png',
            'badge': '/static/images/favicon-32x32.png',
            'url': safe_url,
            'tag': tag or 'abhihub-notification',
            'notification_id': notification_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        sent_count = 0
        failed_count = 0
        expired_count = 0

        for item in sub_list:
            sub_data = item.get('subscription', item)
            endpoint = sub_data.get('endpoint')
            keys = sub_data.get('keys', {})
            if not endpoint or not keys:
                continue

            subscription_info = {
                'endpoint': endpoint,
                'keys': {
                    'p256dh': keys.get('p256dh', ''),
                    'auth': keys.get('auth', '')
                }
            }

            # Attempt sending with up to 1 retry for transient errors
            delivered = False
            for attempt in range(2):
                res = self.adapter.send(subscription_info, payload)
                if res.get('success'):
                    sent_count += 1
                    delivered = True
                    self.record_delivery_attempt(endpoint, 'success')
                    break
                elif res.get('expired'):
                    remove_subscription_by_endpoint(endpoint)
                    expired_count += 1
                    self.record_delivery_attempt(endpoint, 'failed', failure_code='expired_410')
                    break
                elif res.get('retryable') and attempt == 0:
                    time.sleep(0.5)
                    continue
                else:
                    failed_count += 1
                    self.record_delivery_attempt(endpoint, 'failed', failure_code=res.get('error', 'send_error'))
                    break

        return {
            'success': sent_count > 0,
            'sent': sent_count,
            'failed': failed_count,
            'expired': expired_count,
            'removed': expired_count > 0 and sent_count == 0
        }


    def send_notification_to_all(
        self,
        title: str,
        body: str,
        url: Optional[str] = None,
        icon: Optional[str] = None,
        tag: Optional[str] = None
    ) -> Dict:
        """Send a push notification to all active subscribers (Admin Broadcast)."""
        subscriptions = load_subscriptions()
        if not subscriptions:
            return {'success': False, 'error': 'No subscriptions'}

        results = {'sent': 0, 'failed': 0, 'expired': 0, 'total': len(subscriptions)}

        for user_id in list(subscriptions.keys()):
            result = self.send_notification(
                user_id,
                title,
                body,
                url=url,
                icon=icon,
                tag=tag,
                category='announcements'
            )
            if result.get('success'):
                if not result.get('suppressed'):
                    results['sent'] += 1
            elif result.get('removed'):
                results['expired'] += 1
            else:
                results['failed'] += 1

        results['success'] = results['sent'] > 0
        return results


# ── Top-level functional adapters for backward compatibility ──

def add_subscription(
    user_id_or_email: str,
    subscription_info: dict,
    device_type: str = None,
    platform: str = None,
    browser: str = None,
    permission_state: str = "granted"
) -> bool:
    return NotificationService.get_instance().register_device_or_subscription(
        user_id_or_email,
        subscription_info,
        device_type=device_type,
        platform=platform,
        browser=browser,
        permission_state=permission_state
    )


def remove_subscription(user_id_or_email: str) -> bool:
    return NotificationService.get_instance().remove_device_or_subscription(user_id_or_email=user_id_or_email)


def remove_subscription_by_endpoint(endpoint: str) -> bool:
    return NotificationService.get_instance().remove_device_or_subscription(endpoint=endpoint)


def check_user_push_preference(user_id: str, category: Optional[str] = None) -> bool:
    prefs = NotificationService.get_instance().get_notification_preferences(user_id)
    if not prefs.get('push', True):
        return False
    if category and not prefs.get(category, True):
        return False
    return True


def send_notification(
    user_id: str,
    title: str,
    body: str,
    url: Optional[str] = None,
    icon: Optional[str] = None,
    tag: Optional[str] = None,
    category: Optional[str] = None,
    dedupe_key: Optional[str] = None
) -> Dict:
    return NotificationService.get_instance().send_notification(
        user_id=user_id,
        title=title,
        body=body,
        url=url,
        icon=icon,
        tag=tag,
        category=category,
        dedupe_key=dedupe_key
    )


def send_notification_to_all(
    title: str,
    body: str,
    url: Optional[str] = None,
    icon: Optional[str] = None,
    tag: Optional[str] = None
) -> Dict:
    return NotificationService.get_instance().send_notification_to_all(
        title=title,
        body=body,
        url=url,
        icon=icon,
        tag=tag
    )


def is_user_subscribed(user_id: str) -> bool:
    """Check if user has at least one active push subscription endpoint."""
    subscriptions = load_subscriptions()
    subs = subscriptions.get(user_id)
    if not subs:
        return False
    if isinstance(subs, list):
        return len(subs) > 0
    return True


def get_subscription_count() -> int:
    """Get total active subscription endpoints."""
    subscriptions = load_subscriptions()
    total = 0
    for val in subscriptions.values():
        if isinstance(val, list):
            total += len(val)
        else:
            total += 1
    return total

