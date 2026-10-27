import os
import re
import json
import logging
from datetime import datetime
from flask import (
    Blueprint, render_template, session, request, redirect, url_for,
    flash, current_app, jsonify
)
from routes.auth import auth_required
from methods.supabase_helper import (
    get_student_profile, get_all_colleges, get_all_branches,
    create_or_update_student_profile, get_user_file_history,
    get_reputation_stats, get_user_notifications, get_peer_recommended_files,
    get_dashboard_summary_data, init_supabase
)

app_pages_bp = Blueprint('app_pages', __name__)


@app_pages_bp.route('/dashboard')
@auth_required
def dashboard():
    """Dashboard for authenticated users (cached summary architecture)."""
    import app

    user_info = session.get('user', {})
    current_user_id = user_info.get('uid')

    # 1. Fetch user profile & college
    user_data = None
    file_history = []
    college_name = ''

    if 'user' in session:
        user_name = user_info.get('name', '')
        user_email = user_info.get('email', '')
        user_id = user_info.get('uid', '')

        # Fast indexed query for user's own uploads
        user_files = []
        user_notes_count = 0
        user_papers_count = 0
        user_practicals_count = 0
        user_subjects = set()
        if user_id:
            try:
                client = init_supabase()
                if client:
                    u_res = client.table('documents').select(
                        'id, title, document_category, file_type, created_at, view_count, status, subjects(name)'
                    ).eq('uploader_id', user_id).order('created_at', desc=True).limit(50).execute()
                    for d in (u_res.data or []):
                        cat = (d.get('document_category') or '').lower()
                        ft = (d.get('file_type') or '').lower()
                        if cat in ('notes', 'note', 'imp questions', 'imp_questions') or ft == 'notes':
                            user_notes_count += 1
                        elif cat in ('pyq', 'papers', 'paper') or ft in ('pyq', 'papers'):
                            user_papers_count += 1
                        elif cat == 'practical' or ft == 'practical':
                            user_practicals_count += 1
                        subj = (d.get('subjects') or {}).get('name') if isinstance(d.get('subjects'), dict) else ''
                        if subj:
                            user_subjects.add(subj)
                        user_files.append({
                            'record_id': d.get('id'),
                            'file-name': d.get('title') or 'Document',
                            'type': cat or 'papers',
                            'subject': subj or 'General',
                            'view_count': d.get('view_count', 0),
                            'date': (d.get('created_at') or '')[:10]
                        })
            except Exception as e:
                logging.warning(f"[Dashboard] Error fetching user uploads: {e}")
        user_uploads_count = len(user_files)

        history_result = get_user_file_history(user_email=user_email, user_id=user_id, limit=12)
        file_history = history_result.get('data', []) if history_result.get('success') else []

        try:
            profile_data = session.get('profile')
            if not profile_data or not profile_data.get('college_id'):
                profile_res = get_student_profile(user_id)
                profile_data = profile_res.get('data', {}) if profile_res.get('success') else {}
                if profile_data:
                    session['profile'] = profile_data
            college_name = profile_data.get('college_name') or ''

            if not profile_data or not profile_data.get('college_id'):
                flash("Welcome to AbhiHub! Please complete your profile to access all personalized features.", "warning")
                return redirect(url_for('app_pages.settings'))

            rank_list = app.calculate_user_ranks()
            _rank_lookup = {e['uploader_id']: (str(i + 1), e.get('points', 0)) for i, e in enumerate(rank_list)}
            global_rank = _rank_lookup.get(user_id, ('-', 0))[0]
            computed_score = _rank_lookup.get(user_id, ('-', 0))[1]

            rep_stats = session.get('rep_stats')
            if not rep_stats:
                rep_stats = get_reputation_stats(user_id) or {}
                if rep_stats.get('success'):
                    session['rep_stats'] = rep_stats
            students_helped = rep_stats.get('students_helped', 0) if rep_stats.get('success') else 0
            badges = rep_stats.get('badges', []) if rep_stats.get('success') else []
        except Exception as e:
            logging.error(f"[Dashboard] Error fetching profile/rank data: {e}")
            profile_data = {}
            global_rank = '-'
            computed_score = 0
            students_helped = 0
            badges = []

        user_data = {
            'name': user_name,
            'email': user_info.get('email', ''),
            'uploads_count': user_uploads_count,
            'notes_count': user_notes_count,
            'papers_count': user_papers_count,
            'practicals_count': user_practicals_count,
            'subjects_contributed': len(user_subjects),
            'user_files': user_files[:10],
            'role': profile_data.get('role', 'student') if profile_data else 'student',
            'reputation_score': max(computed_score, profile_data.get('reputation_score', 0)) if profile_data else computed_score,
            'referral_credits': profile_data.get('referral_credits', 0) if profile_data else 0,
            'referral_count': profile_data.get('referral_count', 0) if profile_data else 0,
            'rank_title': profile_data.get('rank_title', 'Beginner') if profile_data else 'Beginner',
            'is_verified': profile_data.get('is_verified', False) if profile_data else False,
            'subscription_tier': profile_data.get('subscription_tier', 'free') if profile_data else 'free',
            'global_rank': global_rank,
            'students_helped': students_helped,
            'badges': badges,
            'college_name': college_name,
            'college_id': profile_data.get('college_id') or '',
            'college_slug': profile_data.get('college_slug') or (profile_data.get('college_abbreviation') or '').lower() or re.sub(r'[^a-z0-9]+', '-', college_name.lower()).strip('-'),
            'branch_name': profile_data.get('branch_name') or '',
            'branch_id': profile_data.get('branch_id') or ''
        }

    if user_data is None:
        user_data = {}

    user_data.setdefault('paper_quota_remaining', app._get_quota().get('credits', 19))
    user_data.setdefault('students_helped', 0)
    user_data.setdefault('reputation_score', 0)
    user_data.setdefault('badges', [])
    user_data.setdefault('global_rank', '-')
    user_data.setdefault('rank_title', 'Beginner')
    user_data.setdefault('is_verified', False)
    user_data.setdefault('college_name', '')
    user_data.setdefault('subscription_tier', 'free')

    promo_context = {
        'remaining_views': user_data.get('paper_quota_remaining', 19) if user_data else 19,
        'students_helped': user_data.get('students_helped', 0) if user_data else 0,
        'reputation_score': user_data.get('reputation_score', 0) if user_data else 0,
        'upload_goal_month': 'May'
    }

    # 2. Pre-computed, memory-cached dashboard summary (zero heavy DB query loops)
    summary = get_dashboard_summary_data(college_name=college_name)
    paper_count = summary.get('counts', {}).get('papers', 0)
    notes_count = summary.get('counts', {}).get('notes', 0)
    top_subjects = summary.get('top_subjects', [])
    seo_keywords = "AbhiHub, GHRCE papers, engineering papers, " + ", ".join(top_subjects) + ", exam resources, study materials"

    relevant_papers = summary.get('relevant_papers', [])
    trending_papers = summary.get('trending_papers', [])
    recent_papers = summary.get('recent_papers', [])
    relevant_notes = summary.get('relevant_notes', [])
    trending_notes = summary.get('trending_notes', [])
    recent_notes = summary.get('recent_notes', [])
    recently_added_files = summary.get('recently_added_files', [])
    premium_files = summary.get('premium_files', [])
    top_authors = summary.get('top_authors', [])
    preview_pool = summary.get('preview_pool', [])

    # 3. Resolve recently viewed & peer recommended files
    file_pool = preview_pool + relevant_papers + trending_papers + relevant_notes + trending_notes
    file_lookup = {f.get('record_id'): f for f in file_pool if f.get('record_id')}
    user_viewed_ids = set()
    recently_viewed_files = []
    for h in file_history:
        did = h.get('document_id')
        if did and did not in user_viewed_ids:
            user_viewed_ids.add(did)
            if did in file_lookup:
                recently_viewed_files.append(file_lookup[did])
            else:
                recently_viewed_files.append({
                    'record_id': did,
                    'file-name': h.get('file_name', 'Document'),
                    'type': h.get('document_category', 'papers'),
                    'subject': 'Recent',
                    'view_count': 0,
                    'date': (h.get('accessed_at') or '')[:10],
                    'file-type': h.get('file_type', 'pdf')
                })

    recommended_files = []
    college_id = user_data.get('college_id') if user_data else ''
    branch_id = user_data.get('branch_id') if user_data else ''
    peer_doc_ids = get_peer_recommended_files(user_id=current_user_id, college_id=college_id, department_id=branch_id, limit=8) if current_user_id else []

    for pid in peer_doc_ids:
        if pid in file_lookup and pid not in user_viewed_ids:
            recommended_files.append(file_lookup[pid])

    if len(recommended_files) < 6:
        seen_rec_ids = {r.get('record_id') for r in recommended_files} | user_viewed_ids
        pool = relevant_papers + relevant_notes
        for item in pool:
            rid = item.get('record_id')
            if rid and rid not in seen_rec_ids:
                seen_rec_ids.add(rid)
                recommended_files.append(item)
                if len(recommended_files) >= 8:
                    break

    from data.tea_supporters import get_recent_feedbacks
    community_feedbacks = get_recent_feedbacks(limit=8)

    featured_channels = []
    try:
        from methods.channel_service import get_featured_channels
        featured_channels = get_featured_channels(limit=10)
    except Exception as e:
        logging.warning(f"[Dashboard] Featured channels error: {e}")

    return render_template(
        'app/dashboard.html',
        data=preview_pool,
        seo_keywords=seo_keywords,
        top_subjects=top_subjects,
        paper_count=paper_count,
        notes_count=notes_count,
        user_data=user_data,
        file_history=file_history,
        recently_viewed_files=recently_viewed_files,
        recommended_files=recommended_files,
        recently_added_files=recently_added_files,
        premium_files=premium_files,
        top_authors=top_authors,
        now=datetime.now(),
        promo_context=promo_context,
        relevant_papers=relevant_papers,
        trending_papers=trending_papers,
        recent_papers=recent_papers,
        relevant_notes=relevant_notes,
        trending_notes=trending_notes,
        recent_notes=recent_notes,
        community_feedbacks=community_feedbacks,
        featured_channels=featured_channels
    )


