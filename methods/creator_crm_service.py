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
    """Calculate creator CRM overview stats from real file sales only."""
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
        # Check real customers
        real_customers = get_creator_top_customers(creator_id, limit=200)
        if real_customers:
            stats['total_customers'] = len(real_customers)
            repeat = sum(1 for r in real_customers if int(r.get('total_notes', 0)) > 1)
            vips = sum(1 for r in real_customers if r.get('vip_tier') in ('vip', 'superfan'))
            rev = sum(float(r.get('total_spent', 0)) for r in real_customers)
            stats['repeat_customers'] = repeat
            stats['vip_count'] = vips
            stats['total_revenue'] = round(rev, 2)
            stats['repeat_rate'] = int((repeat / len(real_customers)) * 100) if real_customers else 0

        # Synchronize balances from creator_wallets
        try:
            cw = db.table('creator_wallets').select('*').eq('user_id', creator_id).limit(1).execute()
            if cw.data:
                w_row = cw.data[0]
                withdrawable = float(w_row.get('withdrawable_balance', 0) or 0)
                pending = float(w_row.get('pending_balance', 0) or 0)
                stats['withdrawable_balance'] = round(withdrawable, 2)
                stats['pending_balance'] = round(pending, 2)
        except Exception as e_cw:
            logger.debug(f"[CREATOR_CRM] Wallets check note: {e_cw}")

        # Fetch total published notes count
        try:
            doc_res = db.table('documents').select('id', count='exact').eq('uploader_id', creator_id).execute()
            stats['total_uploads'] = doc_res.count if doc_res.count is not None else len(doc_res.data or [])
        except Exception:
            pass

    except Exception as e:
        logger.warning(f"[CREATOR_CRM] Error fetching stats: {e}")

    return stats


