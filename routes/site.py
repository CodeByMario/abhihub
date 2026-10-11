from flask import Blueprint, render_template, session, redirect, url_for, request
from routes.seo import sitemap_page
from routes.auth import auth_required

site_bp = Blueprint('site', __name__)


@site_bp.route('/about')
@sitemap_page(priority="0.85")
def about():
    """About page"""
    return render_template('about.html')


@site_bp.route('/open-source')
@sitemap_page(priority="0.85")
def open_source():
    """Open source page"""
    return render_template('open_source.html')


@site_bp.route('/features-tour')
@sitemap_page(priority="0.85")
def features_tour():
    return render_template('features.html')


@site_bp.route('/terms')
@sitemap_page(priority="0.80", changefreq="monthly")
def terms():
    return render_template('terms.html')


@site_bp.route('/privacy')
@sitemap_page(priority="0.80", changefreq="monthly")
def privacy():
    return render_template('privacy.html')


@site_bp.route('/contribute')
@sitemap_page(priority="0.95", changefreq="weekly")
def contribute_page():
    """Public SEO-optimized contributor guide, rank progression & perks page."""
    return render_template('contribute.html')


@site_bp.route('/earn-with-abhihub')
def earn_with_abhihub_legacy_redirect():
    """301 permanent redirect from deprecated /earn-with-abhihub to /contribute."""
    return redirect(url_for('site.contribute_page'), code=301)


@site_bp.route('/dmca')
@sitemap_page(priority="0.70", changefreq="monthly")
def dmca():
    """DMCA and Academic Copyright Policy page."""
    return render_template('dmca.html')


@site_bp.route('/help')
@sitemap_page()
def help_center():
    return render_template('help.html')


@site_bp.route('/join')
@sitemap_page()
def join_team():
    """Collaborator recruitment landing page"""
    return render_template('join.html')


@site_bp.route('/team')
@sitemap_page()
def team():
    """Team page"""
    return render_template('team.html')


@site_bp.route('/contact')
@sitemap_page()
def contact():
    """Contact page"""
    return render_template('contact.html')


@site_bp.route('/support')
@auth_required
def support():
    default_name = session.get('user', {}).get('name', '') if 'user' in session else ''
    return render_template('site/support.html', default_name=default_name)


@site_bp.route('/')
@sitemap_page(priority="1.00", changefreq="daily")
def features():
    """Root route - public landing page with crawlable university, subject, and resource hubs"""
    if 'user' in session:
        if request.headers.get('Sec-Fetch-Dest') == 'iframe':
            return redirect(url_for('app_pages.dashboard'))
        return redirect(url_for('app_pages.app_shell'))
    
    import logging
    from methods.supabase_helper import get_all_colleges, get_all_branches, init_supabase
    from routes.seo import slugify
    from data.pricing import extract_document_pricing

    colleges_res = get_all_colleges()
    all_colleges = colleges_res.get('data', []) if colleges_res.get('success') else []
    
    for c in all_colleges:
        c['slug'] = slugify(c.get('abbreviation') or c.get('name'))
        
    branches_res = get_all_branches()
    branches = branches_res.get('data', []) if branches_res.get('success') else []
    for b in branches:
        b['slug'] = slugify(b.get('abbreviation') or b.get('name'))

    recent_docs = []
    try:
        client = init_supabase()
        if client:
            res = client.table('documents')\
                .select('id, title, document_category, created_at, view_count, description, college:colleges(name, abbreviation), department:departments(name, abbreviation), subject:subjects(name)')\
                .eq('status', 'approved')\
                .order('created_at', desc=True)\
                .limit(12)\
                .execute()
            for doc in (res.data or []):
                c_data = doc.get('college') or {}
                d_data = doc.get('department') or {}
                s_data = doc.get('subject') or {}
                c_slug = slugify(c_data.get('abbreviation') or c_data.get('name') or 'college')
                d_slug = slugify(d_data.get('abbreviation') or d_data.get('name') or 'dept')
                s_slug = slugify(s_data.get('name') or 'subject')
                t_slug = slugify(doc.get('title') or 'file')
                doc['canonical_slug'] = f"{c_slug}-{d_slug}-{s_slug}-{t_slug}-{doc.get('id')}"
                doc['pricing'] = extract_document_pricing(doc)
                recent_docs.append(doc)
    except Exception as e:
        logging.warning(f"Error fetching landing page docs: {e}")

    from data.tea_supporters import get_recent_tea_supporters
    tea_supporters = get_recent_tea_supporters(8)

    return render_template(
        'site/landing.html',
        colleges=all_colleges[:8],
        branches=branches[:8],
        recent_docs=recent_docs,
        tea_supporters=tea_supporters
    )


