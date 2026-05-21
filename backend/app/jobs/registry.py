"""In-memory job registry with thread-pool execution.

Used by the analysis endpoint so cold-cache requests don't block the HTTP
worker. Jobs are deduplicated by `key` — concurrent requests for the same
(player, season) share the same job, and completed results stick around
for `result_ttl` so a poll right after completion still works.

Limits & known trade-offs:
- In-memory only. A worker restart loses state. For Phase 5 / production with
  multiple replicas, swap this for Postgres or Redis. For now the API is
  single-instance, so this is fine.
- ThreadPool, not asyncio. The analysis path uses pandas/sklearn which release
  the GIL on the heavy numpy work, so threads work well here.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Literal


log = logging.getLogger(__name__)


JobStatus = Literal["pending", "running", "complete", "failed"]


@dataclass
class Job:
    id: str
    key: str
    kind: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    progress: float = 0.0      # 0..1, updated by the worker if useful
    meta: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "kind": self.kind,
            "status": self.status,
            "created_at": self.created_at.isoformat() + "Z",
            "started_at": self.started_at.isoformat() + "Z" if self.started_at else None,
            "completed_at": self.completed_at.isoformat() + "Z" if self.completed_at else None,
            "progress": self.progress,
            "error": self.error,
            "result": self.result,
            "meta": self.meta,
        }


class JobRegistry:
    def __init__(self, *, max_workers: int = 4, result_ttl_seconds: int = 1800):
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="ds-job")
        self._jobs: dict[str, Job] = {}            # job_id -> Job
        self._by_key: dict[str, str] = {}          # key -> job_id (only for active/recent)
        self._futures: dict[str, Future] = {}
        self._lock = threading.RLock()
        self._result_ttl = timedelta(seconds=result_ttl_seconds)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit(self, *, key: str, kind: str, fn: Callable[[], Any], meta: dict | None = None) -> Job:
        """Submit a job. If a job with the same `key` is in-flight or recently
        completed, return THAT job instead of starting a new one.
        """
        with self._lock:
            self._gc_expired_locked()
            existing_id = self._by_key.get(key)
            if existing_id and existing_id in self._jobs:
                return self._jobs[existing_id]

            job_id = str(uuid.uuid4())
            job = Job(
                id=job_id,
                key=key,
                kind=kind,
                status="pending",
                created_at=datetime.utcnow(),
                meta=meta or {},
            )
            self._jobs[job_id] = job
            self._by_key[key] = job_id

        future = self._pool.submit(self._run, job_id, fn)
        with self._lock:
            self._futures[job_id] = future
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def get_by_key(self, key: str) -> Job | None:
        with self._lock:
            jid = self._by_key.get(key)
            return self._jobs.get(jid) if jid else None

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {"pending": 0, "running": 0, "complete": 0, "failed": 0}
            for j in self._jobs.values():
                counts[j.status] = counts.get(j.status, 0) + 1
            return counts

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run(self, job_id: str, fn: Callable[[], Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.started_at = datetime.utcnow()

        try:
            result = fn()
            with self._lock:
                job = self._jobs[job_id]
                job.status = "complete"
                job.completed_at = datetime.utcnow()
                job.result = result
                job.progress = 1.0
        except Exception as e:
            log.exception("job %s (%s) failed", job_id, job.kind)
            with self._lock:
                job = self._jobs[job_id]
                job.status = "failed"
                job.completed_at = datetime.utcnow()
                job.error = f"{type(e).__name__}: {e}"

    def _gc_expired_locked(self) -> None:
        """Drop completed/failed jobs older than the TTL. Caller holds the lock."""
        now = datetime.utcnow()
        dead: list[str] = []
        for jid, job in self._jobs.items():
            if job.status in ("complete", "failed") and job.completed_at is not None:
                if now - job.completed_at > self._result_ttl:
                    dead.append(jid)
        for jid in dead:
            job = self._jobs.pop(jid, None)
            self._futures.pop(jid, None)
            if job and self._by_key.get(job.key) == jid:
                self._by_key.pop(job.key, None)


_registry: JobRegistry | None = None


def get_registry() -> JobRegistry:
    global _registry
    if _registry is None:
        _registry = JobRegistry()
    return _registry


def reset_registry_for_tests() -> None:
    """Test hook: replace the singleton with a fresh one."""
    global _registry
    if _registry is not None:
        _registry.shutdown()
    _registry = JobRegistry()
