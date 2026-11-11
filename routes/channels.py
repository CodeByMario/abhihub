"""
Creator Channels Blueprint (Phase 1)
Supports personalized channels: www.abhihub.edu.eu.org/c/<handle>
Allows educators to showcase and monetize their notes, link from YouTube/Telegram,
and track notes analytics with "Powered by AbhiHub" branding.
"""
import logging
from flask import Blueprint, request, render_template, redirect, url_for, jsonify, session, abort, make_response
from routes.auth import auth_required
from methods.channel_service import (
    auto_index_channel,
    generate_channel_og_image,
    get_channel_by_handle,
    get_channel_by_user_id,
    save_user_channel,
    increment_channel_views,
    get_channel_notes,
    sanitize_handle,
    get_preview_notes
)

channels_bp = Blueprint('channels', __name__)
logger = logging.getLogger(__name__)

@channels_bp.route('/preview')
@channels_bp.route('/preview/<slug>')
def educator_preview(slug=None):
    slug = slug or request.args.get('c') or request.args.get('channel') or 'study_with_wasu'
    real_notes = get_preview_notes(slug)
    return render_template('educator_preview.html', slug=slug, real_notes=real_notes)



@channels_bp.route('/c/<handle>')
def public_channel_view(handle):
    """Public creator channel page accessible from YouTube / Telegram / Instagram links."""
    channel = get_channel_by_handle(handle)
    if not channel:
        clean_h = sanitize_handle(handle)
        from methods.channel_service import ALL_LEADS, get_preview_notes
        if clean_h in ALL_LEADS:
            lead = ALL_LEADS[clean_h]
            channel = {
                'id': f"lead_{clean_h}",
                'handle': lead['handle'],
                'title': lead['title'],
                'bio': lead['bio'],
                'avatar_url': lead.get('avatar'),
                'banner_url': lead.get('banner'),
                'social_links': lead.get('socials', {}),
                'views_count': lead.get('views', 1200),
                'rating': lead.get('rating', 4.9),
                'verified': True,
                'user_id': None
            }
            notes = get_preview_notes(clean_h)
            total_notes = len(notes)
            total_views = sum(n.get('views', 0) for n in notes) or channel['views_count']
            seo_title = f"{channel['title']} (@{channel['handle']}) - Notes & Exam Materials | AbhiHub"
            seo_desc = f"Study verified university notes, syllabus guides, and previous question papers from {channel['title']} (@{channel['handle']}) on AbhiHub."
            seo_keywords = f"{channel['title']}, {channel['handle']}, engineering notes, exam prep, AbhiHub channel"
            canonical_url = url_for('channels.public_channel_view', handle=channel['handle'], _external=True)
            og_image = url_for('channels.channel_og_image', handle=channel['handle'], _external=True)
            if not og_image.endswith('.png'):
                og_image += '.png'
            return render_template(
                'channel_view.html',
                channel=channel,
                notes=notes,
                total_notes=total_notes,
                total_views=total_views,
                is_owner=False,
                seo_title=seo_title,
                seo_description=seo_desc,
                seo_keywords=seo_keywords,
                canonical_url=canonical_url,
                og_image=og_image
            )
        return render_template(
            'channel_view.html',
            channel=None,
            handle=handle,
            notes=[],
            noindex=True,
            seo_title='Channel Not Found (404) | AbhiHub',
            seo_description='The creator channel you are looking for does not exist on AbhiHub.'
        ), 404

    # Increment view count
    increment_channel_views(channel.get('id'), channel.get('views_count', 0))

    # Fetch notes belonging to this creator
    notes = get_channel_notes(channel.get('user_id'))
    if not notes:
        # Fallback to preview notes so prospect channels always showcase documents
        notes = get_preview_notes(handle)
    
    # Calculate channel stats
    total_notes = len(notes)
    total_views = sum(n.get('views', 0) for n in notes)

    is_owner = False
    current_user = session.get('user', {})
    if current_user and str(current_user.get('uid')) == str(channel.get('user_id')):
        is_owner = True

    seo_title = f"{channel['title']} (@{channel['handle']}) - Notes & Exam Materials | AbhiHub"
    seo_desc = f"Study verified university notes, syllabus guides, and previous question papers from {channel['title']} (@{channel['handle']}) on AbhiHub."
    seo_keywords = f"{channel['title']}, {channel['handle']}, engineering notes, exam prep, AbhiHub channel"
    canonical_url = url_for('channels.public_channel_view', handle=channel['handle'], _external=True)
    og_image = url_for('channels.channel_og_image', handle=channel['handle'], _external=True)
    if not og_image.endswith('.png'):
        og_image += '.png'

    return render_template(
        'channel_view.html',
        channel=channel,
        notes=notes,
        total_notes=total_notes,
        total_views=total_views,
        is_owner=is_owner,
        seo_title=seo_title,
        seo_description=seo_desc,
        seo_keywords=seo_keywords,
        canonical_url=canonical_url,
        og_image=og_image
    )