@app_pages_bp.route('/profile')
@auth_required
def profile():
    """Display user's own profile and account management in Settings."""
    return redirect(url_for('app_pages.settings'), code=301)


@app_pages_bp.route('/dashboard/profile')
@auth_required
def p_profile_redirect():
    return redirect(url_for('app_pages.settings'), code=301)


@app_pages_bp.route('/account', methods=['GET'])
@auth_required
def account():
    """Account route — redirect to canonical /settings."""
    return redirect(url_for('app_pages.settings'), code=301)


@app_pages_bp.route('/account/update', methods=['POST'])
@auth_required
def update_account():
    """Handle account profile updates"""
    user_info = session['user']
    user_id = user_info.get('uid')
    user_email = user_info.get('email')

    profile_data = {
        'student_name': request.form.get('student_name'),
        'student_email': user_email,
        'student_moblie_number': request.form.get('student_moblie_number'),
        'college_id': request.form.get('college_id'),
        'branch_id': request.form.get('branch_id'),
        'degree': request.form.get('degree'),
        'user_role': request.form.get('user_role'),
        'year_of_joining': request.form.get('year_of_joining'),
        'pursuing_year': request.form.get('pursuing_year') if request.form.get('pursuing_year') else None,
        'registration_number': request.form.get('registration_number')
    }

    result = create_or_update_student_profile(user_id, profile_data)
    msg_type = 'success' if result.get('success') else 'error'
    msg = result.get('message') or ('Profile updated!' if result.get('success') else 'Failed to update profile')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or (request.accept_mimetypes.accept_json and not request.accept_mimetypes.accept_html):
        return jsonify(result), (200 if result.get('success') else 400)

    flash(msg, msg_type)
    return redirect(url_for('app_pages.settings'))


@app_pages_bp.route('/settings')
@auth_required
def settings():
    """Display user settings page."""
    user_info = session.get('user', {})
    user_id = user_info.get('uid')
    profile_result = get_student_profile(user_id)
    profile = profile_result.get('data') if profile_result.get('success') else None
    colleges_result = get_all_colleges()
    branches_result = get_all_branches()
    colleges = colleges_result.get('data', []) if colleges_result.get('success') else []
    branches = branches_result.get('data', []) if branches_result.get('success') else []

    merged_user_data = dict(user_info)
    if profile:
        merged_user_data.update(profile)

    try:
        import app
        quota = app._get_quota()
        if quota and 'credits' in quota:
            merged_user_data['paper_quota_remaining'] = quota['credits']
    except Exception:
        pass

    return render_template('settings.html',
                           user_data=merged_user_data,
                           user=user_info,
                           profile=profile,
                           colleges=colleges,
                           branches=branches)


@app_pages_bp.route('/dashboard/setting')
def p_setting():
    return redirect(url_for('app_pages.settings'), code=301)


@app_pages_bp.route('/earnings')
@auth_required
def earnings():
    """Eligibility and earnings info page."""
    return render_template('earnings.html')