def get_creator_top_customers(creator_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieve top real customers with purchase metrics.
    STRICTLY REAL DATA ONLY - NEVER GENERATE PLACEHOLDERS.
    STRICTLY NAME ONLY - NO PII (No phone, No email).
    """
    db = _client()
    if not db or not creator_id:
        return []

    try:
        # 1. Query dedicated creator_customer_relations table
        res = db.table('creator_customer_relations') \
            .select('customer_id, customer_name, total_spent, total_notes_unlocked, vip_tier, last_interacted_at, profiles!creator_customer_relations_customer_id_fkey(full_name)') \
            .eq('creator_id', str(creator_id)) \
            .order('total_spent', desc=True) \
            .limit(limit) \
            .execute()

        customers = []
        if res.data:
            for r in res.data:
                prof = r.get('profiles') or {}
                if isinstance(prof, list) and prof:
                    prof = prof[0]
                elif not isinstance(prof, dict):
                    prof = {}
                name = prof.get('full_name') or r.get('customer_name')
                if not name or name.strip() == '':
                    continue

                spent = float(r.get('total_spent', 0))
                notes = int(r.get('total_notes_unlocked', 1))
                tier = r.get('vip_tier', 'regular')

                customers.append({
                    'customer_id': r.get('customer_id'),
                    'name': name.strip(),
                    'total_spent': round(spent, 2),
                    'total_notes': notes,
                    'vip_tier': tier,
                    'last_active': (r.get('last_interacted_at') or '')[:10]
                })
            return customers

        # 2. Real fallback: Only match real orders from credit_transactions and profiles
        wl_res = db.table('wallet_ledger') \
            .select('order_id, amount, created_at') \
            .eq('creator_id', str(creator_id)) \
            .eq('type', 'credit') \
            .execute()

        wl_data = [w for w in (wl_res.data or []) if w.get('order_id') and not str(w.get('order_id', '')).startswith(('ADMIN-', 'REFUND-', 'PAYOUT-'))]
        if not wl_data:
            return []  # Real empty state, NEVER generate fake supporters

        order_ids = [w['order_id'] for w in wl_data]
        tx_res = db.table('credit_transactions').select('order_id, user_id').in_('order_id', order_ids).execute().data or []
        tx_by_order = {t['order_id']: t['user_id'] for t in tx_res if t.get('user_id')}
        uids = list({uid for uid in tx_by_order.values() if uid and uid != str(creator_id)})

        if not uids:
            return []  # No real buyer profiles found

        profs_res = db.table('profiles').select('id, full_name').in_('id', uids).execute().data or []
        profs = {p['id']: p.get('full_name') for p in profs_res if p.get('full_name')}

        buyers = {}
        for w in wl_data:
            oid = w.get('order_id')
            uid = tx_by_order.get(oid)
            if not uid or uid not in profs:
                continue
            amt = float(w.get('amount') or 0)
            c_at = (w.get('created_at') or '')[:10]
            if uid not in buyers:
                buyers[uid] = {
                    'customer_id': uid,
                    'name': profs[uid].strip(),
                    'total_spent': 0.0,
                    'total_notes': 0,
                    'last_active': c_at
                }
            buyers[uid]['total_spent'] = round(buyers[uid]['total_spent'] + amt, 2)
            buyers[uid]['total_notes'] += 1
            if c_at > buyers[uid]['last_active']:
                buyers[uid]['last_active'] = c_at

        for b in sorted(buyers.values(), key=lambda x: x['total_spent'], reverse=True)[:limit]:
            b['vip_tier'] = 'vip' if b['total_spent'] >= 100 or b['total_notes'] >= 3 else 'regular'
            customers.append(b)

        return customers
    except Exception as e:
        logger.error(f"[CREATOR_CRM] Error fetching top customers: {e}")
        return []


def get_creator_products_with_sales(creator_id: str) -> Dict[str, Any]:
    """
    Fetch all documents uploaded by creator, grouped by subject/course,
    with per-document sales count and gross revenue.
    """
    db = _client()
    if not db or not creator_id:
        return {'products': [], 'grouped': {}, 'total_sales_count': 0, 'gross_sales': 0.0}

    try:
        # 1. Fetch creator's documents
        docs_res = db.table('documents') \
            .select('id, title, document_category, subject_id, is_paid, price, view_count, created_at, file_type') \
            .eq('uploader_id', str(creator_id)) \
            .order('created_at', desc=True) \
            .execute()

        docs = docs_res.data or []
        if not docs:
            return {'products': [], 'grouped': {}, 'total_sales_count': 0, 'gross_sales': 0.0}

        # 2. Map subject names
        subj_ids = list({d['subject_id'] for d in docs if d.get('subject_id')})
        subj_map = {}
        if subj_ids:
            try:
                s_res = db.table('subjects').select('id, name, subject_code').in_('id', subj_ids).execute()
                for s in (s_res.data or []):
                    subj_map[s['id']] = s.get('name') or s.get('subject_code') or 'General Subject'
            except Exception as e_s:
                logger.debug(f"[CREATOR_CRM] Subject fetch note: {e_s}")

        # 3. Aggregate sales from wallet_ledger
        ledger_res = db.table('wallet_ledger') \
            .select('doc_id, amount, status') \
            .eq('creator_id', str(creator_id)) \
            .eq('type', 'credit') \
            .execute()

        sales_map = {}
        gross_map = {}
        total_sales_count = 0
        total_gross_sales = 0.0

        for row in (ledger_res.data or []):
            d_id = row.get('doc_id')
            amt = float(row.get('amount') or 0.0)
            if d_id:
                sales_map[d_id] = sales_map.get(d_id, 0) + 1
                gross_map[d_id] = round(gross_map.get(d_id, 0.0) + amt, 2)
                total_sales_count += 1
                total_gross_sales += amt

        # Build enriched product list and group
        products = []
        grouped = {}
        for d in docs:
            d_id = d['id']
            group_name = subj_map.get(d.get('subject_id')) or (d.get('document_category') or 'General Study Notes').title()
            p_item = {
                'id': d_id,
                'title': d.get('title') or 'Untitled Document',
                'category': (d.get('document_category') or 'notes').title(),
                'group': group_name,
                'is_paid': bool(d.get('is_paid')),
                'price': float(d.get('price') or 0.0),
                'views': int(d.get('view_count') or 0),
                'sales_count': sales_map.get(d_id, 0),
                'gross_revenue': gross_map.get(d_id, 0.0),
                'created_at': (d.get('created_at') or '')[:10]
            }
            products.append(p_item)
            grouped.setdefault(group_name, []).append(p_item)

        return {
            'products': products,
            'grouped': grouped,
            'total_sales_count': total_sales_count,
            'gross_sales': round(total_gross_sales, 2)
        }
    except Exception as e:
        logger.error(f"[CREATOR_CRM] Error fetching products with sales: {e}")
        return {'products': [], 'grouped': {}, 'total_sales_count': 0, 'gross_sales': 0.0}


def update_document_monetization(creator_id: str, doc_id: str, is_paid: bool, price: float) -> Dict[str, Any]:
    """Update price and is_paid for a creator's document."""
    db = _client()
    if not db or not creator_id or not doc_id:
        return {'success': False, 'error': 'Missing parameters'}

    try:
        price_val = max(0.0, round(float(price or 0.0), 2))
        if is_paid and price_val <= 0:
            price_val = 19.0  # Default nominal study note price if set to paid without price
        elif not is_paid:
            price_val = 0.0

        res = db.table('documents') \
            .update({
                'is_paid': bool(is_paid),
                'price': price_val,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }) \
            .eq('id', str(doc_id)) \
            .eq('uploader_id', str(creator_id)) \
            .execute()

        if res.data:
            return {'success': True, 'doc_id': doc_id, 'is_paid': bool(is_paid), 'price': price_val}
        return {'success': False, 'error': 'Document not found or unauthorized'}
    except Exception as e:
        logger.error(f"[CREATOR_CRM] Update monetization failed: {e}")
        return {'success': False, 'error': str(e)}



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
            if not customer_name or not customer_email:
                try:
                    p_res = db.table('profiles').select('full_name, email').eq('id', str(customer_id)).limit(1).execute()
                    if p_res.data:
                        customer_name = customer_name or p_res.data[0].get('full_name')
                        customer_email = customer_email or p_res.data[0].get('email')
                except Exception:
                    pass
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

