"""
Store Room Blueprint (Phase 5.9A Routing Overhaul)
Handles file curation, labeling queue, storage sync, verification, and asset renaming.
"""
import os
import re
import time
import logging
from datetime import datetime
from flask import Blueprint, request, jsonify, session

from routes.auth import auth_required
from methods.supabase_helper import (
    init_supabase,
    get_pending_storage_assets,
    mark_storage_asset_labeled,
    verify_hierarchy,
    save_file_record,
    log_label_audit,
    add_paper_verification,
    get_pending_verification_papers,
    validate_uuid,
    invalidate_files_cache,
)
from methods.cloudinary_helper import (
    search_files,
    filter_files,
    sort_files,
    build_inverted_index,
)


store_room_bp = Blueprint('store_room', __name__)

_unlabeled_cache = {
    'data': None,
    'labeled_count': 0,
    'timestamp': 0,
    'ttl': 60  # Cache for 60 seconds
}

# Cache the last sort result to avoid re-sorting on every API call
_SORTED_CACHE: dict = {'key': None, 'data': []}


def _mark_labeled(storage_provider, cloudinary_public_id, filename=None, file_url=None):
    """Mark a storage asset as labeled."""
    storage_provider = storage_provider or ('cloudinary' if cloudinary_public_id else 'firebase')
    mark_storage_asset_labeled(storage_provider, cloudinary_public_id, filename=filename, url=file_url)


def get_cached_unlabeled_files():
    now = time.time()
    if _unlabeled_cache['data'] is not None and (now - _unlabeled_cache['timestamp'] < _unlabeled_cache['ttl']):
        return _unlabeled_cache['data'], _unlabeled_cache['labeled_count']

    pending_assets = get_pending_storage_assets()

    # Load fast in-memory lookup for original file size, bytes, format, and timestamp
    extra_lookup = {}
    try:
        import os, json
        cache_path = os.path.join("data", "cache", "cloudinary_files_cache.json")
        if os.path.exists(cache_path):
            with open(cache_path, 'r', encoding='utf-8') as cf_file:
                cdata = json.load(cf_file)
                for cf in cdata.get('files', []):
                    pid = cf.get('public_id')
                    if pid:
                        extra_lookup[pid] = {
                            'size': cf.get('size'),
                            'bytes': cf.get('bytes'),
                            'created_at': cf.get('created_at'),
                            'format': cf.get('format')
                        }
    except Exception as c_err:
        logging.debug(f"[STORE-ROOM] Cloudinary cache lookup note: {c_err}")

    unlabeled_files = []
    for f in pending_assets:
        storage_id = f.get('provider_public_id')
        extra = extra_lookup.get(storage_id) or {}
        unlabeled_files.append({
            'storage_provider': f.get('provider'),
            'storage_id': storage_id,
            'filename': f.get('filename'),
            'url': f.get('public_url'),
            'path': f.get('public_url'),
            'created_at': extra.get('created_at') or f.get('uploaded_at') or f.get('created_at'),
            'size': extra.get('size') or 'Unknown',
            'bytes': extra.get('bytes') or 0,
            'format': (extra.get('format') or (f.get('mime') or 'unknown').split('/')[-1]).lower(),
            'record_id': None,
            'verified': False,
            'verification_status': None,
            'like_count': 0,
            'bookmark_count': 0,
            'comment_count': 0,
            'view_count': 0
        })

    labeled_count = 0
    try:
        client = init_supabase()
        if client:
            res = client.table('storage_assets').select('id', count='exact').eq('status', 'LABELED').execute()
            labeled_count = res.count or 0
    except Exception as e:
        logging.warning(f"[STORE-ROOM] Error fetching labeled count: {e}")

    _unlabeled_cache['data'] = unlabeled_files
    _unlabeled_cache['labeled_count'] = labeled_count
    _unlabeled_cache['timestamp'] = now

    # Build inverted index once on cache fill for O(1) search lookups
    global _SORTED_CACHE
    _SORTED_CACHE = {'key': None, 'data': []}  # invalidate stale sort cache
    _unlabeled_cache['index'] = build_inverted_index(unlabeled_files)

    return unlabeled_files, labeled_count


