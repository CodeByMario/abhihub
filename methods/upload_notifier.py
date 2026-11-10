"""
Upload Notifier Module
Handles sending notifications to users 1 hour after successful file upload.
"""

import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List
from methods.supabase_helper import init_supabase

logging.basicConfig(level=logging.INFO)


def get_files_needing_notification() -> List[Dict]:
    """
    Query file_records table for files uploaded ~1 hour ago that haven't been notified.
    
    Returns:
        List of file records that need notification
    """
    client = init_supabase()
    
    if not client:
        logging.error("Supabase client not available for notification check")
        return []
    
    try:
        # Gap-proof notification query: Any unnotified file created at least 55 minutes ago
        now = datetime.now(timezone.utc)
        one_hour_ago_cutoff = now - timedelta(minutes=55)
        
        logging.info(f"Checking for unnotified files uploaded before {one_hour_ago_cutoff} in abhihub schema")
        
        response = (client.table('documents')
                   .select('id, uploader_id, title, document_category, created_at, profiles!documents_uploader_id_fkey(email)')
                   .lte('created_at', one_hour_ago_cutoff.isoformat())
                   .is_('upload_notified', 'null')
                   .limit(50)
                   .execute())
        
        files = []
        for d in response.data or []:
            prof = d.get('profiles')
            user_email = (prof.get('email') if isinstance(prof, dict) else (prof[0].get('email') if isinstance(prof, list) and prof else 'unknown')) or 'unknown'
            files.append({
                'id': d['id'],
                'user_id': d['uploader_id'],
                'user_email': user_email,
                'file_name': d['title'],
                'document_type': d['document_category'],
                'uploaded_at': d['created_at']
            })

        logging.info(f"Found {len(files)} files needing notification in abhihub schema")
        return files
    
    except Exception as e:
        if "10035" in str(e) or "WinError" in str(e):
            try:
                from methods.supabase_helper import reset_thread_client
                reset_thread_client()
            except Exception:
                pass
        logging.error(
            "Error querying files for notification (error_type=%s)",
            type(e).__name__,
        )
        return []


def send_upload_notification(user_id: str, user_email: str, file_name: str, subject: str, doc_type: str, file_id: str = None) -> bool:
    """
    Send push notification to user about successful upload.
    
    Args:
        user_id: User ID to send notification to
        user_email: User email (for logging)
        file_name: Name of the uploaded file
        subject: Subject/topic of the file
        doc_type: Document type (Notes, PYQ, etc.)
        file_id: Optional document UUID for direct resource deep-linking
    
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        from push_notifications import send_notification
        
        title = "AbhiHub · Document Published"
        clean_name = str(file_name or 'study material')[:40]
        body = f"Your {doc_type.lower() if doc_type else 'document'} '{clean_name}' is now live and accessible to students."
        url = f"/resource/{file_id}" if file_id else "/dashboard"
        icon = "/static/images/android-chrome-192x192.png"
        tag = f"upload-{file_id}" if file_id else "upload-published"
        
        logging.info("Sending upload notification (document_type=%s)", doc_type)
        
        # Send notification with category='uploads'
        result = send_notification(user_id, title, body, url, icon, tag, category="uploads")
        
        if result.get('success'):
            logging.info("✅ Upload notification sent successfully")
            return True
        else:
            logging.warning("⚠️ Upload notification delivery failed")
            return False
    
    except Exception as e:
        logging.error(
            "❌ Error sending upload notification (error_type=%s)",
            type(e).__name__,
        )
        return False


def mark_as_notified(file_record_id: str) -> bool:
    """
    Mark a file record as notified in the database.
    
    Args:
        file_record_id: UUID of the file record
    
    Returns:
        True if marked successfully, False otherwise
    """
    client = init_supabase()
    
    if not client:
        logging.error("Supabase client not available")
        return False
    
    try:
        try:
            response = (client.table('documents')
                       .update({
                           'upload_notified': True,
                           'notified_at': datetime.now(timezone.utc).isoformat()
                       })
                       .eq('id', file_record_id)
                       .execute())
            
            if response.data:
                logging.info("✅ Marked upload notification as complete")
                return True
        except Exception as e:
            logging.warning(
                "Could not mark upload notification as complete (error_type=%s)",
                type(e).__name__,
            )
            return True  # Return true so we don't spam errors in scheduler
            
        return False
    
    except Exception as e:
        logging.error(
            "❌ Error marking upload notification as complete (error_type=%s)",
            type(e).__name__,
        )
        return False


def process_upload_notifications() -> Dict:
    """
    Main function to process all pending upload notifications.
    Queries for files needing notification, sends notifications, and marks them as notified.
    
    Returns:
        Dictionary with statistics: {sent: int, failed: int, total: int}
    """
    logging.info("=== Starting upload notification processing ===")
    
    # Get files needing notification
    files = get_files_needing_notification()
    
    if not files:
        logging.info("No files need notification at this time")
        return {'sent': 0, 'failed': 0, 'total': 0}
    
    sent_count = 0
    failed_count = 0
    
    for file_record in files:
        file_id = file_record.get('id')
        user_id = file_record.get('user_id')
        user_email = file_record.get('user_email')
        file_name = file_record.get('file_name')
        subject = file_record.get('subject_name', 'Unknown')
        doc_type = file_record.get('document_type', 'File')
        
        # Send notification
        success = send_upload_notification(user_id, user_email, file_name, subject, doc_type, file_id=file_id)
        
        if success:
            # Mark as notified
            if mark_as_notified(file_id):
                sent_count += 1
            else:
                failed_count += 1
        else:
            # Even if notification fails, mark as attempted to avoid retrying forever
            # But don't count it as success
            mark_as_notified(file_id)
            failed_count += 1
    
    logging.info(f"=== Notification processing complete: {sent_count} sent, {failed_count} failed out of {len(files)} total ===")
    
    return {
        'sent': sent_count,
        'failed': failed_count,
        'total': len(files)
    }


if __name__ == '__main__':
    # For testing: can be run directly
    process_upload_notifications()