@app_pages_bp.route('/notifications')
@auth_required
def notifications_page():
    """Full notification center page with all notifications."""
    user_id = session.get('user', {}).get('uid')
    if not user_id:
        return redirect(url_for('auth.login'))
    limit = min(request.args.get('limit', 50, type=int), 100)
    offset = request.args.get('offset', 0, type=int)
    items = get_user_notifications(user_id, limit=limit, offset=offset)
    unread = sum(1 for n in items if not n.get('is_read'))
    has_more = len(items) == limit
    return render_template('notifications.html', notifications=items, unread=unread,
                           offset=offset, limit=limit, has_more=has_more)


@app_pages_bp.route('/dashboard/view', methods=['POST', 'GET'])
@auth_required
def view():
    """Handle file viewing - supports both form POST and file handler GET"""
    if request.method == 'GET':
        return render_template('app/file_receiver.html')

    file_name = request.form.get('file_name')
    subject = request.form.get('subject')
    date = request.form.get('date')
    section = request.form.get('section')
    url = request.form.get('url')
    file_data = {
        'file_name': file_name,
        'subject': subject,
        'date': date,
        'section': section,
        'url': url
    }
    return render_template('app/view.html', file=file_data)


@app_pages_bp.route('/dashboard/share-receiver', methods=['POST', 'GET'])
@auth_required
def share_receiver():
    """Handle shared files from other apps via PWA share_target."""
    if request.method == 'GET':
        return render_template('app/share_receiver.html', files=[], message="Share files using your device's share menu")

    title = request.form.get('title', '')
    text = request.form.get('text', '')
    url = request.form.get('url', '')
    files = request.files.getlist('files')

    received_files = []
    allowed_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.pdf'}
    max_file_size = 50 * 1024 * 1024

    for file in files:
        if file and file.filename:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in allowed_extensions:
                continue
            file.seek(0, 2)
            size = file.tell()
            file.seek(0)
            if size > max_file_size:
                continue
            temp_path = os.path.join('temp_uploads', file.filename)
            os.makedirs(os.path.dirname(temp_path), exist_ok=True)
            file.save(temp_path)
            received_files.append({
                'name': file.filename,
                'type': file.content_type,
                'size': size,
                'path': temp_path
            })

    return render_template('app/share_receiver.html',
                           files=received_files,
                           title=title,
                           text=text,
                           url=url,
                           message=f"Received {len(received_files)} file(s)")


@app_pages_bp.route('/dashboard/profile/old')
@auth_required
def p_profile_deprecated():
    return redirect(url_for('app_pages.profile'))


@app_pages_bp.route('/delete-account')
@auth_required
def delete_account():
    """Account deletion request page"""
    return render_template('delete_account.html')


@app_pages_bp.route('/app-shell')
@auth_required
def app_shell():
    """Native-like App Shell container for authenticated users."""
    if not current_app.config.get('APP_SHELL_ENABLED', True):
        return redirect(url_for('app_pages.dashboard'))

    target_path = request.args.get('p', '/dashboard').strip()
    if (
        not target_path.startswith('/')
        or target_path.startswith('//')
        or target_path.startswith('/\\')
        or '\\' in target_path
        or 'javascript:' in target_path.lower()
        or 'data:' in target_path.lower()
        or 'vbscript:' in target_path.lower()
    ):
        target_path = '/dashboard'

    path_only = target_path.split('?')[0].split('#')[0].rstrip('/')
    if not path_only:
        path_only = '/'

    blocked_prefixes = (
        '/app-shell', '/login', '/signup', '/logout', '/auth',
        '/reset-password', '/reset-password-confirm', '/google/callback',
        '/offline', '/api'
    )
    if path_only in blocked_prefixes or any(path_only.startswith(p + '/') for p in blocked_prefixes):
        target_path = '/dashboard'

    if request.headers.get('Sec-Fetch-Dest') == 'iframe':
        return redirect(target_path if target_path != '/app-shell' else url_for('app_pages.dashboard'))

    return render_template('app_shell.html', initial_path=target_path)


@app_pages_bp.route('/chat')
@auth_required
def chat_page():
    return render_template('chat.html')


@app_pages_bp.route('/chat/<peer_id>')
@auth_required
def chat_with_peer(peer_id):
    return render_template('chat.html', preload_peer=peer_id)


@app_pages_bp.route('/upload-gate')
@auth_required
def upload_gate():
    """Shown when a user has exhausted their paper-access credits."""
    import app
    q = app._get_quota()
    next_url = request.args.get('next', url_for('app_pages.app_shell'))
    return render_template('app/upload_gate.html',
                           credits=q.get('credits', 0),
                           quota_per_upload=app.QUOTA_PER_UPLOAD,
                           next_url=next_url)


@app_pages_bp.route('/local-viewer')
@auth_required
def local_viewer():
    """Standalone page: open a local image/PDF, preview it, then upload to Cloudinary."""
    return render_template('app/local_preview.html')


@app_pages_bp.route('/store-room')
@auth_required
def store_room():
    """Store Room page - displays unsorted papers from Cloudinary."""
    import app
    from routes.store_room import get_cached_unlabeled_files
    try:
        unlabeled_files, sorted_papers = get_cached_unlabeled_files()
        all_files = unlabeled_files
        total_papers = len(unlabeled_files) + sorted_papers
        remaining_papers = len(unlabeled_files)

        formats = app.get_unique_formats(all_files)
        folders = app.get_unique_folders(all_files)
        initial_batch_size = 20
        initial_files = all_files[:initial_batch_size]

        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        curator_stats = {
            'name': user_info.get('name', 'Academic Curator'),
            'reputation_score': 0,
            'uploads_count': 0,
            'tier_title': 'Curator'
        }
        if user_id:
            try:
                from methods.supabase_helper import calculate_user_ranks
                for r in calculate_user_ranks():
                    if r.get('uploader_id') == user_id:
                        curator_stats['uploads_count'] = r.get('upload_count', 0)
                        pts = r.get('points', 0)
                        curator_stats['reputation_score'] = int(pts * 10)
                        break
            except Exception:
                pass

        return render_template('app/store_room.html',
                               files=initial_files,
                               total_papers=total_papers,
                               sorted_papers=sorted_papers,
                               remaining_papers=remaining_papers,
                               formats=formats,
                               folders=folders,
                               initial_batch_size=initial_batch_size,
                               current_user=user_info,
                               curator_stats=curator_stats)
    except Exception as e:
        logging.error(f"Error loading store room: {e}")
        return render_template('site/error.html', error=str(e)), 500


