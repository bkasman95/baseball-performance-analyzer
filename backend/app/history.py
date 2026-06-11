"""Analysis-history recording helpers.

The analysis endpoint calls these to log each query into `analysis_history`.
Two paths:

  * `record_cache_hit(...)` — synchronous: the result is already known, so
    we insert a fully-populated `complete` row.

  * `start_history_row(...)` + `wrap_job_for_history(...)` — async: we
    insert a `running` row at request time and let the wrapped job's
    completion update it with timing, size, and final status.

All DB work is in short sessions so it can't share a session with a request
handler — the wrapped job runs on a separate thread pool.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable

from app.db import SessionLocal
from app.models.analysis_history import AnalysisHistory


log = logging.getLogger(__name__)


def _result_size(result: Any) -> int | None:
    if result is None:
        return None
    try:
        return len(json.dumps(result, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return None


def record_cache_hit(
    *,
    user_id: int,
    player_id: int,
    player_name: str | None,
    season: int,
    job_id: str,
    result: Any,
) -> None:
    """Insert a fully-populated `complete` history row for a cached result."""
    try:
        with SessionLocal() as db:
            row = AnalysisHistory(
                user_id=user_id,
                player_id=player_id,
                player_name=player_name,
                season=season,
                status="complete",
                cache_hit=True,
                job_id=job_id,
                created_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                duration_ms=0,
                response_size_bytes=_result_size(result),
            )
            db.add(row)
            db.commit()
    except Exception as e:
        # History is not on the critical path — never let logging fail the request.
        log.warning("failed to record cache-hit history: %s", e)


def start_history_row(
    *,
    user_id: int,
    player_id: int,
    player_name: str | None,
    season: int,
) -> int | None:
    """Insert a `running` row and return its id for later patching."""
    try:
        with SessionLocal() as db:
            row = AnalysisHistory(
                user_id=user_id,
                player_id=player_id,
                player_name=player_name,
                season=season,
                status="running",
                cache_hit=False,
                created_at=datetime.utcnow(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id
    except Exception as e:
        log.warning("failed to start history row: %s", e)
        return None


def attach_job_id(history_id: int | None, job_id: str) -> None:
    if history_id is None:
        return
    try:
        with SessionLocal() as db:
            row = db.get(AnalysisHistory, history_id)
            if row is None:
                return
            row.job_id = job_id
            db.commit()
    except Exception as e:
        log.warning("failed to attach job_id %s to history %s: %s", job_id, history_id, e)


def _finish(history_id: int, *, status: str, result: Any, error: str | None, started_at: float) -> None:
    duration_ms = int((time.monotonic() - started_at) * 1000)
    try:
        with SessionLocal() as db:
            row = db.get(AnalysisHistory, history_id)
            if row is None:
                return
            row.status = status
            row.completed_at = datetime.utcnow()
            row.duration_ms = duration_ms
            row.response_size_bytes = _result_size(result)
            row.error = (error or "")[:2000] if error else None
            db.commit()
    except Exception as e:
        log.warning("failed to finalize history row %s: %s", history_id, e)


def wrap_job_for_history(history_id: int | None, fn: Callable[[], Any]) -> Callable[[], Any]:
    """Wrap a job function so the history row tracks its outcome."""
    if history_id is None:
        return fn

    def wrapped() -> Any:
        started_at = time.monotonic()
        try:
            result = fn()
        except Exception as e:
            _finish(history_id, status="failed", result=None,
                    error=f"{type(e).__name__}: {e}", started_at=started_at)
            raise
        _finish(history_id, status="complete", result=result, error=None, started_at=started_at)
        return result

    return wrapped


__all__ = [
    "record_cache_hit",
    "start_history_row",
    "attach_job_id",
    "wrap_job_for_history",
]
