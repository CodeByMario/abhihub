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
    get_reputation_stats, get_user_notifications, get_peer_recommended_files
)

app_pages_bp = Blueprint('app_pages', __name__)


@app_pages_bp.route('/dashboard')
@auth_required
def dashboard():
    """Dashboard for authenticated users."""
    import app

    user_info = session.get('user', {})
    current_user_id = user_info.get('uid')
    files = app.get_all_file_records_formatted(current_user_id=current_user_id)

    all_subjects = list(set([f.get('subject', '') for f in files if f.get('subject', '').strip()]))
    top_subjects = sorted(all_subjects)[:8]
    paper_count = len([f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')])
    notes_count = len([f for f in files if f.get('type', '').lower() in ('notes', 'note', 'imp questions', 'imp_questions')])

    seo_keywords = "AbhiHub, GHRCE papers, engineering papers, " + ", ".join(top_subjects) + ", exam resources, study materials"

    user_data = None
    if 'user' in session:
        user_info = session['user']
        user_name = user_info.get('name', '')
        user_email = user_info.get('email', '')
        user_id = user_info.get('uid', '')

        user_files = [f for f in files if f.get('author', '') == user_name or f.get('author_email', '') == user_email]
        user_uploads_count = len(user_files)

        user_notes_count = 0
        user_papers_count = 0
        user_practicals_count = 0
        user_subjects = set()
        for f in user_files:
            ft = f.get('type', '').lower()
            if ft == 'notes':
                user_notes_count += 1
            elif ft in ('pyq', 'papers'):
                user_papers_count += 1
            elif ft == 'practical':
                user_practicals_count += 1
            subj = f.get('subject', '').strip()
            if subj:
                user_subjects.add(subj)

        history_result = get_user_file_history(user_email=user_email, user_id=user_id, limit=12)
        file_history = history_result.get('data', []) if history_result.get('success') else []

        college_name = ''
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
    else:
        file_history = []

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

    all_papers = [f for f in files if f.get('type', '').lower() in ('papers', 'paper', 'pyq')]
    all_papers_by_views = sorted(all_papers, key=lambda f: f.get('view_count', 0), reverse=True)

    user_college = user_data.get('college_name', '') if user_data else ''
    if user_college:
        college_papers = [f for f in all_papers_by_views if f.get('college', '') == user_college]
        relevant_papers = college_papers[:8]
        paper_count = len(college_papers)
    else:
        relevant_papers = all_papers_by_views[:8]

    trending_papers = all_papers_by_views[:8]
    recent_papers = sorted(all_papers, key=lambda f: f.get('date', ''), reverse=True)[:8]

    notes_type_values = ('notes', 'note', 'imp questions', 'imp_questions')
    all_notes = [f for f in files if f.get('type', '').lower() in notes_type_values]
    all_notes_by_views = sorted(all_notes, key=lambda f: f.get('view_count', 0), reverse=True)

    if user_college:
        college_notes = [f for f in all_notes_by_views if f.get('college', '') == user_college]
        relevant_notes = college_notes[:8]
        notes_count = len(college_notes)
    else:
        relevant_notes = all_notes_by_views[:8]

    trending_notes = all_notes_by_views[:8]
    recent_notes = sorted(all_notes, key=lambda f: f.get('date', ''), reverse=True)[:8]

    file_lookup = {f.get('record_id'): f for f in files if f.get('record_id')}
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

    # Fallback to same college or trending resources if peer view history is sparse
    if len(recommended_files) < 6:
        seen_rec_ids = {r.get('record_id') for r in recommended_files} | user_viewed_ids
        pool = (relevant_papers if user_college else trending_papers) + (relevant_notes if user_college else trending_notes)
        for item in pool:
            rid = item.get('record_id')
            if rid and rid not in seen_rec_ids:
                seen_rec_ids.add(rid)
                recommended_files.append(item)
                if len(recommended_files) >= 8:
                    break

    return render_template(
        'app/dashboard.html',
        data=files,
        seo_keywords=seo_keywords,
        top_subjects=top_subjects,
        paper_count=paper_count,
        notes_count=notes_count,
        user_data=user_data,
        file_history=file_history,
        recently_viewed_files=recently_viewed_files,
        recommended_files=recommended_files,
        now=datetime.now(),
        promo_context=promo_context,
        relevant_papers=relevant_papers,
        trending_papers=trending_papers,
        recent_papers=recent_papers,
        relevant_notes=relevant_notes,
        trending_notes=trending_notes,
        recent_notes=recent_notes
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

            if not title_val or len(title_val) < 3:
                title_val = f"{subject or 'Study Material'} {document_type.replace('_', ' ').title()} {year}".strip()

            if not college_id:
                college_id = user_info.get('college_id') or (user_info.get('user_metadata') or {}).get('college_id', '')

            if (not subject_id or subject_id == '__other__') and document_type.lower() != 'question_bank':
                logging.warning(f"[UPLOAD REJECTED] Reason:Missing subject_id Uploader:{user_id}")
                return jsonify(success=False, message="Subject selection is required. Please select a subject from the dropdown."), 400

            if semester is None:
                semester = 1

            if not (year.isdigit() and len(year) == 4 and 1990 <= int(year) <= 2035):
                return jsonify(success=False, message="Please provide a valid 4-digit academic year (e.g. 2025)."), 400

            _ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
            _subject_part = (subject or '').strip()
            if not _subject_part and document_type.lower() == 'question_bank':
                _subject_part = (request.form.get('qb_tags') or '').strip() or 'question_bank'
            _safe = lambda s: re.sub(r'[^a-zA-Z0-9_-]+', '', s.replace(' ', '_')).lower()
            _parts = [str(year), _safe(_subject_part), _safe(document_type)]
            if unit: _parts.append(_safe(unit))
            _parts.append(str(int(time.time()))[-6:])
            _base = '_'.join(p for p in _parts if p) or 'upload'
            original_filename = f"{_base}.{_ext}"

            ext = _ext
            file_type_category = {
                'pdf': 'pdf',
                'doc': 'document', 'docx': 'document', 'txt': 'document',
                'ppt': 'presentation', 'pptx': 'presentation',
                'xls': 'spreadsheet', 'xlsx': 'spreadsheet',
                'png': 'image', 'jpg': 'image', 'jpeg': 'image', 'gif': 'image', 'webp': 'image',
                'zip': 'archive', 'rar': 'archive', '7z': 'archive'
            }.get(ext, 'file')
            
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
            
            from methods.cloudinary_upload import upload_file_to_cloudinary, delete_file_from_cloudinary
            upload_result = upload_file_to_cloudinary(
                file_data=file,
                filename=original_filename,
                user_id=user_id or user_name.replace(' ', '_'),
                folder=cloudinary_folder,
                compress=True
            )
            
            if not upload_result.get('success'):
                return jsonify(
                    success=False,
                    message=f"Upload failed: {upload_result.get('error', 'Unknown error')}"
                ), 500

            logging.info(f"[UPLOAD] Uploader:{user_id} College:{college_id} Branch:{branch_id} Semester:{semester} Subject:{subject!r} SubjectID:{subject_id}")
            
            file_hash = request.form.get('file_hash', '').strip() or None
            exam_type = request.form.get('exam_type', '').strip() or ''
            subject_code = request.form.get('subject_code', '').strip() or ''

            file_record_result = save_file_record(
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
            
            if not file_record_result.get('success'):
                logging.error(f"[UPLOAD ERROR] Supabase record creation failed: {file_record_result.get('message')}")
                try:
                    delete_file_from_cloudinary(upload_result['public_id'], upload_result.get('resource_type', 'raw'))
                except Exception:
                    pass
                return jsonify(
                    success=False,
                    message=f"File uploaded to Cloudinary, but database record creation failed: {file_record_result.get('message')}"
                ), 500

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
                c = init_supabase()
                if c and user_id:
                    cnt_res = c.table('documents').select('id', count='exact').eq('uploader_id', user_id).execute()
                    if cnt_res and cnt_res.count is not None:
                        total_uploads = cnt_res.count
            except Exception:
                pass

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
    import app
    q = request.args.get('q', '').strip().lower()
    if not q or not getattr(app, 'data_cache', None):
        return jsonify({"subjects": [], "types": [], "authors": []})

    subjects, types, authors = {}, {}, {}
    for item in app.data_cache:
        s = item.get("subject", "")
        t = item.get("type", "")
        a = item.get("author", "")
        if q in app._normalize(s):
            subjects[s] = subjects.get(s, 0) + 1
        if q in app._normalize(t):
            types[t] = types.get(t, 0) + 1
        if q in app._normalize(a):
            authors[a] = authors.get(a, 0) + 1

    top_subjects = [k for k, _ in sorted(subjects.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    top_types    = [k for k, _ in sorted(types.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    top_authors  = [k for k, _ in sorted(authors.items(), key=lambda kv: kv[1], reverse=True)[:5]]

    return jsonify({"subjects": top_subjects, "types": top_types, "authors": top_authors})


@app_pages_bp.route('/dashboard/')
@auth_required
def index():
    return redirect(url_for('app_pages.dashboard'), code=301)


@app_pages_bp.route('/dashboard/search', methods=['POST', 'GET'])
@auth_required
def search():
    search_query = request.form.get('search') or request.args.get('search', '')
    if not search_query:
        return redirect(url_for('app_pages.dashboard'))
    return redirect(url_for('app_pages.dashboard', search_query=search_query))


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
    search_data = request.get_json()
    search_query = search_data.get('searchquery') if search_data else None
    if search_query:
        search_file = os.path.join(current_app.root_path, 'premium/static/search.json')
        search_entry = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'time': datetime.now().strftime('%H:%M:%S'),
            'searchquery': search_query
        }
        try:
            if os.path.exists(search_file):
                with open(search_file, 'r') as f:
                    searches = json.load(f)
            else:
                searches = []
            searches.append(search_entry)
            with open(search_file, 'w') as f:
                json.dump(searches, f, indent=4)
            return jsonify({'status': 'success'}), 200
        except Exception:
            return jsonify({'status': 'error'}), 500
    return jsonify({'status': 'error'}), 400


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

    og_title = f"{peer['name']} on AbhiHub"
    og_description = f"{peer['name']} has shared {len(uploads)} study materials on AbhiHub."

    return render_template('profile_instagram.html',
                           peer=peer,
                           uploads=uploads,
                           referred=referred,
                           memory_wall=memory_wall,
                           crush_state=crush_state,
                           og_title=og_title,
                           og_description=og_description,
                           og_image=None)

