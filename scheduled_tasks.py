"""
Scheduled Tasks Module
Background task scheduler for periodic jobs like upload notifications.
Uses APScheduler to run tasks at regular intervals.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

logging.basicConfig(level=logging.INFO)

# Global scheduler instance
scheduler = None


def init_scheduler(app=None):
    """
    Initialize the background scheduler for periodic tasks.
    
    Args:
        app: Flask app instance (optional, for logging context)
    
    Returns:
        BackgroundScheduler instance
    """
    global scheduler
    
    if scheduler is not None:
        logging.warning("Scheduler already initialized")
        return scheduler
    
    logging.info("Initializing background task scheduler...")
    
    # Create scheduler
    scheduler = BackgroundScheduler(daemon=True)
    
    # Add jobs
    setup_jobs(scheduler)
    
    # Start the scheduler
    scheduler.start()
    logging.info("✅ Background scheduler started successfully")
    
    # Shut down the scheduler when app exits
    atexit.register(lambda: shutdown_scheduler())
    
    return scheduler


def setup_jobs(scheduler):
    """
    Set up all scheduled jobs.
    
    Args:
        scheduler: APScheduler instance
    """
    # Import here to avoid circular imports
    from methods.upload_notifier import process_upload_notifications
    
    # Job 1: Check for upload notifications every 10 minutes
    scheduler.add_job(
        func=process_upload_notifications,
        trigger=IntervalTrigger(minutes=10),
        id='upload_notifications',
        name='Process upload notifications',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Upload notifications (every 10 minutes)")


def shutdown_scheduler():
    """
    Gracefully shut down the scheduler.
    """
    global scheduler
    
    if scheduler is not None:
        logging.info("Shutting down background scheduler...")
        scheduler.shutdown()
        scheduler = None
        logging.info("✅ Scheduler shut down successfully")


def get_scheduler():
    """
    Get the global scheduler instance.
    
    Returns:
        BackgroundScheduler instance or None
    """
    return scheduler


# CLI function for manual execution (can be called from Heroku Scheduler)
def run_upload_notifications_task():
    """
    Standalone function for running upload notifications.
    Can be called from Heroku Scheduler or Flask CLI.
    """
    from methods.upload_notifier import process_upload_notifications
    
    logging.info("Running upload notifications task (manual/scheduled execution)")
    result = process_upload_notifications()
    logging.info(f"Task complete: {result}")
    return result


if __name__ == '__main__':
    # For testing: run the task immediately
    run_upload_notifications_task()