@channels_bp.route('/c/<handle>/og-image.png')
@channels_bp.route('/c/<handle>/og-image')
def channel_og_image(handle):
    """Generates a custom branded 1200x630 OpenGraph preview image for social platforms."""
    channel = get_channel_by_handle(handle)
    if not channel:
        from methods.channel_service import ALL_LEADS, sanitize_handle
        clean_h = sanitize_handle(handle)
        if clean_h in ALL_LEADS:
            lead = ALL_LEADS[clean_h]
            channel = {
                'title': lead['title'],
                'handle': lead['handle'],
                'bio': lead['bio'],
                'avatar_url': lead.get('avatar')
            }
        else:
            channel = {'title': handle, 'handle': handle, 'bio': 'Creator on AbhiHub'}

    img_bytes = generate_channel_og_image(channel)
    resp = make_response(img_bytes)
    resp.headers['Content-Type'] = 'image/png'
    resp.headers['Cache-Control'] = 'public, max-age=86400, stale-while-revalidate=604800'
    return resp


@channels_bp.route('/channel/studio')
@auth_required
def channel_studio():
    """Creator Studio to manage the user's single channel and view shareable links."""
    user = session.get('user', {})
    user_id = user.get('uid')

    channel = get_channel_by_user_id(user_id)
    all_notes = get_channel_notes(user_id) if user_id else []

    # Pagination for uploaded materials (6 cards per page)
    page = max(1, int(request.args.get('page', 1)))
    per_page = 6
    total_notes = len(all_notes)
    total_pages = max(1, (total_notes + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
    paginated_notes = all_notes[(page - 1) * per_page : page * per_page]

    return render_template(
        'channel_studio.html',
        user=user,
        channel=channel,
        notes=paginated_notes,
        all_notes=all_notes,
        all_notes_count=total_notes,
        page=page,
        total_pages=total_pages
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

    auto_index_channel(result)

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
    """
    Creator Hub: Real earnings dashboard, file monetization, subject grouping,
    and customer supporter ledger (strictly customer names only).
    """
    from datetime import datetime, timezone, timedelta
    user = session.get('user', {})
    user_id = user.get('uid')

    from methods.creator_crm_service import (
        get_creator_customer_stats,
        get_creator_top_customers,
        get_creator_broadcasts,
        get_creator_products_with_sales
    )
    from methods.wallet_service import get_creator_wallet
    from methods.payment_engine import engine

    stats = get_creator_customer_stats(user_id) if user_id else {}
    broadcasts = get_creator_broadcasts(user_id, limit=10) if user_id else []
    channel = get_channel_by_user_id(user_id) if user_id else None

    # Real Wallet & Financial Data (File Sales Sole Source)
    wallet_info = get_creator_wallet(user_id) if user_id else {}
    wallet = wallet_info.get('wallet', {})
    ledger = wallet_info.get('ledger', [])
    all_payouts = wallet_info.get('payouts', [])

    # Real Products, Grouping & Sales
    products_data = get_creator_products_with_sales(user_id) if user_id else {}
    all_products = products_data.get('products', [])
    grouped_products = products_data.get('grouped', {})
    total_sales_count = products_data.get('total_sales_count', 0)
    doc_gross_sales = products_data.get('gross_sales', 0.0)

    # Customer Supporters with Pagination (10 per page)
    all_customers = get_creator_top_customers(user_id, limit=300) if user_id else []
    c_page = max(1, int(request.args.get('c_page', 1)))
    c_per_page = 10
    total_customers_count = len(all_customers)
    total_customer_pages = max(1, (total_customers_count + c_per_page - 1) // c_per_page)
    if c_page > total_customer_pages:
        c_page = total_customer_pages
    customers = all_customers[(c_page - 1) * c_per_page : c_page * c_per_page]

    # Products Pagination (10 per page)
    p_page = max(1, int(request.args.get('p_page', 1)))
    p_per_page = 10
    total_products_count = len(all_products)
    total_product_pages = max(1, (total_products_count + p_per_page - 1) // p_per_page)
    if p_page > total_product_pages:
        p_page = total_product_pages
    products = all_products[(p_page - 1) * p_per_page : p_page * p_per_page]

    # Re-group paginated products
    paginated_grouped = {}
    for p in products:
        paginated_grouped.setdefault(p['group'], []).append(p)

    # Payouts Pagination (10 per page)
    po_page = max(1, int(request.args.get('po_page', 1)))
    po_per_page = 10
    total_payouts_count = len(all_payouts)
    total_payout_pages = max(1, (total_payouts_count + po_per_page - 1) // po_per_page)
    if po_page > total_payout_pages:
        po_page = total_payout_pages
    payouts = all_payouts[(po_page - 1) * po_per_page : po_page * po_per_page]

    # Reconciled Balances
    withdrawable = float(wallet.get('withdrawable_balance', 0.0))
    pending = float(wallet.get('pending_balance', 0.0))
    total_withdrawn = float(wallet.get('total_withdrawn', 0.0))
    comm_pct = float(wallet.get('creator_commission_pct', 90.0))

    # Real Financial Metrics
    if doc_gross_sales > 0:
        gross_sales = doc_gross_sales
    elif (withdrawable + pending + total_withdrawn) > 0:
        gross_sales = round((withdrawable + pending + total_withdrawn) / (comm_pct / 100.0), 2)
    else:
        gross_sales = 0.0

    platform_fee = round(gross_sales * (1.0 - (comm_pct / 100.0)), 2)
    tds_tax = round(gross_sales * 0.01, 2)  # 1% TDS under Section 194-O
    net_earnings = max(0.0, round(gross_sales - platform_fee - tds_tax, 2))
    if net_earnings == 0 and (withdrawable + pending) > 0:
        net_earnings = round(withdrawable + pending, 2)

    # Next Payout Schedule & KYC details
    kyc = engine.get_kyc(user_id) if user_id else None
    destination_display = "Bank / UPI (KYC pending)"
    if kyc and kyc.get('is_verified'):
        pref = kyc.get('preferred_method', 'upi')
        if pref == 'upi' and kyc.get('upi_id'):
            destination_display = f"UPI •••• {kyc.get('upi_id')}"
        elif kyc.get('account_number'):
            b_name = kyc.get('bank_name') or 'Bank'
            destination_display = f"{b_name} {kyc.get('account_number')}"

    # Calculate next scheduled payout date (coming Sunday or T+3)
    today = datetime.now()
    days_ahead = (6 - today.weekday()) % 7
    if days_ahead <= 1:
        days_ahead += 7
    next_payout_date = (today + timedelta(days=days_ahead)).strftime('%a, %d %b %Y')

    return render_template(
        'p_creator_hub.html',
        user=user,
        channel=channel,
        stats=stats,
        customers=customers,
        broadcasts=broadcasts,
        wallet=wallet,
        ledger=ledger,
        payouts=payouts,
        products=products,
        grouped_products=paginated_grouped if paginated_grouped else grouped_products,
        all_products_count=total_products_count,
        p_page=p_page,
        total_product_pages=total_product_pages,
        c_page=c_page,
        total_customer_pages=total_customer_pages,
        total_customers_count=total_customers_count,
        po_page=po_page,
        total_payout_pages=total_payout_pages,
        total_payouts_count=total_payouts_count,
        total_sales_count=total_sales_count,
        gross_sales=gross_sales,
        platform_fee=platform_fee,
        tds_tax=tds_tax,
        net_earnings=net_earnings,
        withdrawable=withdrawable,
        pending=pending,
        total_withdrawn=total_withdrawn,
        destination_display=destination_display,
        next_payout_date=next_payout_date,
        kyc=kyc
    )


@channels_bp.route('/api/creator/customers', methods=['GET'])
@auth_required
def api_creator_customers():
    """API to fetch top customers with metrics (strictly name only, no PII)."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    from methods.creator_crm_service import get_creator_top_customers, get_creator_customer_stats
    limit = int(request.args.get('limit', 20))
    customers = get_creator_top_customers(user_id, limit=limit)
    stats = get_creator_customer_stats(user_id)
    return jsonify({'success': True, 'customers': customers, 'stats': stats})


@channels_bp.route('/api/creator/product/monetize', methods=['POST'])
@auth_required
def api_creator_product_monetize():
    """Update price and is_paid for a creator's uploaded document."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    doc_id = data.get('doc_id')
    is_paid = bool(data.get('is_paid'))
    price = float(data.get('price') or 0.0)

    if not doc_id:
        return jsonify({'success': False, 'error': 'Document ID is required.'}), 400

    from methods.creator_crm_service import update_document_monetization
    res = update_document_monetization(user_id, doc_id, is_paid, price)
    if not res.get('success'):
        return jsonify(res), 400
    return jsonify(res)


@channels_bp.route('/api/creator/payout/request', methods=['POST'])
@auth_required
def api_creator_payout_request():
    """Trigger a payout withdrawal request to verified bank/UPI."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form.to_dict() or {}
    amount = float(data.get('amount') or 0.0)
    if amount <= 0:
        return jsonify({'success': False, 'error': 'Invalid withdrawal amount.'}), 400

    from methods.wallet_service import request_withdrawal
    ok, err_or_res = request_withdrawal(user_id, amount)
    if not ok:
        return jsonify({'success': False, 'error': err_or_res}), 400
    return jsonify({'success': True, 'message': 'Payout request submitted successfully.'})

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



@channels_bp.route('/api/channel/fetch-youtube-meta', methods=['POST'])
def api_fetch_youtube_meta():
    """Extracts logo, banner, and channel name directly from a public YouTube channel URL."""
    data = request.get_json(silent=True) or {}
    youtube_url = (data.get('youtube_url') or '').strip()
    if not youtube_url:
        return jsonify({'success': False, 'error': 'YouTube URL or handle is required'}), 400

    from methods.channel_service import fetch_youtube_branding
    result = fetch_youtube_branding(youtube_url)
    return jsonify(result)
