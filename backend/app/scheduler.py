"""
APScheduler setup.

IMPORTANT: This scheduler runs in-process with FastAPI.
The uvicorn command MUST use --workers 1 (enforced in docker-compose.yml).
Adding workers will cause every scheduled job to fire N times.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _heartbeat():
    logger.debug("Scheduler heartbeat — running")


def init_scheduler():
    scheduler.add_job(
        _heartbeat,
        trigger=IntervalTrigger(minutes=5),
        id="heartbeat",
        replace_existing=True,
    )
    # Phase 2: Jira polling job added here
    # Phase 3: Alert engine job added here
    scheduler.start()
    logger.info("APScheduler started (single-worker mode)")