@app_pages_bp.route('/upload', methods=['GET', 'POST'])
@auth_required
def upload():
    import app
    if request.method == 'POST':
        if 'upload_document' not in request.files:
            return jsonify(success=False, message="No file provided"), 400
        
        file = request.files['upload_document']
        if file.filename == '':
            return jsonify(success=False, message="No file selected"), 400
        
        if not app.validate_file_content(file, file.filename):
            return jsonify(success=False, message="File type not allowed or invalid file content. Allowed types: PDF, PNG, JPG, JPEG, WEBP, GIF"), 400
        
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > app.MAX_FILE_SIZE:
            return jsonify(success=False, message=f"File too large. Maximum size is {app.MAX_FILE_SIZE // (1024*1024)}MB"), 400
        
        if file_size == 0:
            return jsonify(success=False, message="File is empty"), 400
        
        try:
            import re
            import time
            from methods.supabase_helper import save_file_record, init_supabase, recalculate_and_persist_user_rank, track_user_event
            user_info = session['user']
            user_id = user_info.get('uid', '')
            user_email = user_info.get('email', '')
            user_name = user_info.get('name', '')
            
            subject = request.form.get('subject', '').strip()
            year = (request.form.get('Year') or request.form.get('year') or '').strip()
            doc_type = request.form.get('type', 'Other')
            document_type = request.form.get('document_type') or request.form.get('type') or 'Other'
            college_id = request.form.get('college_id', '').strip()
            branch_id = request.form.get('branch_id', '').strip()
            subject_id = request.form.get('subject_id', '').strip()
            semester_raw = request.form.get('semester', '').strip()
            semester = int(semester_raw) if semester_raw.isdigit() and 1 <= int(semester_raw) <= 8 else None
            title_val = (request.form.get('title') or subject or '').strip()
            description_val = request.form.get('description', '').strip()
            program = request.form.get('program', 'b.tech').strip() or 'b.tech'
            unit = request.form.get('unit', '')

            price_raw = request.form.get('price', '').strip()
            coupon_raw = request.form.get('coupon_code', '').strip().upper()
            disc_raw = request.form.get('coupon_discount', '').strip()
            pricing_data = None

            if price_raw:
                try:
                    price_val = round(float(price_raw), 2)
                    if price_val > 0:
                        price_val = max(1.0, min(5000.0, price_val))
                        pricing_data = {'is_paid': True, 'price': price_val, 'seller_id': user_id}
                        if coupon_raw and coupon_raw.isalnum():
                            try:
                                disc_val = max(1, min(90, int(disc_raw or 10)))
                                pricing_data['coupon_code'] = coupon_raw[:12]
                                pricing_data['coupon_discount'] = disc_val
                            except (ValueError, TypeError):
                                pass
                except (ValueError, TypeError):
                    pass

            if pricing_data:
                desc_payload = {
                    'text_description': description_val,
                    'pricing': pricing_data
                }
                description_val = json.dumps(desc_payload)

            _ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
            folder_map = {
                'papers': 'pyq',
                'notes': 'notes',
                'practical': 'practical',
                'syllabus': 'syllabus',
                'assisment': 'other',
                'timetable': 'other',
                'question_bank': 'pyq'
            }
            cloudinary_folder = folder_map.get(doc_type, 'uploads')

            # 1. FIRST: Upload file directly to Cloudinary
            from methods.cloudinary_upload import upload_file_to_cloudinary
            upload_result = upload_file_to_cloudinary(
                file_data=file,
                filename=file.filename,
                user_id=user_id or user_name.replace(' ', '_'),
                folder=cloudinary_folder,
                compress=True
            )

            if not upload_result.get('success'):
                return jsonify(
                    success=False,
                    message=f"Upload failed: {upload_result.get('error', 'Unknown error')}"
                ), 500

            # 2. NEXT: Verification of metadata and academic requirements
            verification_issues = []
            if (not subject_id or subject_id == '__other__') and document_type.lower() != 'question_bank':
                verification_issues.append(f"Subject selection is required (provided subject: '{subject or 'None'}')")

            if semester is None:
                semester = 1

            if not (year.isdigit() and len(year) == 4 and 1990 <= int(year) <= 2035):
                verification_issues.append(f"Academic year '{year}' invalid or requires verification")

            if not title_val or len(title_val) < 3:
                title_val = f"{subject or 'Study Material'} {document_type.replace('_', ' ').title()} {year}".strip()

            if not college_id:
                college_id = user_info.get('college_id') or (user_info.get('user_metadata') or {}).get('college_id', '')

            # Abbreviation resolution for College, Department, Subject, and Subject Code
            col_abbr = (request.form.get('college_abbr') or '').strip().upper()
            dept_abbr = (request.form.get('branch_abbr') or request.form.get('department_abbr') or '').strip().upper()
            subj_abbr = (request.form.get('subject_abbr') or '').strip().upper()
            subject_code = (request.form.get('subject_code') or '').strip().upper()

            # Fast cache lookup for College, Department, Subject abbreviations
            global _ACRONYM_CACHE
            if '_ACRONYM_CACHE' not in globals():
                _ACRONYM_CACHE = {}

            if not col_abbr and college_id:
                col_abbr = _ACRONYM_CACHE.get(f"col:{college_id}", "")
            if not dept_abbr and branch_id:
                dept_abbr = _ACRONYM_CACHE.get(f"dept:{branch_id}", "")
            if not subj_abbr and subject_id:
                subj_abbr = _ACRONYM_CACHE.get(f"subj:{subject_id}", "")
            if not subject_code and subject_id:
                subject_code = _ACRONYM_CACHE.get(f"code:{subject_id}", "")

            # Query DB only if any required abbreviation is not yet cached
            if (not col_abbr and college_id) or (not dept_abbr and branch_id) or (subject_id and (not subj_abbr or not subject_code)):
                from methods.supabase_helper import init_supabase, make_acronym
                client_sb = init_supabase()
                if client_sb:
                    if not col_abbr and college_id:
                        try:
                            c_row = client_sb.table('colleges').select('name, abbreviation').eq('id', college_id).limit(1).execute()
                            if c_row.data:
                                col_abbr = (c_row.data[0].get('abbreviation') or make_acronym(c_row.data[0].get('name'))).strip().upper()
                                _ACRONYM_CACHE[f"col:{college_id}"] = col_abbr
                        except Exception:
                            pass
                    if not dept_abbr and branch_id:
                        try:
                            d_row = client_sb.table('departments').select('name, abbreviation').eq('id', branch_id).limit(1).execute()
                            if d_row.data:
                                dept_abbr = (d_row.data[0].get('abbreviation') or make_acronym(d_row.data[0].get('name'))).strip().upper()
                                _ACRONYM_CACHE[f"dept:{branch_id}"] = dept_abbr
                        except Exception:
                            pass
                    if subject_id and (not subj_abbr or not subject_code):
                        try:
                            s_row = client_sb.table('subjects').select('name, subject_code').eq('id', subject_id).limit(1).execute()
                            if s_row.data:
                                if not subject_code:
                                    subject_code = (s_row.data[0].get('subject_code') or '').strip().upper()
                                    _ACRONYM_CACHE[f"code:{subject_id}"] = subject_code
                                if not subj_abbr:
                                    subj_abbr = make_acronym(s_row.data[0].get('name') or subject)
                                    _ACRONYM_CACHE[f"subj:{subject_id}"] = subj_abbr
                        except Exception:
                            pass

            if not subj_abbr and subject:
                subj_abbr = make_acronym(subject)

            # Program-aware department abbreviation override
            if program and str(program).lower() != 'b.tech':
                prog_clean = re.sub(r'[^a-zA-Z0-9]', '', str(program)).upper()
                if not dept_abbr or dept_abbr in ('ALL', 'ABA', 'ALLBRANCHES'):
                    dept_abbr = prog_clean

            # Override known corrupted acronym artifacts
            if col_abbr == 'GHRCEG':
                col_abbr = 'GHRCE'
            if dept_abbr == 'ABA' and program and str(program).lower() == 'mba':
                dept_abbr = 'MBA'

            # Build standardized descriptive title: CollegeAbbr - DeptAbbr - SubjAbbr (SubjectCode) - Topic/Unit/Category Year
            prefix_tags = [p for p in [col_abbr, dept_abbr, subj_abbr] if p]
            header = " - ".join(prefix_tags)
            if subject_code and subject_code not in header:
                header = f"{header} ({subject_code})" if header else subject_code

            cat_title = document_type.replace('_', ' ').title()
            unit_clean = re.sub(r'[^a-zA-Z0-9]', '', unit or '')

            if not title_val or len(title_val) < 3 or title_val.lower() == (subject or '').lower():
                detail_parts = [p for p in [unit, cat_title, year] if p]
                title_val = f"{header} - {' · '.join(detail_parts)}" if header else " · ".join(detail_parts)
            elif header and not title_val.startswith(col_abbr) and not title_val.startswith(header) and header not in title_val:
                title_val = f"{header} - {title_val}"

            if title_val:
                title_val = re.sub(r'\bGHRCEG\b', 'GHRCE', title_val)
                if program and str(program).lower() == 'mba':
                    title_val = re.sub(r'\bABA\b', 'MBA', title_val)

            fn_components = [p for p in [col_abbr, dept_abbr, subj_abbr, subject_code, unit_clean, cat_title.replace(' ', ''), str(year)] if p]
            if fn_components:
                _base = "_".join(re.sub(r'[^a-zA-Z0-9]', '', c) for c in fn_components)
            else:
                _base = f"upload_{int(time.time())}"
            original_filename = f"{_base}.{_ext}"
            original_filename = re.sub(r'\bGHRCEG\b', 'GHRCE', original_filename)
            if program and str(program).lower() == 'mba':
                original_filename = re.sub(r'\bABA\b', 'MBA', original_filename)

            ext = _ext
            file_type_category = {
                'pdf': 'pdf',
                'doc': 'document', 'docx': 'document', 'txt': 'document',
                'ppt': 'presentation', 'pptx': 'presentation',
                'xls': 'spreadsheet', 'xlsx': 'spreadsheet',
                'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'webp': 'image',
                'zip': 'archive', 'rar': 'archive', '7z': 'archive'
            }.get(ext, 'file')

            logging.info(f"[UPLOAD] Uploader:{user_id} College:{college_id} Branch:{branch_id} Semester:{semester} Subject:{subject!r} SubjectID:{subject_id}")

            file_hash = request.form.get('file_hash', '').strip() or None
            exam_type = request.form.get('exam_type', '').strip() or ''
            subject_code = request.form.get('subject_code', '').strip() or ''

            _save_fn = getattr(app, 'save_file_record', None) or save_file_record
            file_record_result = _save_fn(
                user_id=user_id,
                user_email=user_email,
                file_name=original_filename,
                file_url=upload_result['secure_url'],
                file_type=file_type_category,
                file_size=upload_result.get('bytes') or file_size,
                cloudinary_public_id=upload_result['public_id'],
                subject_name=subject,
                document_type=document_type.lower(),
                year=year,
                college_id=college_id if college_id else None,
                branch_id=branch_id if branch_id else None,
                title=title_val,
                description=description_val,
                subject_id=subject_id if subject_id else None,
                semester=semester,
                program=program,
                exam_type=exam_type,
                subject_code=subject_code,
                file_hash=file_hash
            )

            # 3. IF ANY VERIFICATION ISSUES OR DB RECORD ERROR: Report to admin (Admin decides to keep or delete)
            if not file_record_result.get('success') or verification_issues:
                err_detail = '; '.join(verification_issues) if verification_issues else file_record_result.get('message', 'Database record creation deferred')
                logging.warning(f"[UPLOAD FLAGGED FOR ADMIN] File: {upload_result['public_id']} Reason: {err_detail}")
                try:
                    from methods.supabase_helper import init_supabase
                    client_sb = init_supabase()
                    if client_sb:
                        client_sb.table('storage_assets').upsert({
                            'provider': 'cloudinary',
                            'provider_public_id': upload_result.get('public_id'),
                            'filename': original_filename,
                            'public_url': upload_result.get('secure_url'),
                            'mime': upload_result.get('format', 'unknown'),
                            'status': 'NEEDS_ADMIN_REVIEW',
                            'notes': f"Verification note: {err_detail}"
                        }, on_conflict='provider,provider_public_id').execute()

                        client_sb.table('notifications').insert({
                            'user_id': user_id,
                            'type': 'upload_flagged_for_admin',
                            'title': f"Upload needs verification: {original_filename[:35]}",
                            'message': f"Uploaded file ({upload_result.get('secure_url')}) flagged: {err_detail}. Admin review to keep or delete.",
                            'is_read': False
                        }).execute()

                        doc_id_flagged = file_record_result.get('data', {}).get('id') if file_record_result.get('success') else None
                        if doc_id_flagged:
                            client_sb.table('documents').update({
                                'status': 'pending',
                                'verification_notes': err_detail
                            }).eq('id', doc_id_flagged).execute()
                except Exception as admin_rep_err:
                    logging.warning(f"[UPLOAD ADMIN REPORT NOTE] {admin_rep_err}")

                doc_id = file_record_result.get('data', {}).get('id') if file_record_result.get('success') else None
                return jsonify(
                    success=True,
                    pending_admin=True,
                    message=f"File uploaded to cloud storage successfully! Flagged for admin verification ({err_detail}).",
                    file_url=upload_result['secure_url'],
                    public_id=upload_result['public_id'],
                    document={'id': doc_id, 'title': title_val, 'url': upload_result['secure_url']},
                    data={'record_id': doc_id, 'url': upload_result['secure_url']}
                ), 200

            doc_id = file_record_result.get('data', {}).get('id')
            material_request_id = request.form.get('material_request_id')

            def _bg_post_upload(u_id, u_email, d_id, s_id, sem, d_type, m_req_id, d_title, s_name):
                try:
                    track_user_event(u_id, 'UPLOAD', {
                        'document_id': d_id,
                        'subject_id': s_id,
                        'semester': sem,
                        'document_type': d_type
                    })
                except Exception:
                    pass
                if m_req_id and d_id:
                    try:
                        c = init_supabase()
                        if c:
                            c.table('material_requests').update({
                                'status': 'accepted',
                                'responder_id': u_id,
                                'responder_email': u_email,
                                'response_message': f"Uploaded file {d_id}",
                                'response_document_id': d_id,
                                'responded_at': 'now()'
                            }).eq('id', m_req_id).execute()
                    except Exception:
                        pass
                try:
                    app._trigger_indexnow([
                        f"https://{app.BASE_DOMAIN}/pyq",
                        f"https://{app.BASE_DOMAIN}/resource/{d_id}" if d_id else None,
                    ])
                except Exception:
                    pass
                try:
                    recalculate_and_persist_user_rank(u_id)
                except Exception:
                    pass
                try:
                    from methods.supabase_helper import notify_all_new_upload
                    notify_all_new_upload(doc_id=d_id, title=d_title, uploader_id=u_id, subject=s_name)
                except Exception as ex:
                    logging.warning(f"[UPLOAD NOTIFY] notify_all_new_upload failed: {ex}")

            import threading
            threading.Thread(
                target=_bg_post_upload,
                args=(user_id, user_email, doc_id, subject_id or None, semester, document_type.lower(), material_request_id, title_val, subject),
                daemon=True
            ).start()

            app._grant_upload_credits()

            cat = document_type.lower()
            raw_pts = app.POINTS_MAP.get(cat, app.DEFAULT_POINTS)
            xp_gained = round(raw_pts * 0.5, 2)
            new_score = 0.0
            try:
                profile_row = session.get('profile') or {}
                new_score = round(float(profile_row.get('reputation_score') or 0.0) + xp_gained, 2)
            except Exception:
                pass

            try:
                from cache_manager import get_cache
                c_mgr = get_cache()
                if c_mgr:
                    c_mgr.invalidate_files()
                    c_mgr.invalidate_dropdowns()
                    c_mgr.bump_version()
            except Exception:
                pass

            total_uploads = 1
            try:
                prof = session.get('profile') or {}
                cached_cnt = prof.get('total_contributions') or prof.get('total_uploads')
                total_uploads = int(cached_cnt) + 1 if cached_cnt is not None else 1
            except Exception:
                total_uploads = 1

            document_payload = {
                'id': doc_id,
                'title': title_val,
                'url': f"/resource/{doc_id}" if doc_id else upload_result['secure_url'],
                'subject': subject,
                'semester': semester,
                'document_type': document_type.lower()
            }
            contribution_payload = {
                'xp_earned': xp_gained,
                'total_xp': new_score,
                'total_contributions': total_uploads
            }

            return jsonify(
                success=True,
                message="Contribution uploaded and published successfully! 🎉",
                document=document_payload,
                contribution=contribution_payload,
                data={
                    'url': upload_result['secure_url'],
                    'record_id': doc_id,
                    'resource_id': doc_id,
                    'resource_url': f"/resource/{doc_id}" if doc_id else None,
                    'title': title_val,
                    'subject': subject,
                    'semester': semester,
                    'document_type': document_type.lower(),
                    'public_id': upload_result['public_id'],
                    'file_size': upload_result.get('bytes') or file_size,
                    'file_type': file_type_category,
                    'compressed': bool(upload_result.get('bytes') and upload_result['bytes'] < file_size),
                    'credits_granted': app.QUOTA_PER_UPLOAD,
                    'credits_remaining': app._get_quota().get('credits', 0),
                    'xp_gained': xp_gained,
                    'new_score': new_score,
                    'total_contributions': total_uploads
                }
            ), 200
            
        except Exception as e:
            logging.error(f"[UPLOAD EXCEPTION] Upload error: {e}")
            return jsonify(
                success=False,
                message=f"Upload failed: {str(e)}"
            ), 500

    if 'user' in session:
        return render_template('app/upload.html')
    else:
        return render_template('site/login.html')