@store_room_bp.route('/store-room/api/label', methods=['POST'])
@auth_required
def label_store_room_paper():
    """
    Label a paper from store room and save to file_records table.
    Expects JSON with: filename, url, college_name, subject_name, branch, year, exam_type, etc.
    """
    global _unlabeled_cache
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        user_email = user_info.get('email', '')

        if not user_email:
            return jsonify({
                'success': False,
                'message': 'User not authenticated'
            }), 401

        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'message': 'No data provided'
            }), 400

        filename = data.get('filename', '')
        file_url = data.get('url', '')
        college_id = data.get('college_id', '').strip() or None
        branch_id = data.get('branch_id', '').strip() or None
        subject_id = data.get('subject_id', '').strip() or None
        subject_name = data.get('subject_name', '')
        subject_code = data.get('subject_code', '')
        year_raw = data.get('year', '')
        year = str(year_raw)
        try:
            year_int = int(year_raw)
            current_year = datetime.now().year
            if year_int < 1900 or year_int > current_year + 1:
                return jsonify({'success': False, 'message': 'Invalid year provided'}), 400
        except Exception:
            return jsonify({'success': False, 'message': 'Year must be a number'}), 400

        custom_title = data.get('title', '')
        document_category = data.get('document_category', 'papers')
        custom_description = data.get('description', '')
        exam_type = data.get('exam_type', '')
        program = data.get('program', 'b.tech') or 'b.tech'
        semester_raw = data.get('semester')
        semester = int(semester_raw) if semester_raw and str(semester_raw).isdigit() and 1 <= int(semester_raw) <= 8 else None

        missing_fields = []
        if not filename: missing_fields.append('filename')
        if not file_url: missing_fields.append('url')
        if not subject_name and document_category.lower() != 'question_bank': missing_fields.append('subject_name')
        if not year: missing_fields.append('year')

        if missing_fields:
            return jsonify({'success': False, 'message': f'Missing required fields: {", ".join(missing_fields)}'}), 400
        if not subject_id and document_category.lower() != 'question_bank':
            return jsonify({'success': False, 'message': 'Subject selection is required'}), 400

        if not verify_hierarchy(college_id, branch_id, subject_id):
            return jsonify({'success': False, 'message': 'Invalid academic hierarchy (mismatched college/branch/subject)'}), 400

        allowed_categories = ['papers', 'notes', 'practical', 'syllabus', 'assisment', 'timetable', 'question_bank']
        if document_category not in allowed_categories:
            document_category = 'papers'

        storage_provider = (data.get('storage_provider') or '').strip().lower()
        cloudinary_public_id = (data.get('provider_public_id') or '').strip()
        if not cloudinary_public_id and 'cloudinary.com' in file_url:
            parts = file_url.split('/')
            if 'upload' in parts:
                idx = parts.index('upload')
                if idx + 1 < len(parts):
                    p_id_ext = '/'.join(parts[idx + 1:])
                    p_id_ext = re.sub(r'^v\d+/', '', p_id_ext)
                    cloudinary_public_id = p_id_ext.rsplit('.', 1)[0]
        if not cloudinary_public_id:
            cloudinary_public_id = filename

        file_ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
        file_type = 'pdf' if file_ext == 'pdf' else 'image'

        # Resolve abbreviations for College, Branch, Subject, Subject Code
        col_abbr = (data.get('college_abbr') or '').strip().upper()
        dept_abbr = (data.get('branch_abbr') or data.get('department_abbr') or '').strip().upper()
        subj_abbr = (data.get('subject_abbr') or '').strip().upper()
        subj_code = (subject_code or data.get('subject_code') or '').strip().upper()

        if program and program.lower() != 'b.tech' and (not dept_abbr or dept_abbr in ('ALL', 'ABA')):
            dept_abbr = re.sub(r'[^a-zA-Z0-9]', '', program).upper()

        from methods.supabase_helper import init_supabase, make_acronym
        client_sb = init_supabase()
        if client_sb:
            if not col_abbr and college_id:
                try:
                    c_row = client_sb.table('colleges').select('name, abbreviation').eq('id', college_id).limit(1).execute()
                    if c_row.data:
                        col_abbr = (c_row.data[0].get('abbreviation') or make_acronym(c_row.data[0].get('name'))).strip().upper()
                except Exception:
                    pass
            if not dept_abbr and branch_id:
                try:
                    d_row = client_sb.table('departments').select('name, abbreviation').eq('id', branch_id).limit(1).execute()
                    if d_row.data:
                        dept_abbr = (d_row.data[0].get('abbreviation') or make_acronym(d_row.data[0].get('name'))).strip().upper()
                except Exception:
                    pass
            if subject_id:
                try:
                    s_row = client_sb.table('subjects').select('name, subject_code').eq('id', subject_id).limit(1).execute()
                    if s_row.data:
                        if not subj_code:
                            subj_code = (s_row.data[0].get('subject_code') or '').strip().upper()
                        if not subj_abbr:
                            subj_abbr = make_acronym(s_row.data[0].get('name') or subject_name)
                except Exception:
                    pass

        if col_abbr == 'GHRCEG':
            col_abbr = 'GHRCE'
        if dept_abbr == 'ABA':
            dept_abbr = 'MBA'

        if not subj_abbr and subject_name:
            subj_abbr = make_acronym(subject_name)

        # Standardize title: CollegeAbbr - DeptAbbr - SubjAbbr (SubjectCode) - Details
        prefix_tags = [p for p in [col_abbr, dept_abbr, subj_abbr] if p]
        header = " - ".join(prefix_tags)
        if subj_code and subj_code not in header:
            header = f"{header} ({subj_code})" if header else subj_code

        cat_title = document_category.replace('_', ' ').title()
        exam_title = exam_type.upper() if exam_type else ''
        details_list = [p for p in [exam_title, cat_title, str(year)] if p]
        details_str = " · ".join(details_list)

        if not custom_title or custom_title.lower() == subject_name.lower():
            final_title = f"{header} - {details_str}" if header else (details_str or subject_name)
        elif header and not custom_title.startswith(col_abbr) and not custom_title.startswith(header) and header not in custom_title:
            final_title = f"{header} - {custom_title}"
        else:
            final_title = custom_title or subject_name

        final_title = final_title.replace('GHRCEG', 'GHRCE').replace('ABA', 'MBA')

        # Standardize filename: CollegeAbbr_DeptAbbr_SubjAbbr_SubjCode_Exam_Category_Year.ext
        fn_components = [p for p in [col_abbr, dept_abbr, subj_abbr, subj_code, exam_title, cat_title.replace(' ', ''), str(year)] if p]
        if fn_components:
            clean_filename = "_".join(re.sub(r'[^a-zA-Z0-9]', '', c) for c in fn_components) + f".{file_ext}"
            clean_filename = clean_filename.replace('GHRCEG', 'GHRCE').replace('ABA', 'MBA')
        else:
            clean_filename = filename

        result = save_file_record(
            user_id=user_id or user_email.split('@')[0],
            user_email=user_email,
            file_name=clean_filename,
            file_url=file_url,
            file_type=file_type,
            file_size=0,
            cloudinary_public_id=cloudinary_public_id,
            subject_name=subject_name,
            document_type=document_category,
            year=year,
            college_id=college_id,
            branch_id=branch_id,
            subject_id=subject_id,
            subject_code=subj_code,
            semester=semester,
            title=final_title,
            description=custom_description,
            exam_type=exam_type,
            program=program
        )

        if result.get('success'):
            _mark_labeled(storage_provider, cloudinary_public_id, filename=filename, file_url=file_url)
            doc_data = result.get('data', {})
            doc_id = doc_data.get('id')
            uploader_uid = doc_data.get('uploader_id') or user_id
            if doc_id and uploader_uid:
                log_label_audit(
                    user_id=uploader_uid,
                    document_id=doc_id,
                    action='LABELED_FROM_QUEUE',
                    details={'subject_id': subject_id, 'branch_id': branch_id, 'college_id': college_id}
                )
            _unlabeled_cache['data'] = None
            invalidate_files_cache()
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': doc_data
            }), 200
        else:
            if result.get('conflict'):
                _mark_labeled(storage_provider, cloudinary_public_id, filename=filename, file_url=file_url)
                _unlabeled_cache['data'] = None
                invalidate_files_cache()
                return jsonify({
                    'success': True,
                    'message': 'File was already labeled and has been removed from the Store Room queue.',
                    'data': result.get('data', {})
                }), 200
            status_code = 409 if result.get('conflict') else 500
            return jsonify({
                'success': False,
                'message': result.get('message', 'Failed to save label')
            }), status_code

    except Exception as e:
        logging.error(f"[STORE_ROOM_LABEL] EXCEPTION: {e}")
        return jsonify({
            'success': False,
            'message': f'Error labeling paper: {str(e)}'
        }), 500


