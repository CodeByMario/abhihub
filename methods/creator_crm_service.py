"""
Creator CRM & Community Service
Aggregates top customers, buyer lifetime value (LTV), and handles community broadcast messaging.
"""

import logging
from typing import Dict, List, Any
from datetime import datetime, timezone
from methods.supabase_helper import init_supabase, init_supabase_admin

logger = logging.getLogger(__name__)


def _client():
    client = init_supabase_admin()
    if client:
        return client
    return init_supabase()


def get_creator_customer_stats(creator_id: str) -> Dict[str, Any]:
    """Calculate creator CRM overview stats (total customers, repeat rate, total revenue)."""
    db = _client()
    stats = {
        'total_customers': 0,
        'repeat_customers': 0,
        'vip_count': 0,
        'total_revenue': 0.0,
        'repeat_rate': 0
    }
    if not db or not creator_id:
        return stats

    try:
        res = db.table('creator_customer_relations').select('*').eq('creator_id', creator_id).execute()
        rows = res.data or []
        if rows:
            stats['total_customers'] = len(rows)
            repeat = sum(1 for r in rows if int(r.get('total_notes_unlocked', 0)) > 1)
            vips = sum(1 for r in rows if r.get('vip_tier') in ('vip', 'superfan'))
            rev = sum(float(r.get('total_spent', 0)) for r in rows)
            stats['repeat_customers'] = repeat
            stats['vip_count'] = vips
            stats['total_revenue'] = round(rev, 2)
            stats['repeat_rate'] = int((repeat / len(rows)) * 100) if rows else 0
        else:
            # Fallback to wallet ledger if customer relations table is fresh
            wl = db.table('wallet_ledger').select('amount').eq('creator_id', creator_id).execute()
            wl_rows = wl.data or []
            stats['total_revenue'] = round(sum(float(w.get('amount', 0)) for w in wl_rows), 2)
    except Exception as e:
        logger.warning(f"[CREATOR_CRM] Error fetching stats: {e}")

    return stats


def get_creator_top_customers(creator_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieve top customers with contact links, tiers, and purchase metrics."""
    db = _client()
    if not db or not creator_id:
        return []

    try:
        # 1. Try dedicated table first
        res = db.table('creator_customer_relations') \
            .select('*, profiles!creator_customer_relations_customer_id_fkey(full_name, email, phone_number)') \
            .eq('creator_id', creator_id) \
            .order('total_spent', desc=True) \
            .limit(limit) \
            .execute()

        customers = []
        if res.data:
            for r in res.data:
                prof = r.get('profiles') or {}
                name = prof.get('full_name') or r.get('customer_name') or 'Student Supporter'
                email = prof.get('email') or r.get('customer_email') or ''
                spent = float(r.get('total_spent', 0))
                notes = int(r.get('total_notes_unlocked', 1))
                tier = r.get('vip_tier', 'regular')
                phone_num = prof.get('phone_number') or ''

                customers.append({
                    'customer_id': r.get('customer_id'),
                    'name': name,
                    'email': email,
                    'phone': phone_num,
                    'avatar_url': f"https://api.dicebear.com/7.x/bottts/svg?seed={name}",
                    'total_spent': spent,
                    'total_notes': notes,
                    'vip_tier': tier,
                    'last_active': (r.get('last_interacted_at') or '')[:10],
                    'email_link': f"mailto:{email}?subject=Thank%20you%20for%20supporting%20my%20notes%20on%20AbhiHub" if email else None,
                    'whatsapp_link': f"https://wa.me/{phone_num.replace('+', '').replace(' ', '')}" if phone_num else None
                })
            return customers

        # 2. Resilient backfill fallback from transactions/ledger if fresh
        wl = db.table('wallet_ledger').select('*').eq('creator_id', creator_id).limit(limit).execute()
        if wl.data:
            for idx, item in enumerate(wl.data):
                amt = float(item.get('amount', 0))
                customers.append({
                    'customer_id': f"cust_{idx}",
                    'name': f"Supporter #{idx + 1}",
                    'email': '',
                    'phone': '',
                    'avatar_url': f"https://api.dicebear.com/7.x/bottts/svg?seed=supporter_{idx}",
                    'total_spent': amt,
                    'total_notes': 1,
                    'vip_tier': 'vip' if amt >= 100 else 'regular',
                    'last_active': (item.get('created_at') or '')[:10],
                    'email_link': None,
                    'whatsapp_link': None
                })
        return customers
    except Exception as e:
        logger.error(f"[CREATOR_CRM] Error fetching top customers: {e}")
        return []


def create_creator_broadcast(creator_id: str, title: str, message: str, channel_url: str = '', target_tier: str = 'all') -> Dict[str, Any]:
    """Publish a community update / announcement to the creator's buyers."""
    db = _client()
    if not db or not creator_id or not title or not message:
        return {'success': False, 'error': 'Missing title or message'}

    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = {
            'creator_id': creator_id,
            'title': title.strip(),
            'message': message.strip(),
            'channel_url': channel_url.strip() if channel_url else None,
            'target_tier': target_tier if target_tier in ('all', 'vip', 'superfan') else 'all',
            'view_count': 0,
            'created_at': now_iso
        }
        res = db.table('creator_broadcasts').insert(payload).execute()
        return {'success': True, 'data': res.data[0] if res.data else {}}
    except Exception as e:
        logger.error(f"[CREATOR_CRM] Broadcast creation failed: {e}")
        return {'success': False, 'error': str(e)}


def get_creator_broadcasts(creator_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Fetch past broadcast updates sent by this creator."""
    db = _client()
    if not db or not creator_id:
        return []
    try:
        res = db.table('creator_broadcasts') \
            .select('*') \
            .eq('creator_id', creator_id) \
            .order('created_at', desc=True) \
            .limit(limit) \
            .execute()
        return res.data or []
    except Exception as e:
        logger.warning(f"[CREATOR_CRM] Error fetching broadcasts: {e}")
        return []


def record_creator_customer_purchase(creator_id: str, customer_id: str, amount: float, customer_name: str = None, customer_email: str = None):
    """Upserts customer-creator relationship with cumulative spending and VIP tier evaluation."""
    db = _client()
    if not db or not creator_id or not customer_id:
        return
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        amt = float(amount or 0)
        existing = db.table('creator_customer_relations') \
            .select('*') \
            .eq('creator_id', str(creator_id)) \
            .eq('customer_id', str(customer_id)) \
            .limit(1) \
            .execute()

        if existing.data:
            row = existing.data[0]
            new_spent = round(float(row.get('total_spent', 0)) + amt, 2)
            new_notes = int(row.get('total_notes_unlocked', 1)) + 1
            tier = 'superfan' if new_spent >= 250 or new_notes >= 5 else ('vip' if new_spent >= 100 or new_notes >= 3 else 'regular')
            db.table('creator_customer_relations').update({
                'total_spent': new_spent,
                'total_notes_unlocked': new_notes,
                'vip_tier': tier,
                'last_interacted_at': now_iso
            }).eq('id', row['id']).execute()
        else:
            tier = 'superfan' if amt >= 250 else ('vip' if amt >= 100 else 'regular')
            db.table('creator_customer_relations').insert({
                'creator_id': str(creator_id),
                'customer_id': str(customer_id),
                'total_spent': round(amt, 2),
                'total_notes_unlocked': 1,
                'vip_tier': tier,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'last_interacted_at': now_iso,
                'created_at': now_iso
            }).execute()
    except Exception as e:
        logger.warning(f"[CREATOR_CRM] record_creator_customer_purchase note: {e}")

