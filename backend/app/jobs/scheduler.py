"""Scheduled background jobs.

In-season (Mar–Oct): nightly refresh of current-season league aggregates so
the cache is warm before users hit the dashboard.

Offseason: weekly light refresh.

Run in-process via APScheduler's BackgroundScheduler. The scheduler is
started in the API lifespan and skipped during tests (DIAMONDSCOPE_DISABLE_SCHEDULER=1).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger


log = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def refresh_current_season_aggregates() -> None:
    """Invalidate the current-season league aggregates so the next read
    re-fetches fresh data from FanGraphs / Statcast."""
    from app.data.cache import invalidate

    year = datetime.utcnow().year
    pitched = invalidate(f"pitching_stats:{year}")
    batted = invalidate(f"batting_stats:{year}")
    log.info(
        "nightly refresh: invalidated %d pitching + %d batting cache entries for %d",
        pitched, batted, year,
    )


def _is_in_season(month: int) -> bool:
    return 3 <= month <= 10


def start_scheduler() -> BackgroundScheduler | None:
    """Idempotent. Returns the running scheduler or None when disabled."""
    global _scheduler
    if os.environ.get("DIAMONDSCOPE_DISABLE_SCHEDULER") == "1":
        log.info("scheduler disabled via env")
        return None
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    sched = BackgroundScheduler(timezone="UTC")

    # Nightly at 09:00 UTC (~early morning ET, before users wake up). The
    # job body checks in-season vs offseason and adjusts.
    def nightly():
        now = datetime.utcnow()
        if _is_in_season(now.month):
            refresh_current_season_aggregates()
        else:
            # Offseason: only run on Sundays to limit upstream pressure.
            if now.weekday() == 6:
                refresh_current_season_aggregates()

    sched.add_job(
        nightly,
        trigger=CronTrigger(hour=9, minute=0),
        id="nightly_refresh",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )

    sched.start()
    _scheduler = sched
    log.info("scheduler started; nightly_refresh registered at 09:00 UTC")
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            log.exception("scheduler shutdown error")
        _scheduler = None