@app_pages_bp.route('/dashboard/suggest')
@auth_required
def suggest():
    """Deprecated: now forwards to V2 suggest (taxonomy + intent detection)."""
    q = request.args.get('q', '').strip()
    college_id = request.args.get('college_id', '').strip() or None
    if not q:
        return jsonify({"subjects": [], "types": [], "authors": []})
    try:
        from methods.search_api import get_suggestions_payload
        payload = get_suggestions_payload(q, college_id=college_id)
        subjects = [s['title'] for s in payload.get('groups', {}).get('subjects', [])]
        branches = [b['title'] for b in payload.get('groups', {}).get('branches', [])]
        return jsonify({"subjects": subjects, "types": branches, "authors": [], "v2": payload})
    except Exception as e:
        logging.warning(f"[suggest] V2 suggest error: {e}")
        return jsonify({"subjects": [], "types": [], "authors": []})


@app_pages_bp.route('/dashboard/')
@auth_required
def index():
    return redirect(url_for('app_pages.dashboard'), code=301)


@app_pages_bp.route('/dashboard/search', methods=['POST', 'GET'])
@auth_required
def search():
    """Search entry point — redirects to the SPA search page with query."""
    search_query = request.form.get('search') or request.args.get('search', '')
    if not search_query:
        return redirect(url_for('app_pages.dashboard'))
    # Redirect to SPA search view (frontend reads ?q= and calls /api/v2/search)
    from urllib.parse import quote_plus
    return redirect(f"/app-shell?p=/search&q={quote_plus(search_query)}")