@site_bp.route("/logo")
def logo():
    from flask import send_file
    return send_file('static/images/logo.png', mimetype='image/png')


@site_bp.route('/offline')
def offline_page():
    return render_template('offline.html')


@site_bp.route('/payment')
def payment_page():
    import time
    import secrets
    from datetime import datetime
    from flask import request

    raw_amount = request.args.get('amount', '49')
    purpose = request.args.get('purpose', 'AbhiHub Support / Credits')
    doc_id = request.args.get('doc_id', '').strip()
    if not doc_id and 'Document-' in purpose:
        doc_id = purpose.split('Document-')[-1].strip()

    try:
        amount = f"{float(raw_amount):.2f}"
        if float(amount) <= 0 or float(amount) > 50000:
            amount = "49.00"
    except (ValueError, TypeError):
        amount = "49.00"

    order_id = f"AH{int(time.time())}{secrets.token_hex(2).upper()}"
    purchase_date = datetime.now().strftime("%d %b %Y, %I:%M %p")

    doc_info = None
    if doc_id:
        try:
            from methods.supabase_helper import get_document_by_id_rich
            doc_res = get_document_by_id_rich(doc_id)
            if doc_res.get('success'):
                doc_info = doc_res.get('data')
        except Exception:
            pass

    return render_template(
        'payment.html',
        amount=amount,
        purpose=purpose,
        order_id=order_id,
        doc_id=doc_id,
        doc_info=doc_info,
        purchase_date=purchase_date
    )


@site_bp.route('/payment/receipt', methods=['GET'])
def payment_receipt_page():
    """Valid feedback and receipt page for completed or failed PhonePe payments."""
    from flask import request
    order_id = request.args.get('order_id', '').strip()
    status = request.args.get('status', 'success')
    doc_id = request.args.get('doc_id', '').strip()
    raw_amount = request.args.get('amount', '49.00')
    error_msg = request.args.get('error', '').strip()

    from data.transactions import get_transaction_record
    rec = get_transaction_record(order_id)
    if rec and rec.get('amount'):
        amount = f"{float(rec['amount']):.2f}"
    else:
        amount = raw_amount

    doc_info = None
    if doc_id:
        try:
            from methods.supabase_helper import get_document_by_id_rich
            doc_res = get_document_by_id_rich(doc_id)
            if doc_res.get('success'):
                doc_info = doc_res.get('data')
        except Exception:
            pass

    is_paid = (status == 'success')
    admin_notes = (rec.get('admin_notes', '') if rec else '')
    is_credits = (request.args.get('is_credits') == '1' or 'Credits-' in admin_notes or 'pack=' in admin_notes or 'credits' in admin_notes.lower())
    pack_size = request.args.get('pack') or 0
    if not pack_size and is_credits:
        for part in admin_notes.split(';'):
            if part.startswith('pack='):
                try: pack_size = int(part.replace('pack=', '').strip())
                except: pass
            elif part.startswith('purpose=Credits-'):
                try: pack_size = int(part.replace('purpose=Credits-', '').split('-')[0].strip())
                except: pass
        if not pack_size:
            try: pack_size = int(float(amount) / 2)
            except: pack_size = 50

    if is_credits:
        purpose = f"Study View Credits ({pack_size} Views)"
    elif doc_id:
        purpose = "Document Access"
    else:
        purpose = "Community Support Contribution"

    return render_template(
        'payment_receipt.html',
        order_id=order_id,
        amount=amount,
        doc_id=doc_id,
        doc_info=doc_info,
        purpose=purpose,
        is_paid=is_paid,
        is_credits=is_credits,
        pack_size=pack_size,
        error_msg=error_msg
    )

