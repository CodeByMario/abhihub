import time
"""
AbhiHub Gamification, Badges & Ambassador Program Service.
Normalized relational data access with resilient table fallbacks.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

log = logging.getLogger(__name__)

# Master Badge Catalog
BADGE_DEFINITIONS = {
    'pioneer': {
        'slug': 'pioneer',
        'name': 'Pioneer',
        'icon': '🚩',
        'rarity': 'Legendary',
        'description': 'First student to join AbhiHub from their college.',
        'scarcity_rule': 'One per college'
    },
    'first_upload': {
        'slug': 'first_upload',
        'name': 'First Upload',
        'icon': '⚡',
        'rarity': 'Legendary',
        'description': 'Uploaded the very first approved resource for a college.',
        'scarcity_rule': 'One per college'
    },
    'first_buyer': {
        'slug': 'first_buyer',
        'name': 'First Buyer',
        'icon': '🛍️',
        'rarity': 'Rare',
        'description': 'First student to purchase study material for their college.',
        'scarcity_rule': 'One per college'
    },
    'founding_ambassador': {
        'slug': 'founding_ambassador',
        'name': 'Founding Ambassador',
        'icon': '👑',
        'rarity': 'Legendary',
        'description': 'Exclusive Founding Ambassador who unlocked their college.',
        'scarcity_rule': 'Exclusive title (1 person per college)'
    },
    'top_10_member': {
        'slug': 'top_10_member',
        'name': 'Top 10 Member',
        'icon': '🏅',
        'rarity': 'Rare',
        'description': 'One of the first 10 students registered from their college.',
        'scarcity_rule': 'Max 10 per college'
    },
    'streak_scholar': {
        'slug': 'streak_scholar',
        'name': 'Streak Scholar',
        'icon': '🔥',
        'rarity': 'Common',
        'description': 'Maintained active study or upload streak for 3 consecutive days.',
        'scarcity_rule': 'Recurring activity'
    },
    'top_seller': {
        'slug': 'top_seller',
        'name': 'Top Seller',
        'icon': '⭐',
        'rarity': 'Rare',
        'description': 'Achieved 10+ paid resource sales with a 4.5+ student rating.',
        'scarcity_rule': 'High quality seller'
    },
    'referral_champion': {
        'slug': 'referral_champion',
        'name': 'Referral Champion',
        'icon': '🚀',
        'rarity': 'Legendary',
        'description': 'Successfully invited 10+ verified students to AbhiHub.',
        'scarcity_rule': 'Top inviter'
    }
}


def _get_client():
    from methods.supabase_helper import init_supabase_admin, init_supabase
    return init_supabase_admin() or init_supabase()


_BADGES_CACHE = {}
_BADGES_CACHE_TTL = 60.0

def get_user_badges(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all badges earned by a user, including permanent timestamp."""
    client = _get_client()
    if not client or not user_id:
        return []

    now = time.time()
    if user_id in _BADGES_CACHE:
        c_time, c_data = _BADGES_CACHE[user_id]
        if now - c_time < _BADGES_CACHE_TTL:
            return c_data

    earned_badges = []
    # 1. Check normalized user_badges table
    try:
        res = client.table('user_badges').select('*').eq('user_id', user_id).execute()
        if res.data:
            for row in res.data:
                slug = row.get('badge_slug')
                b_def = BADGE_DEFINITIONS.get(slug, {
                    'slug': slug,
                    'name': slug.replace('_', ' ').title(),
                    'icon': '🎖️',
                    'rarity': 'Common',
                    'description': ''
                })
                earned_badges.append({
                    **b_def,
                    'earned_at': row.get('earned_at') or row.get('created_at'),
                    'college_id': row.get('college_id'),
                    'claimed_by_username': row.get('claimed_by_username')
                })
            _BADGES_CACHE[user_id] = (now, earned_badges)
            return earned_badges
    except Exception as e:
        log.debug(f"[Gamification] user_badges query: {e}")

    _BADGES_CACHE[user_id] = (now, earned_badges)
    return earned_badges


