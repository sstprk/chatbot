"""
APScheduler-based ingestion scheduler.

Runs Slack and Notion ingestors on a configurable interval,
and triggers an initial ingestion on startup.
"""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.ingestion.notion_ingestor import ingest_notion
from app.ingestion.slack_ingestor import ingest_slack

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_all_ingestors() -> None:
    """Execute all ingestors and log results."""
    logger.info("── Ingestion cycle started ──")

    try:
        slack_count = await ingest_slack()
        logger.info("Slack ingestion complete: %d chunks upserted", slack_count)
    except Exception:
        logger.error("Slack ingestion failed", exc_info=True)

    try:
        notion_count = await ingest_notion()
        logger.info("Notion ingestion complete: %d chunks upserted", notion_count)
    except Exception:
        logger.error("Notion ingestion failed", exc_info=True)

    logger.info("── Ingestion cycle finished ──")


def start_scheduler() -> AsyncIOScheduler:
    """
    Create and start the APScheduler scheduler.

    Registers both ingestors to run at the configured interval.
    The scheduler is returned so it can be shut down on app teardown.
    """
    global _scheduler

    _scheduler = AsyncIOScheduler()

    _scheduler.add_job(
        _run_all_ingestors,
        trigger="interval",
        minutes=settings.ingestion_interval_minutes,
        id="ingestion_cycle",
        name="Periodic knowledge ingestion",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — ingestion every %d minutes",
        settings.ingestion_interval_minutes,
    )

    return _scheduler


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
        _scheduler = None


async def run_initial_ingestion() -> None:
    """Run all ingestors once (called on app startup)."""
    logger.info("Running initial ingestion on startup...")
    await _run_all_ingestors()
