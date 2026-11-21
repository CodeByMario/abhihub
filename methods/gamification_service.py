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
    'starter_scholar': {
        'slug': 'starter_scholar',
        'name': 'Campus Scholar',
        'icon': '🎖️',
        'rarity': 'Special',
        'medal_tier': 'Starter',
        'description': 'Welcome honor awarded for joining the AbhiHub academic community.',
        'scarcity_rule': 'Starter medal for every student'
    },
    'knowledge_seeker': {
        'slug': 'knowledge_seeker',
        'name': 'Curious Explorer',
        'icon': '🔍',
        'rarity': 'Rare',
        'medal_tier': 'Bronze',
        'description': 'Discovered academic knowledge and searched campus study resources.',
        'scarcity_rule': 'Earned on first academic search'
    },
    'master_researcher': {
        'slug': 'master_researcher',
        'name': 'Master Researcher',
        'icon': '🏆',
        'rarity': 'Legendary',
        'medal_tier': 'Gold',
        'description': 'Conducted 10+ active searches across campus subjects and materials.',
        'scarcity_rule': 'Active researcher milestone'
    },
    'pioneer': {
        'slug': 'pioneer',
        'name': 'Pioneer',
        'icon': '🚩',
        'rarity': 'Legendary',
        'medal_tier': 'Gold',
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
_BADGES_CACHE_TTL = 300.0

def get_user_badges(user_id: str) -> List[Dict[str, Any]]:
    """Retrieve all badges earned by a user from user_achievements table."""
    client = _get_client()
    if not client or not user_id:
        return []

    now = time.time()
    if user_id in _BADGES_CACHE:
        c_time, c_data = _BADGES_CACHE[user_id]
        if now - c_time < _BADGES_CACHE_TTL:
            return c_data

    earned_badges = []
    # 1. Query normalized user_achievements table
    try:
        res = client.table('user_achievements').select('*').eq('user_id', user_id).execute()
        if res.data:
            name_to_slug = {v['name'].lower(): k for k, v in BADGE_DEFINITIONS.items()}
            for row in res.data:
                b_name = row.get('badge_name') or ''
                slug = name_to_slug.get(b_name.lower()) or b_name.lower().replace(' ', '_')
                b_def = BADGE_DEFINITIONS.get(slug, {
                    'slug': slug,
                    'name': b_name,
                    'icon': row.get('badge_icon') or '🎖️',
                    'rarity': 'Campus',
                    'description': 'Campus recognition badge'
                })
                earned_badges.append({
                    **b_def,
                    'earned_at': row.get('unlocked_at'),
                    'college_id': None,
                    'claimed_by_username': None
                })
            _BADGES_CACHE[user_id] = (now, earned_badges)
            return earned_badges
    except Exception as e:
        log.debug(f"[Gamification] user_achievements query: {e}")

    _BADGES_CACHE[user_id] = (now, earned_badges)

    # Guarantee every user starts with at least the starter badge
    has_starter = any(b.get('slug') == 'starter_scholar' for b in earned_badges)
    if not has_starter and 'starter_scholar' in BADGE_DEFINITIONS:
        starter_meta = {
            **BADGE_DEFINITIONS['starter_scholar'],
            'earned_at': datetime.now(timezone.utc).isoformat(),
            'college_id': None,
            'claimed_by_username': None
        }
        earned_badges.insert(0, starter_meta)
        _BADGES_CACHE[user_id] = (now, earned_badges)
        try:
            award_badge(user_id, 'starter_scholar')
        except Exception:
            pass

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
            # Calculate remaining Top 10 spots for this college
            member_cnt_res = client.table('profiles').select('id', count='exact').eq('college_id', college_id).execute()
            current_members = member_cnt_res.count or len(member_cnt_res.data or [])
            top10_remaining = max(0, 10 - current_members)
        except Exception as e:
            log.debug(f"[Gamification] member count lookup: {e}")

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
    """Award a badge to user_achievements."""
    if badge_slug not in BADGE_DEFINITIONS or not user_id:
        return False

    client = _get_client()
    if not client:
        return False

    b_meta = BADGE_DEFINITIONS.get(badge_slug, {})
    b_name = b_meta.get('name', badge_slug.replace('_', ' ').title())
    b_icon = b_meta.get('icon', '🏅')
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        # Check if already claimed in user_achievements
        existing = client.table('user_achievements').select('id') \
            .eq('user_id', user_id).eq('badge_name', b_name).limit(1).execute()
        if existing.data:
            return True

        payload = {
            'user_id': user_id,
            'badge_name': b_name,
            'badge_icon': b_icon,
            'unlocked_at': now_iso
        }
        client.table('user_achievements').insert(payload).execute()

        try:
            from methods.supabase_helper import log_notification
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

        _BADGES_CACHE.pop(user_id, None)
        return True
    except Exception as e:
        log.debug(f"[Gamification] award_badge error: {e}")
        return False


def record_user_activity(user_id: str, activity_type: str, metadata: Optional[Dict] = None, college_id: Optional[str] = None):
    """
    Scalable event-driven gamification pipeline:
    - Ingests user actions (search, upload, etc.)
    - Records activity in user_activities with non-blocking fallback
    - Triggers badge evaluation & real-time unlock notifications
    """
    if not user_id or not activity_type:
        return

    client = _get_client()
    if not client:
        return

    now_iso = datetime.now(timezone.utc).isoformat()
    meta = metadata or {}

    # 1. Log activity to user_activities for analytics & milestone triggers
    try:
        client.table('user_activities').insert({
            'user_id': user_id,
            'activity_type': activity_type,
            'metadata': meta,
            'created_at': now_iso
        }).execute()
    except Exception as e:
        log.debug(f"[Gamification] user_activities log (non-fatal): {e}")

    # 2. Trigger activity badges
    if activity_type == 'search':
        # Immediate milestone: first search query award
        award_badge(user_id, 'knowledge_seeker', college_id=college_id, metadata=meta)

        # Milestone: 10+ searches award Master Researcher
        try:
            res = client.table('user_activities').select('id', count='exact') \
                .eq('user_id', user_id).eq('activity_type', 'search').execute()
            count = res.count or len(res.data or [])
            if count >= 10:
                award_badge(user_id, 'master_researcher', college_id=college_id, metadata={'total_searches': count})
        except Exception:
            pass


def get_college_ambassador_status(college_id: str) -> Dict[str, Any]:
    """Get ambassador unlocking status and progress for a college."""
    client = _get_client()
    if not client or not college_id:
        return {'is_unlocked': False, 'approved_uploads': 0, 'required': 3, 'founding_ambassador': None}

    try:
        # Check approved uploads count
        docs_res = client.table('documents').select('id', count='exact') \
            .eq('college_id', college_id).eq('status', 'approved').limit(10).execute()
        approved_count = docs_res.count or len(docs_res.data or [])

        # Check existing founding ambassador from profiles
        founding_user = None
        amb_res = client.table('profiles').select('id, full_name, email') \
            .eq('college_id', college_id).order('reputation_score', desc=True).limit(1).execute()
        if amb_res.data:
            p = amb_res.data[0]
            founding_user = {
                'id': p.get('id'),
                'name': p.get('full_name') or (p.get('email', '').split('@')[0]) or 'Campus Lead'
            }

        return {
            'is_unlocked': approved_count >= 1,
            'approved_uploads': approved_count,
            'required': 3,
            'remaining_to_unlock': max(0, 3 - approved_count),
            'founding_ambassador': founding_user
        }
    except Exception as e:
        log.debug(f"[Gamification] get_college_ambassador_status fallback: {e}")
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
    except Exception as e:
        log.warning(f"[Gamification] on_document_approved error: {e}")