@app_pages_bp.route('/dashboard/static/search.json')
@auth_required
def search_in():
    search_file = os.path.join(current_app.root_path, 'premium/static/search.json')
    try:
        with open(search_file, 'r') as f:
            searches = json.load(f)
        return jsonify(searches), 200
    except Exception:
        return jsonify({'status': 'error'}), 500


@app_pages_bp.route('/dashboard/save_search', methods=['POST'])
@auth_required
def save_search():
    """Persist a search query — writes to search_analytics DB (not flat file)."""
    search_data = request.get_json()
    search_query = search_data.get('searchquery') if search_data else None
    if not search_query:
        return jsonify({'status': 'noop'}), 200
    try:
        from methods.supabase_helper import init_supabase
        client = init_supabase()
        if client:
            client.table('search_analytics').insert({
                'query': search_query,
                'results_count': search_data.get('results_count', 0)
            }).execute()
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logging.warning(f"[save_search] DB insert failed (non-fatal): {e}")
        return jsonify({'status': 'ok'}), 200  # non-fatal — never block UX


@app_pages_bp.route('/memorywall')
@auth_required
def memorywall_dashboard():
    """Creator dashboard — shows wall status, share link, stats, and recent activity."""
    from methods.know_me import get_wall_by_user, get_recent_responses, get_dashboard_metrics
    user = session.get('user', {})
    user_id = user.get('uid')
    wall_result = get_wall_by_user(user_id)
    wall = wall_result.get('data') if wall_result.get('success') else None

    dashboard_data = None
    recent_responses = []
    if wall:
        dashboard_data = get_dashboard_metrics(wall['id'])
        recent_responses = get_recent_responses(wall['id'], limit=5)

    return render_template(
        'know_me/dashboard.html',
        wall=wall,
        user=user,
        dashboard_data=dashboard_data,
        recent_responses=recent_responses
    )