@store_room_bp.route('/store-room/api/sync', methods=['POST'])
@auth_required
def store_room_api_sync():
    """Triggers a manual synchronization from physical storage to the storage_assets table."""
    try:
        from methods.storage_providers import CloudinaryProvider
        provider = CloudinaryProvider()
        result = provider.sync()

        if result.get('success'):
            global _unlabeled_cache
            _unlabeled_cache['data'] = None
            return jsonify({'success': True, 'message': f"Synced {result.get('upserted', 0)} assets successfully."}), 200
        else:
            return jsonify({'success': False, 'message': result.get('message', 'Sync failed')}), 500
    except Exception as e:
        logging.error(f"Error syncing storage: {e}")
@store_room_bp.route('/store-room/api/history', methods=['GET'])
@auth_required
def store_room_api_history():
    """Fetch history of papers labeled/curated by current user."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        user_email = user_info.get('email', '')
        if not user_id and not user_email:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 401

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'data': []})

        history_list = []
        seen_doc_ids = set()

        try:
            user_candidates = []
            if user_id and validate_uuid(user_id):
                user_candidates.append(user_id)
            if user_email:
                try:
                    p_res = client.table('profiles').select('id').eq('email', user_email).limit(1).execute()
                    if p_res.data and p_res.data[0].get('id'):
                        p_id = p_res.data[0]['id']
                        if validate_uuid(p_id) and p_id not in user_candidates:
                            user_candidates.append(p_id)
                except Exception:
                    pass

            if not user_candidates:
                return jsonify({'success': True, 'count': 0, 'data': []}), 200

            query = (
                client.table('label_audit_logs')
                .select('id, document_id, action, created_at, documents(id, title, document_category, file_url, view_count, status, created_at, college_id, department_id, subject_id, exam_type, semester, description, colleges(name, abbreviation), subjects(name, subject_code))')
                .eq('action', 'LABELED_FROM_QUEUE')
                .in_('user_id', user_candidates)
                .order('created_at', desc=True)
                .limit(100)
            )
            res = query.execute()
            for row in (res.data or []):
                doc = row.get('documents') or {}
                doc_id = doc.get('id') or row.get('document_id')
                if doc and doc.get('id') and doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    col = doc.get('colleges') or {}
                    sub = doc.get('subjects') or {}
                    desc_str = doc.get('description') or ''
                    year_val = ''
                    if desc_str and desc_str.startswith('{'):
                        try:
                            import json
                            desc_data = json.loads(desc_str)
                            year_val = str(desc_data.get('year') or '')
                        except Exception:
                            pass
                    if not year_val and doc.get('title'):
                        ym = re.search(r'\b(201\d|202\d)\b', doc.get('title'))
                        if ym: year_val = ym.group(1)

                    history_list.append({
                        'id': doc_id,
                        'title': doc.get('title') or 'Cataloged Resource',
                        'category': doc.get('document_category') or 'papers',
                        'college_id': doc.get('college_id') or '',
                        'branch_id': doc.get('department_id') or '',
                        'subject_id': doc.get('subject_id') or '',
                        'college': col.get('abbreviation') or col.get('name') or '',
                        'subject': sub.get('name') or '',
                        'subject_code': sub.get('subject_code') or '',
                        'semester': doc.get('semester') or '',
                        'year': year_val or '',
                        'exam_type': doc.get('exam_type') or '',
                        'file_url': doc.get('file_url') or '',
                        'view_count': doc.get('view_count') or 0,
                        'status': doc.get('status') or 'approved',
                        'labeled_at': row.get('created_at') or doc.get('created_at') or ''
                    })
        except Exception as audit_err:
            logging.warning(f"[STORE_ROOM_HISTORY] Audit log fetch failed: {audit_err}")

        return jsonify({
            'success': True,
            'count': len(history_list),
            'data': history_list
        }), 200
    except Exception as e:
        logging.error(f"[STORE_ROOM_HISTORY] Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@store_room_bp.route('/store-room/api/edit-label', methods=['POST'])
@auth_required
def edit_store_room_label():
    """Edit an existing labeled document record."""
    try:
        user_info = session.get('user', {})
        user_id = user_info.get('uid', '')
        user_email = user_info.get('email', '')
        if not user_email:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401

        data = request.get_json() or {}
        doc_id = data.get('document_id') or data.get('record_id')
        if not doc_id:
            return jsonify({'success': False, 'message': 'Document ID is required'}), 400

        client = init_supabase()
        if not client:
            return jsonify({'success': False, 'message': 'Database unavailable'}), 500

        d_res = client.table('documents').select('*').eq('id', doc_id).limit(1).execute()
        if not d_res.data:
            return jsonify({'success': False, 'message': 'Document not found'}), 404
        doc = d_res.data[0]

        from routes.auth import is_admin_user
        is_admin = is_admin_user(user_info)
        is_uploader = bool(user_id and str(doc.get('uploader_id') or '') == str(user_id))
        if not (is_admin or is_uploader):
            return jsonify({'success': False, 'message': 'Unauthorized to modify this label'}), 403

        college_id = (data.get('college_id') or '').strip() or None
        branch_id = (data.get('branch_id') or '').strip() or None
        subject_id = (data.get('subject_id') or '').strip() or None
        subject_name = (data.get('subject_name') or '').strip()
        subject_code = (data.get('subject_code') or '').strip()
        year_raw = data.get('year', '')
        year = str(year_raw).strip()
        custom_title = (data.get('title') or '').strip()
        document_category = data.get('document_category', 'papers')
        exam_type = (data.get('exam_type') or '').strip()
        semester_raw = data.get('semester')
        semester = int(semester_raw) if semester_raw and str(semester_raw).isdigit() and 1 <= int(semester_raw) <= 8 else None

        allowed_categories = ['papers', 'notes', 'practical', 'syllabus', 'assisment', 'timetable', 'question_bank']
        if document_category not in allowed_categories:
            document_category = 'papers'

        from methods.supabase_helper import make_acronym
        col_abbr = (data.get('college_abbr') or '').strip().upper()
        dept_abbr = (data.get('branch_abbr') or data.get('department_abbr') or '').strip().upper()
        subj_abbr = (data.get('subject_abbr') or '').strip().upper()
        subj_code = (subject_code or '').strip().upper()

        prog_val = (data.get('program') or doc.get('program') or '').strip()
        if prog_val and prog_val.lower() != 'b.tech' and (not dept_abbr or dept_abbr in ('ALL', 'ABA')):
            dept_abbr = re.sub(r'[^a-zA-Z0-9]', '', prog_val).upper()

        if not col_abbr and college_id:
            try:
                c_row = client.table('colleges').select('name, abbreviation').eq('id', college_id).limit(1).execute()
                if c_row.data:
                    col_abbr = (c_row.data[0].get('abbreviation') or make_acronym(c_row.data[0].get('name'))).strip().upper()
            except Exception:
                pass
        if not dept_abbr and branch_id:
            try:
                d_row = client.table('departments').select('name, abbreviation').eq('id', branch_id).limit(1).execute()
                if d_row.data:
                    dept_abbr = (d_row.data[0].get('abbreviation') or make_acronym(d_row.data[0].get('name'))).strip().upper()
            except Exception:
                pass
        if subject_id:
            try:
                s_row = client.table('subjects').select('name, subject_code').eq('id', subject_id).limit(1).execute()
                if s_row.data:
                    if not subj_code:
                        subj_code = (s_row.data[0].get('subject_code') or '').strip().upper()
                    if not subj_abbr:
                        subj_abbr = make_acronym(s_row.data[0].get('name') or subject_name)
            except Exception:
                pass

        if col_abbr == 'GHRCEG':
            col_abbr = 'GHRCE'
        if dept_abbr == 'ABA':
            dept_abbr = 'MBA'

        if not subj_abbr and subject_name:
            subj_abbr = make_acronym(subject_name)

        prefix_tags = [p for p in [col_abbr, dept_abbr, subj_abbr] if p]
        header = " - ".join(prefix_tags)
        if subj_code and subj_code not in header:
            header = f"{header} ({subj_code})" if header else subj_code

        cat_title = document_category.replace('_', ' ').title()
        exam_title = exam_type.upper() if exam_type else ''
        details_list = [p for p in [exam_title, cat_title, str(year) if year else ''] if p]
        details_str = " · ".join(details_list)

        final_title = custom_title or (f"{header} - {details_str}" if header else (details_str or subject_name or doc.get('title')))
        final_title = final_title.replace('GHRCEG', 'GHRCE').replace('ABA', 'MBA')

        import json
        desc_obj = {}
        if doc.get('description'):
            try:
                desc_obj = json.loads(doc.get('description'))
            except Exception:
                pass
        if not isinstance(desc_obj, dict):
            desc_obj = {}
        if subject_name: desc_obj['subject'] = subject_name
        if year: desc_obj['year'] = year
        if subj_code: desc_obj['subject_code'] = subj_code
        if semester: desc_obj['semester'] = semester

        update_data = {
            'title': final_title,
            'college_id': college_id,
            'department_id': branch_id,
            'subject_id': subject_id,
            'document_category': document_category,
            'exam_type': exam_type or None,
            'semester': semester,
            'description': json.dumps(desc_obj) if desc_obj else doc.get('description')
        }

        up_res = client.table('documents').update(update_data).eq('id', doc_id).execute()
        if up_res.data:
            log_label_audit(
                user_id=user_id or doc.get('uploader_id'),
                document_id=doc_id,
                action='LABELED_EDITED',
                details={'subject_id': subject_id, 'branch_id': branch_id, 'college_id': college_id}
            )
            invalidate_files_cache()
            return jsonify({
                'success': True,
                'message': 'Document label updated successfully',
                'data': up_res.data[0]
            }), 200
        else:
            return jsonify({'success': False, 'message': 'Failed to update record in database'}), 500

    except Exception as e:
        logging.error(f"[STORE_ROOM_EDIT_LABEL] Exception: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


@store_room_bp.route('/store-room/api/unlabeled', methods=['GET'])
@auth_required
def store_room_api_unlabeled():
    """API endpoint for fetching unlabeled queue files."""
    try:
        search_query = request.args.get('search', '')
        sort_by = request.args.get('sort_by', 'created_at')
        order = request.args.get('order', 'desc')
        format_filter = request.args.get('format', '')
        folder_filter = request.args.get('folder', '')

        offset = int(request.args.get('offset', 0))
        limit = int(request.args.get('limit', 20))

        unlabeled_files, sorted_papers = get_cached_unlabeled_files()
        all_files = unlabeled_files

        if search_query:
            _idx = _unlabeled_cache.get('index')  # use pre-built inverted index
            all_files = search_files(all_files, search_query, _index=_idx)

        if format_filter or folder_filter:
            all_files = filter_files(all_files, format_filter, folder_filter)

        # Only re-sort when params change — avoids O(n log n) on every request
        sort_key = f"{sort_by}:{order}:{search_query}:{format_filter}:{folder_filter}"
        if _SORTED_CACHE['key'] != sort_key:
            _SORTED_CACHE['data'] = sort_files(all_files, sort_by, order)
            _SORTED_CACHE['key'] = sort_key
        all_files = _SORTED_CACHE['data']

        total_papers = len(unlabeled_files) + sorted_papers
        remaining_papers = len(unlabeled_files)

        paginated_files = all_files[offset:offset + limit]
        has_more = (offset + limit) < len(all_files)

        return jsonify({
            'success': True,
            'files': paginated_files,
            'statistics': {
                'total': total_papers,
                'sorted': sorted_papers,
                'remaining': remaining_papers,
                'filtered': len(all_files)
            },
            'pagination': {
                'offset': offset,
                'limit': limit,
                'has_more': has_more,
                'total': len(all_files)
            }
        })
    except Exception as e:
        logging.error(f"Error fetching files: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@store_room_bp.route('/store-room/api/rename-file', methods=['POST'])
@auth_required
def store_room_api_rename_file():
    """API endpoint for renaming files with metadata in filename."""
    try:
        data = request.get_json() or {}
        original_filename = data.get('filename', '')
        if not original_filename:
            return jsonify({'success': False, 'message': 'Filename required'}), 400

        college = (data.get('college_name') or '').strip()[:3].upper()
        subject_code = (data.get('subject_code') or '').strip() or (data.get('subject_name') or '')[:4].upper()
        raw_exam = (data.get('exam_type') or 'unknown').strip()
        exam_type = raw_exam[0].upper() if raw_exam else 'U'
        year = data.get('year', '')
        branch = data.get('branch', '').strip()[:3].upper()
        semesters = data.get('semesters', [])
        sem = '-'.join(str(s) for s in semesters) if semesters else 'UNK'

        file_ext = os.path.splitext(original_filename)[1]
        parts = [p for p in [college, subject_code, exam_type, str(year) if year else '', branch, sem] if p]
        new_filename = "_".join(parts) + file_ext
        new_filename = "".join(c for c in new_filename if c.isalnum() or c in ('_', '.'))

        return jsonify({
            'success': True,
            'message': 'File renamed successfully',
            'new_filename': new_filename,
            'original_filename': original_filename
        })
    except Exception as e:
        logging.error(f"Error renaming file: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@store_room_bp.route('/store-room/api/verify', methods=['POST'])
@auth_required
def store_room_api_verify():
    """API endpoint for verifying a labeled paper."""
    try:
        data = request.get_json() or {}
        labeled_paper_id = data.get('paper_id')
        if not labeled_paper_id:
            return jsonify({'success': False, 'message': 'Paper ID required'}), 400

        user_email = session.get('user', {}).get('email', '')
        if not user_email:
            return jsonify({'success': False, 'message': 'User not authenticated'}), 401

        result = add_paper_verification(labeled_paper_id, user_email)
        return jsonify(result)
    except Exception as e:
        logging.error(f"Error verifying paper: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@store_room_bp.route('/store-room/api/verification-queue', methods=['GET'])
@auth_required
def store_room_api_verification_queue():
    """API endpoint to get papers pending verification."""
    try:
        result = get_pending_verification_papers()
        return jsonify(result), 200 if result.get('success') else 400
    except Exception as e:
        logging.error(f"Error adding verification: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
