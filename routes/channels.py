"""
Creator Channels Blueprint (Phase 1)
Supports personalized channels: abhihub.com/c/<handle>
Allows educators to showcase and monetize their notes, link from YouTube/Telegram,
and track notes analytics with "Powered by AbhiHub" branding.
"""
import logging
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, session, abort
from routes.auth import auth_required
from methods.channel_service import (
    get_channel_by_handle,
    get_channel_by_user_id,
    save_user_channel,
    increment_channel_views,
    get_channel_notes,
    sanitize_handle
)

channels_bp = Blueprint('channels', __name__)
logger = logging.getLogger(__name__)


@channels_bp.route('/c/<handle>')
def public_channel_view(handle):
    """Public creator channel page accessible from YouTube / Telegram / Instagram links."""
    channel = get_channel_by_handle(handle)
    if not channel:
        return render_template('channel_view.html', channel=None, handle=handle, notes=[]), 404

    # Increment view count
    increment_channel_views(channel.get('id'), channel.get('views_count', 0))

    # Fetch notes belonging to this creator
    notes = get_channel_notes(channel.get('user_id'))
    
    # Calculate channel stats
    total_notes = len(notes)
    total_views = sum(n.get('views', 0) for n in notes)

    is_owner = False
    current_user = session.get('user', {})
    if current_user and str(current_user.get('uid')) == str(channel.get('user_id')):
        is_owner = True

    return render_template(
        'channel_view.html',
        channel=channel,
        notes=notes,
        total_notes=total_notes,
        total_views=total_views,
        is_owner=is_owner
    )


@channels_bp.route('/channel/studio')
@auth_required
def channel_studio():
    """Creator Studio to manage the user's single channel and view shareable links."""
    user = session.get('user', {})
    user_id = user.get('uid')

    channel = get_channel_by_user_id(user_id)
    notes = get_channel_notes(user_id) if user_id else []

    return render_template(
        'channel_studio.html',
        user=user,
        channel=channel,
        notes=notes
    )


@channels_bp.route('/api/channel/save', methods=['POST'])
@auth_required
def api_save_channel():
    """Create or update user's single channel."""
    user = session.get('user', {})
    user_id = user.get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    title = str(data.get('title', '')).strip()
    handle = str(data.get('handle', '')).strip()
    bio = str(data.get('bio', '')).strip()
    avatar_url = str(data.get('avatar_url', '')).strip()
    banner_url = str(data.get('banner_url', '')).strip()

    social_links = {
        'youtube': str(data.get('youtube', '')).strip(),
        'telegram': str(data.get('telegram', '')).strip(),
        'instagram': str(data.get('instagram', '')).strip()
    }

    success, result = save_user_channel(
        user_id=user_id,
        title=title,
        handle=handle,
        bio=bio,
        avatar_url=avatar_url,
        banner_url=banner_url,
        social_links=social_links
    )

    if not success:
        return jsonify({'success': False, 'error': result}), 400

    return jsonify({
        'success': True,
        'handle': result,
        'channel_url': url_for('channels.public_channel_view', handle=result, _external=True)
    })


# ---------------------------------------------------------------------
# Creator Hub & Customer CRM
# ---------------------------------------------------------------------
@channels_bp.route('/creator/hub')
@channels_bp.route('/creator-hub')
@channels_bp.route('/creater-hub')
@channels_bp.route('/creater/hub')
@auth_required
def creator_hub():
    """Creator Hub: Top customers leaderboard, revenue metrics, and community broadcasts."""
    user = session.get('user', {})
    user_id = user.get('uid')

    from methods.creator_crm_service import (
        get_creator_customer_stats,
        get_creator_top_customers,
        get_creator_broadcasts
    )

    stats = get_creator_customer_stats(user_id) if user_id else {}
    customers = get_creator_top_customers(user_id, limit=25) if user_id else []
    broadcasts = get_creator_broadcasts(user_id, limit=10) if user_id else []

    channel = get_channel_by_user_id(user_id) if user_id else None

    return render_template(
        'p_creator_hub.html',
        user=user,
        channel=channel,
        stats=stats,
        customers=customers,
        broadcasts=broadcasts
    )


@channels_bp.route('/api/creator/customers', methods=['GET'])
@auth_required
def api_creator_customers():
    """API to fetch top customers with metrics."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    from methods.creator_crm_service import get_creator_top_customers, get_creator_customer_stats
    limit = int(request.args.get('limit', 20))
    customers = get_creator_top_customers(user_id, limit=limit)
    stats = get_creator_customer_stats(user_id)
    return jsonify({'success': True, 'customers': customers, 'stats': stats})


@channels_bp.route('/api/creator/broadcast', methods=['POST'])
@auth_required
def api_create_broadcast():
    """Publish announcement to buyers."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    title = str(data.get('title', '')).strip()
    msg = str(data.get('message', '')).strip()
    channel_url = str(data.get('channel_url', '')).strip()
    tier = str(data.get('target_tier', 'all')).strip()

    if not title or not msg:
        return jsonify({'success': False, 'error': 'Title and message are required.'}), 400

    from methods.creator_crm_service import create_creator_broadcast
    res = create_creator_broadcast(user_id, title=title, message=msg, channel_url=channel_url, target_tier=tier)
    if not res.get('success'):
        return jsonify(res), 400
    return jsonify(res)