@app_pages_bp.route('/memorywall/create', methods=['GET', 'POST'])
@auth_required
def memorywall_create():
    """Create a new MemoryWall."""
    from methods.know_me import get_wall_by_user, create_wall
    user = session.get('user', {})
    user_id = user.get('uid')

    existing = get_wall_by_user(user_id)
    if existing.get('success') and existing.get('data'):
        return redirect(url_for('app_pages.memorywall_dashboard'))

    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()[:80]
        college = (request.form.get('college') or '').strip()[:100]
        branch = (request.form.get('branch') or '').strip()[:100]
        try:
            grad_year = int(request.form.get('graduation_year') or 0) or None
        except ValueError:
            grad_year = None

        if not title:
            return render_template('know_me/create.html', error='Please enter a title.', user=user)

        result = create_wall(user_id, title, college, branch, grad_year)
        if result.get('success') or result.get('message') == 'already_exists':
            return redirect(url_for('app_pages.memorywall_dashboard'))
        else:
            return render_template('know_me/create.html',
                                   error='Something went wrong. Please try again.', user=user)

    return render_template('know_me/create.html', user=user)


@app_pages_bp.route('/m/<slug>')
def memorywall_public(slug):
    """Public submission page — no auth required."""
    from methods.know_me import get_wall_by_slug
    from flask import abort
    result = get_wall_by_slug(slug)
    if not result.get('success') or not result.get('data'):
        abort(404)
    wall = result['data']
    if wall.get('status') == 'closed':
        return render_template('know_me/closed.html', wall=wall), 410
    return render_template('know_me/public_wall.html', wall=wall)


@app_pages_bp.route('/memorywall/reveal/<wall_id>')
@auth_required
def memorywall_reveal(wall_id):
    """Reveal page — authenticated wall owner only."""
    from flask import abort
    from methods.know_me import reveal_wall, get_wall_by_user, get_dashboard_metrics, generate_personality_summary
    from methods.know_me_generator import generate_wordcloud, generate_signature_wall, upload_to_firebase

    user = session.get('user', {})
    user_id = user.get('uid')

    owner_check = get_wall_by_user(user_id)
    if not owner_check.get('success') or not owner_check.get('data'):
        abort(403)
    if owner_check['data']['id'] != wall_id:
        abort(403)

    data = reveal_wall(wall_id)
    responses = data.get('responses', [])
    word_list = data.get('word_list', [])
    words = data.get('words', [])

    try:
        from methods.know_me import increment_view_count
        increment_view_count(wall_id)
    except Exception:
        pass

    metrics = get_dashboard_metrics(wall_id)
    personality_summary = generate_personality_summary(metrics)

    wc_path = generate_wordcloud(word_list, wall_id)
    sig_urls = [
        r['signature'][0]['signature_url']
        for r in responses
        if r.get('signature') and r['signature'][0].get('signature_url')
    ]
    sw_path = generate_signature_wall(sig_urls, wall_id)

    wc_firebase = ""
    sw_firebase = ""
    try:
        if wc_path:
            wc_firebase = upload_to_firebase(wc_path, f"know_me/{wall_id}/wordcloud.png")
        if sw_path:
            sw_firebase = upload_to_firebase(sw_path, f"know_me/{wall_id}/signature_wall.png")
    except Exception as e:
        logging.warning(f"[MemoryWall] Firebase upload skipped: {e}")

    wall = owner_check['data']
    return render_template('know_me/reveal.html',
                           wall=wall, user=user,
                           responses=responses,
                           words=words,
                           wc_path=wc_path,
                           sw_path=sw_path,
                           wc_firebase=wc_firebase,
                           sw_firebase=sw_firebase,
                           metrics=metrics,
                           personality_summary=personality_summary)


@app_pages_bp.route('/profile/<user_id>')
@app_pages_bp.route('/peer/<user_id>')
def peer_profile(user_id):
    """Legacy peer profile route — permanent 301 redirect to canonical /u/<user_id>."""
    return redirect(url_for('app_pages.instagram_profile', user_id=user_id), code=301)