def get_all_badges_with_user_status(user_id: str, college_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all catalog badges, marked earned or greyed out with unlock conditions and scarcity."""
    earned = {b['slug']: b for b in get_user_badges(user_id)}
    catalog = []

    client = _get_client()
    college_first_claims = {}
    top10_remaining = 10

    if client and college_id:
        try:
            # Check who claimed the pioneer or first upload for this college
            c_claims = client.table('user_badges').select('badge_slug, user_id, earned_at, profiles(full_name, email)') \
                .eq('college_id', college_id).execute()
            for r in (c_claims.data or []):
                slug = r.get('badge_slug')
                prof = r.get('profiles') or {}
                uname = prof.get('full_name') or (prof.get('email', '').split('@')[0]) or 'User'
                if slug not in college_first_claims:
                    college_first_claims[slug] = {
                        'user_id': r.get('user_id'),
                        'username': uname,
                        'earned_at': r.get('earned_at')
                    }

            # Calculate remaining Top 10 spots for this college
            member_cnt_res = client.table('profiles').select('id', count='exact').eq('college_id', college_id).execute()
            current_members = member_cnt_res.count or len(member_cnt_res.data or [])
            top10_remaining = max(0, 10 - current_members)
        except Exception as e:
            log.debug(f"[Gamification] badge claims lookup failed: {e}")

    for slug, b_meta in BADGE_DEFINITIONS.items():
        is_earned = slug in earned
        claimed_info = college_first_claims.get(slug)
        item = {
            **b_meta,
            'is_earned': is_earned,
            'earned_at': earned[slug]['earned_at'] if is_earned else None,
            'claim_holder': claimed_info if (not is_earned and claimed_info) else None,
            'scarcity_note': f"Only {top10_remaining} spots left" if slug == 'top_10_member' and not is_earned else b_meta['scarcity_rule']
        }
        catalog.append(item)

    return catalog


def award_badge(user_id: str, badge_slug: str, college_id: Optional[str] = None, metadata: Optional[Dict] = None) -> bool:
    """Award a badge with tie-breaking earliest server timestamp and exclusivity rules."""
    if badge_slug not in BADGE_DEFINITIONS or not user_id:
        return False

    client = _get_client()
    if not client:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    # Exclusive single-holder checks (Founding Ambassador, Pioneer, First Upload)
    if badge_slug in ['pioneer', 'first_upload', 'founding_ambassador', 'first_buyer'] and college_id:
        try:
            existing = client.table('user_badges').select('id, user_id, earned_at') \
                .eq('college_id', college_id).eq('badge_slug', badge_slug) \
                .order('earned_at', desc=False).limit(1).execute()
            if existing.data:
                # Already claimed exclusively for this college!
                return False
        except Exception:
            pass

    # Insert into user_badges
    try:
        payload = {
            'user_id': user_id,
            'badge_slug': badge_slug,
            'college_id': college_id,
            'earned_at': now_iso,
            'metadata': metadata or {}
        }
        client.table('user_badges').insert(payload).execute()

        try:
            from methods.supabase_helper import log_notification
            b_meta = BADGE_DEFINITIONS.get(badge_slug, {})
            b_name = b_meta.get('name', badge_slug.title())
            b_icon = b_meta.get('icon', '🏅')
            log_notification(
                user_id,
                'badge_unlocked',
                f"Badge Unlocked: {b_icon} {b_name}!",
                f"Congratulations! You've earned the {b_meta.get('rarity', 'Campus')} badge '{b_name}'. View it in your Account.",
                url='/settings'
            )
            try:
                from push_notifications import send_notification
                send_notification(
                    user_id,
                    f"Badge Unlocked: {b_icon} {b_name}!",
                    f"You've earned the {b_meta.get('rarity')} badge '{b_name}'!",
                    url='/settings',
                    tag=f"badge-{badge_slug}",
                    category='gamification'
                )
            except Exception:
                pass
        except Exception:
            pass
        return True
    except Exception as e:
        log.debug(f"[Gamification] Relational award_badge failed, falling back to profile JSON: {e}")
        # Fallback to profiles.badges
        try:
            p_res = client.table('profiles').select('badges').eq('id', user_id).single().execute()
            badges = (p_res.data or {}).get('badges') or []
            existing_slugs = [b if isinstance(b, str) else b.get('slug') for b in badges]
            if badge_slug not in existing_slugs:
                badges.append({'slug': badge_slug, 'earned_at': now_iso})
                client.table('profiles').update({'badges': badges}).eq('id', user_id).execute()
                return True
        except Exception as e2:
            log.warning(f"[Gamification] JSON fallback award failed: {e2}")

    return False


def get_college_ambassador_status(college_id: str) -> Dict[str, Any]:
    """Get ambassador unlocking status and progress for a college."""
    client = _get_client()
    if not client or not college_id:
        return {'is_unlocked': False, 'approved_uploads': 0, 'required': 3, 'founding_ambassador': None}

    try:
        # Check approved uploads count
        docs_res = client.table('documents').select('id, uploader_id', count='exact') \
            .eq('college_id', college_id).eq('status', 'approved').execute()
        approved_count = docs_res.count or len(docs_res.data or [])

        # Check existing founding ambassador
        amb_res = client.table('college_ambassadors').select('user_id, is_founding, profiles(id, full_name, email)') \
            .eq('college_id', college_id).eq('is_founding', True).limit(1).execute()
        founding_user = None
        if amb_res.data:
            p = amb_res.data[0].get('profiles') or {}
            founding_user = {
                'id': amb_res.data[0].get('user_id'),
                'name': p.get('full_name') or (p.get('email', '').split('@')[0]) or 'Founding Ambassador'
            }

        return {
            'is_unlocked': approved_count >= 1,
            'approved_uploads': approved_count,
            'required': 3,
            'remaining_to_unlock': max(0, 3 - approved_count),
            'founding_ambassador': founding_user
        }
    except Exception as e:
        log.warning(f"[Gamification] get_college_ambassador_status failed: {e}")
        return {'is_unlocked': False, 'approved_uploads': 0, 'required': 3, 'founding_ambassador': None}


def get_college_referral_leaderboard(college_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Return top student inviters/ambassadors for a college."""
    client = _get_client()
    if not client or not college_id:
        return []

    try:
        # Query profiles in this college ordered by reputation score or referral count
        res = client.table('profiles').select('id, full_name, email, reputation_score, referral_code, is_verified') \
            .eq('college_id', college_id) \
            .order('reputation_score', desc=True).limit(limit).execute()
        
        leaders = []
        for rank, p in enumerate(res.data or [], start=1):
            name = p.get('full_name') or (p.get('email', '').split('@')[0]) or 'Student'
            leaders.append({
                'rank': rank,
                'user_id': p.get('id'),
                'username': p.get('email', '').split('@')[0] if p.get('email') else 'student',
                'name': name,
                'reputation_score': p.get('reputation_score', 0),
                'referral_code': p.get('referral_code', ''),
                'is_verified': p.get('is_verified', False)
            })
        return leaders
    except Exception as e:
        log.warning(f"[Gamification] Leaderboard query error: {e}")
        return []


def on_user_joined_college(user_id: str, college_id: str):
    """Triggered when a user associates with a college to award Pioneer or Top 10."""
    client = _get_client()
    if not client or not user_id or not college_id:
        return

    try:
        res = client.table('profiles').select('id', count='exact') \
            .eq('college_id', college_id).neq('id', user_id).execute()
        prior_count = res.count or len(res.data or [])

        if prior_count == 0:
            award_badge(user_id, 'pioneer', college_id=college_id)
        if prior_count < 10:
            award_badge(user_id, 'top_10_member', college_id=college_id, metadata={'member_index': prior_count + 1})
    except Exception as e:
        log.warning(f"[Gamification] on_user_joined_college error: {e}")


def on_document_approved(doc_id: str, uploader_id: str, college_id: Optional[str]):
    """Triggered after an upload passes moderation/approval to prevent badge abuse."""
    client = _get_client()
    if not client or not uploader_id or not college_id:
        return

    try:
        docs_res = client.table('documents').select('id', count='exact') \
            .eq('college_id', college_id).eq('status', 'approved').execute()
        total_approved = docs_res.count or len(docs_res.data or [])

        if total_approved == 1:
            award_badge(uploader_id, 'first_upload', college_id=college_id)
            award_badge(uploader_id, 'founding_ambassador', college_id=college_id)
            try:
                client.table('college_ambassadors').insert({
                    'college_id': college_id,
                    'user_id': uploader_id,
                    'is_founding': True,
                    'approved_uploads_count': 1
                }).execute()
            except Exception:
                pass
    except Exception as e:
        log.warning(f"[Gamification] on_document_approved error: {e}")
