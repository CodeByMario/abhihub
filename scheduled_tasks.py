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
    from methods.indexer import process_pending_documents
    from methods.analytics_analyzer import analyze_search_metrics
    
    # Job 1: Check for upload notifications every 10 minutes
    scheduler.add_job(
        func=process_upload_notifications,
        trigger=IntervalTrigger(minutes=10),
        id='upload_notifications',
        name='Process upload notifications',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Upload notifications (every 10 minutes)")

    # Job 2: Process pending search index documents every 2 minutes
    scheduler.add_job(
        func=process_pending_documents,
        trigger=IntervalTrigger(minutes=2),
        id='search_indexer',
        name='Process search index queue',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Search Indexer (every 2 minutes)")

    # Job 3: Analytics Analyzer every 24 hours
    scheduler.add_job(
        func=analyze_search_metrics,
        trigger=IntervalTrigger(hours=24),
        id='analytics_analyzer',
        name='Search Analytics Analyzer',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Analytics Analyzer (every 24 hours)")

    # Job 4: Nightly rolling-score recalculation (AbhiHub Score, CCR, access level)
    def _recalc_scores():
        from methods.scoring_engine import recalculate_user_scores
        result = recalculate_user_scores()
        logging.info(f"[SCORING] nightly score recalc: {result}")

    scheduler.add_job(
        func=_recalc_scores,
        trigger=IntervalTrigger(hours=24),
        id='score_recalculator',
        name='Nightly user score recalculation',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Score Recalculator (every 24 hours)")

    # Job 5: Reconcile 30-day mature wallet earnings
    def _reconcile_wallets():
        try:
            from methods.wallet_service import unlock_eligible_entries
            unlocked = unlock_eligible_entries()
            logging.info(f"[WALLET] Daily unlock completed: {unlocked} entries matured")
        except Exception as e:
            logging.error(f"[WALLET] Daily unlock error: {e}")

    scheduler.add_job(
        func=_reconcile_wallets,
        trigger=IntervalTrigger(hours=24),
        id='wallet_unlock_reconciler',
        name='Daily wallet 30-day maturity unlock',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Wallet Maturity Unlocker (every 24 hours)")

    # Job 6: Hourly Tarika model catalog sync
    def _sync_model_catalog():
        try:
            import asyncio
            from services.catalog_sync import sync_all
            count = asyncio.run(sync_all())
            logging.info(f"[CATALOG] Model catalog sync completed: {count} verified models")
        except Exception as e:
            logging.error(f"[CATALOG] Model catalog sync error: {e}")

    scheduler.add_job(
        func=_sync_model_catalog,
        trigger=IntervalTrigger(hours=1),
        id='tarika_catalog_sync',
        name='Tarika AI model catalog sync',
        replace_existing=True
    )
    logging.info("📅 Scheduled job: Tarika Catalog Sync (every 1 hour)")



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