@app_pages_bp.route('/u/<user_id>')
def instagram_profile(user_id):
    """Public, Instagram-friendly profile page with OG meta tags for sharing."""
    from flask import abort
    import app
    from methods.supabase_helper import init_supabase, init_supabase_admin

    if not app.validate_uuid(user_id):
        abort(404)
    client = init_supabase()
    if not client:
        abort(500)
    try:
        pr = client.table('profiles') \
            .select('id, full_name, email, rank_title, reputation_score, is_verified, referral_code, college_id, department_id, colleges(name), departments(name, abbreviation)') \
            .eq('id', user_id).single().execute()
        if not pr.data:
            abort(404)
        p = pr.data
        academic = {}
        try:
            st = client.table('students') \
                .select('pursuing_year, year_of_joining') \
                .eq('profile_id', user_id).limit(1).execute()
            if st.data:
                academic = st.data[0]
        except Exception:
            pass
        college_name = (p.get('colleges') or {}).get('name', '')
        dept = p.get('departments') or {}
        dept_name = dept.get('name') or dept.get('abbreviation') or ''
        peer = {
            'id': p.get('id'),
            'name': p.get('full_name') or 'Student',
            'email': p.get('email', ''),
            'rank_title': p.get('rank_title', 'Student'),
            'reputation_score': p.get('reputation_score', 0),
            'is_verified': p.get('is_verified', False),
            'referral_code': p.get('referral_code', ''),
            'college_name': college_name,
            'department_name': dept_name,
            'pursuing_year': academic.get('pursuing_year') or '',
            'year_of_joining': academic.get('year_of_joining') or '',
        }
    except Exception as e:
        logging.error(f"[u/profile] {e}")
        abort(404)

    uploads = []
    try:
        docs = client.table('documents') \
            .select('id, title, document_category, view_count, subjects(name)') \
            .eq('uploader_id', user_id).eq('status', 'approved') \
            .order('created_at', desc=True).limit(12).execute()
        for d in (docs.data or []):
            uploads.append({
                'record_id': d.get('id'),
                'file-name': d.get('title') or 'Untitled',
                'type': d.get('document_category') or 'papers',
                'subject': (d.get('subjects') or {}).get('name', ''),
                'views': d.get('view_count', 0),
            })
    except Exception:
        pass

    memory_wall = {'exists': False, 'is_open': False, 'url': '', 'response_count': 0}
    try:
        from methods.know_me import get_wall_by_user
        wall_result = get_wall_by_user(user_id)
        wall = wall_result.get('data') if wall_result.get('success') else None
        if wall:
            memory_wall = {
                'exists': True,
                'is_open': wall.get('status', 'open') != 'closed',
                'url': url_for('app_pages.memorywall_public', slug=wall.get('slug')),
                'response_count': wall.get('response_count') or 0,
            }
    except Exception:
        pass

    referred = []
    try:
        views = client.table('document_views') \
            .select('document_id, documents(id, title, document_category, subjects(name))') \
            .eq('user_id', user_id).order('accessed_at', desc=True).limit(8).execute()
        seen = set()
        for v in (views.data or []):
            doc = v.get('documents') or {}
            did = doc.get('id')
            if did and did not in seen:
                seen.add(did)
                referred.append({
                    'record_id': did,
                    'file-name': doc.get('title') or 'Untitled',
                    'type': doc.get('document_category') or 'notes',
                    'subject': (doc.get('subjects') or {}).get('name', ''),
                })
    except Exception:
        pass

    crush_state = {'is_crush': False, 'is_match': False, 'crushes_remaining': 2, 'is_self': False}
    viewer_id = session.get('user', {}).get('uid')
    if viewer_id:
        if viewer_id == user_id:
            crush_state['is_self'] = True
        else:
            year = datetime.utcnow().year
            try:
                ac = init_supabase_admin() or client
                i_crushed = bool(ac.table('user_crushes').select('id')
                    .eq('from_user', viewer_id).eq('to_user', user_id).eq('year', year).execute().data)
                they_crushed = bool(ac.table('user_crushes').select('id')
                    .eq('from_user', user_id).eq('to_user', viewer_id).eq('year', year).execute().data)
                used = (ac.table('user_crushes').select('id', count='exact')
                    .eq('from_user', viewer_id).eq('year', year).execute().count or 0)
                crush_state = {
                    'is_crush': i_crushed,
                    'is_match': i_crushed and they_crushed,
                    'crushes_remaining': max(0, 2 - used),
                    'is_self': False,
                }
            except Exception:
                pass

    campus_peers = []
    try:
        col_id = p.get('college_id')
        dept_id = p.get('department_id')
        seen_ids = {user_id}

        def _format_cp(cp, tag):
            c_name = ((cp.get('colleges') or {}).get('name') or '').strip()
            d_obj = cp.get('departments') or {}
            d_name = (d_obj.get('abbreviation') or d_obj.get('name') or '').strip()
            return {
                'id': cp.get('id'),
                'name': cp.get('full_name') or 'Student',
                'rank_title': cp.get('rank_title') or 'Student',
                'reputation_score': int(cp.get('reputation_score') or 0),
                'is_verified': bool(cp.get('is_verified', False)),
                'college_name': c_name,
                'department_name': d_name,
                'network_tag': tag,
            }

        # 1. Classmates from same department
        if dept_id:
            try:
                res_d = client.table('profiles').select(
                    'id, full_name, rank_title, reputation_score, is_verified, college_id, colleges(name), department_id, departments(name, abbreviation)'
                ).neq('id', user_id).eq('department_id', dept_id).order('reputation_score', desc=True).limit(6).execute()
                for cp in (res_d.data or []):
                    if cp.get('id') not in seen_ids:
                        seen_ids.add(cp.get('id'))
                        campus_peers.append(_format_cp(cp, 'Classmate'))
            except Exception:
                pass

        # 2. Campus peers from same college
        if col_id and len(campus_peers) < 6:
            try:
                res_c = client.table('profiles').select(
                    'id, full_name, rank_title, reputation_score, is_verified, college_id, colleges(name), department_id, departments(name, abbreviation)'
                ).neq('id', user_id).eq('college_id', col_id).order('reputation_score', desc=True).limit(6).execute()
                for cp in (res_c.data or []):
                    if cp.get('id') not in seen_ids:
                        seen_ids.add(cp.get('id'))
                        campus_peers.append(_format_cp(cp, 'Campus Peer'))
            except Exception:
                pass

        # 3. Fill up to 6 with top platform study peers
        if len(campus_peers) < 6:
            try:
                res_top = client.table('profiles').select(
                    'id, full_name, rank_title, reputation_score, is_verified, college_id, colleges(name), department_id, departments(name, abbreviation)'
                ).neq('id', user_id).order('reputation_score', desc=True).limit(10).execute()
                for cp in (res_top.data or []):
                    if cp.get('id') not in seen_ids and len(campus_peers) < 6:
                        seen_ids.add(cp.get('id'))
                        campus_peers.append(_format_cp(cp, 'Study Network'))
            except Exception:
                pass
    except Exception as e:
        logging.error(f"[campus_peers] {e}")

    og_title = f"{peer['name']} on AbhiHub"
    og_description = f"{peer['name']} has shared {len(uploads)} study materials on AbhiHub."

    return render_template('profile_instagram.html',
                           peer=peer,
                           uploads=uploads,
                           referred=referred,
                           memory_wall=memory_wall,
                           crush_state=crush_state,
                           campus_peers=campus_peers,
                           og_title=og_title,
                           og_description=og_description,
                           og_image=None)

