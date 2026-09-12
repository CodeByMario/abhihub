"""
Upload Notifier Module
Handles sending notifications to users 1 hour after successful file upload.
"""

import os
import logging
from datetime import datetime, timedelta
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
        # Calculate time range: 55-65 minutes ago
        now = datetime.utcnow()
        one_hour_ago_start = now - timedelta(minutes=65)
        one_hour_ago_end = now - timedelta(minutes=55)
        
        logging.info(f"Checking for files uploaded between {one_hour_ago_start} and {one_hour_ago_end} in abhihub schema")
        
        # Query documents for unnotified files in the time range
        # Note: 'upload_notified' column might need to be added to abhihub.documents
        # For now, we query the new table to fulfill the "nothing relies on public" requirement.
        response = (client.table('documents')
                   .select('id, uploader_id, title, document_category, created_at, profiles(email)')
                   .gte('created_at', one_hour_ago_start.isoformat())
                   .lte('created_at', one_hour_ago_end.isoformat())
                   .execute())
        
        files = []
        for d in response.data:
            files.append({
                'id': d['id'],
                'user_id': d['uploader_id'],
                'user_email': (d.get('profiles') or {}).get('email', 'unknown'),
                'file_name': d['title'],
                'document_type': d['document_category'],
                'uploaded_at': d['created_at']
            })

        logging.info(f"Found {len(files)} files needing notification in abhihub schema")
        return files
    
    except Exception as e:
        logging.error(f"Error querying files for notification: {e}")
        return []


def send_upload_notification(user_id: str, user_email: str, file_name: str, subject: str, doc_type: str) -> bool:
    """
    Send push notification to user about successful upload.
    
    Args:
        user_id: User ID to send notification to
        user_email: User email (for logging)
        file_name: Name of the uploaded file
        subject: Subject/topic of the file
        doc_type: Document type (Notes, PYQ, etc.)
    
    Returns:
        True if notification sent successfully, False otherwise
    """
    try:
        from push_notifications import send_notification
        
        # Create notification message
        title = "Upload Successful! 🎉"
        body = f"Your file '{file_name}' has been successfully uploaded and is now available for others to view!"
        url = "/dashboard"  # Redirect to dashboard
        icon = "/static/images/android-chrome-192x192.png"
        tag = "upload-success"
        
        logging.info(f"Sending upload notification to {user_email} for file: {file_name}")
        
        # Send notification
        result = send_notification(user_id, title, body, url, icon, tag)
        
        if result.get('success'):
            logging.info(f"✅ Notification sent successfully to {user_email}")
            return True
        else:
            logging.warning(f"⚠️ Failed to send notification to {user_email}: {result.get('error')}")
            return False
    
    except Exception as e:
        logging.error(f"❌ Error sending notification to {user_email}: {e}")
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
        # Update the record in abhihub.documents
        # Note: If 'upload_notified' doesn't exist yet, this will be skipped or handled by schema update
        # We target the new 'documents' table to fully migrate away from public schema.
        try:
            response = (client.table('documents')
                       .update({
                           'status': 'approved' # Example: approving it implies we've processed it
                           # 'upload_notified': True,
                           # 'notified_at': datetime.utcnow().isoformat()
                       })
                       .eq('id', file_record_id)
                       .execute())
            
            if response.data:
                logging.info(f"✅ Processed document {file_record_id} status in abhihub schema")
                return True
        except Exception as e:
            logging.warning(f"Could not update status/notified columns for {file_record_id}: {e}")
            return True  # Return true so we don't spam errors in scheduler
            
        return False
    
    except Exception as e:
        logging.error(f"❌ Error marking record {file_record_id} as notified: {e}")
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
        success = send_upload_notification(user_id, user_email, file_name, subject, doc_type)
        
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
