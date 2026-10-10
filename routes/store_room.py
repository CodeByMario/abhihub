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
)
from methods.cloudinary_helper import (
    search_files,
    filter_files,
    sort_files,
)

store_room_bp = Blueprint('store_room', __name__)

_unlabeled_cache = {
    'data': None,
    'labeled_count': 0,
    'timestamp': 0,
    'ttl': 60  # Cache for 60 seconds
}


def _mark_labeled(storage_provider, cloudinary_public_id):
    """Mark a storage asset as labeled."""
    storage_provider = storage_provider or ('cloudinary' if cloudinary_public_id else 'firebase')
    if cloudinary_public_id:
        mark_storage_asset_labeled(storage_provider, cloudinary_public_id)


def get_cached_unlabeled_files():
    now = time.time()
    if _unlabeled_cache['data'] is not None and (now - _unlabeled_cache['timestamp'] < _unlabeled_cache['ttl']):
        return _unlabeled_cache['data'], _unlabeled_cache['labeled_count']

    pending_assets = get_pending_storage_assets()

    unlabeled_files = []
    for f in pending_assets:
        unlabeled_files.append({
            'storage_provider': f.get('provider'),
            'storage_id': f.get('provider_public_id'),
            'filename': f.get('filename'),
            'url': f.get('public_url'),
            'path': f.get('public_url'),
            'created_at': f.get('uploaded_at'),
            'size': 'Unknown',
            'format': (f.get('mime') or 'unknown').split('/')[-1],
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

        result = save_file_record(
            user_id=user_id or user_email.split('@')[0],
            user_email=user_email,
            file_name=filename,
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
            subject_code=subject_code,
            semester=semester,
            title=custom_title or subject_name,
            description=custom_description,
            exam_type=exam_type,
            program=program
        )

        if result.get('success'):
            _mark_labeled(storage_provider, cloudinary_public_id)
            doc_id = result.get('data', {}).get('id')
            if doc_id:
                log_label_audit(
                    user_id=user_id or user_email.split('@')[0],
                    document_id=doc_id,
                    action='LABELED_FROM_QUEUE',
                    details={'subject_id': subject_id, 'branch_id': branch_id, 'college_id': college_id}
                )
            _unlabeled_cache['data'] = None
            return jsonify({
                'success': True,
                'message': 'Paper labeled successfully',
                'data': result.get('data', {})
            }), 200
        else:
            if result.get('conflict'):
                _mark_labeled(storage_provider, cloudinary_public_id)
                _unlabeled_cache['data'] = None
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
            all_files = search_files(all_files, search_query)

        if format_filter or folder_filter:
            all_files = filter_files(all_files, format_filter, folder_filter)

        all_files = sort_files(all_files, sort_by, order)

        total_papers = len(unlabeled_files) + sorted_papers
        remaining_papers = len(unlabeled_files)

        paginated_files = all_files[offset:offset + limit]
        has_more = (offset + limit) < total_papers

        return jsonify({
            'success': True,
            'files': paginated_files,
            'statistics': {
                'total': total_papers,
                'sorted': sorted_papers,
                'remaining': remaining_papers
            },
            'pagination': {
                'offset': offset,
                'limit': limit,
                'has_more': has_more,
                'total': total_papers
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

        college = data.get('college_name', '').strip()[:3].upper()
        subject_code = data.get('subject_code', '').strip() or data.get('subject_name', '')[:4].upper()
        exam_type = data.get('exam_type', 'unknown')[0].upper()
        year = data.get('year', '')
        branch = data.get('branch', '').strip()[:3].upper()
        semesters = data.get('semesters', [])
        sem = '-'.join(str(s) for s in semesters) if semesters else 'UNK'

        file_ext = os.path.splitext(original_filename)[1]
        new_filename = f"{college}_{subject_code}_{exam_type}_{year}_{branch}_{sem}{file_ext}"
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
