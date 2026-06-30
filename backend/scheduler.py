# backend/scheduler.py
# ----------------------------------------------------------
# Runs the digest build automatically on a schedule so the user
# doesn't have to press the button. Uses APScheduler's background
# scheduler, which runs jobs in a separate thread alongside FastAPI.
#
# Default: every day at 07:00 server time. You can also trigger
# a run immediately with run_now() for testing.
# ----------------------------------------------------------

from apscheduler.schedulers.background import BackgroundScheduler

from backend.database import SessionLocal
from backend.digest_builder import build_digests_for_all_users

# One shared scheduler for the whole app
_scheduler = BackgroundScheduler()


def _daily_job():
    """
    The function the scheduler calls each morning.
    Opens its own DB session (the request-scoped get_db() isn't
    available here — this runs outside any web request).
    """
    print("[scheduler] daily digest job starting...")
    db = SessionLocal()
    try:
        report = build_digests_for_all_users(db)
        built = sum(1 for v in report.values() if v is not None)
        print(f"[scheduler] daily job done — built {built}/{len(report)} digests")
    finally:
        db.close()


def start_scheduler():
    """
    Called once at app startup (from main.py).
    Registers the daily job and starts the scheduler.
    """
    # Avoid adding the job twice if start is somehow called again
    if _scheduler.get_job("daily_digest") is None:
        _scheduler.add_job(
            _daily_job,
            trigger="cron",
            hour=7,
            minute=0,
            id="daily_digest",
            replace_existing=True,
        )
    if not _scheduler.running:
        _scheduler.start()
        print("[scheduler] started — daily digest scheduled for 07:00")


def stop_scheduler():
    """Called at app shutdown to stop the background thread cleanly."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[scheduler] stopped")


def run_now():
    """
    Manually trigger the daily job right now (for testing the
    scheduled path without waiting until 07:00).
    """
    _daily_job()
