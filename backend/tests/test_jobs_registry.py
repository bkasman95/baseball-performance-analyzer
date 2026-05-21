import time

from app.jobs.registry import JobRegistry


def test_submit_runs_and_completes():
    reg = JobRegistry(max_workers=2)
    try:
        job = reg.submit(key="t:1", kind="test", fn=lambda: {"x": 42})
        assert job.status in ("pending", "running", "complete")
        deadline = time.time() + 2.0
        while time.time() < deadline:
            j = reg.get(job.id)
            if j and j.status == "complete":
                break
            time.sleep(0.01)
        final = reg.get(job.id)
        assert final.status == "complete"
        assert final.result == {"x": 42}
    finally:
        reg.shutdown()


def test_submit_deduplicates_by_key():
    reg = JobRegistry(max_workers=2)
    try:
        ran = {"n": 0}

        def slow():
            ran["n"] += 1
            time.sleep(0.05)
            return ran["n"]

        a = reg.submit(key="dup", kind="t", fn=slow)
        b = reg.submit(key="dup", kind="t", fn=slow)
        assert a.id == b.id

        deadline = time.time() + 2.0
        while time.time() < deadline:
            j = reg.get(a.id)
            if j and j.status == "complete":
                break
            time.sleep(0.01)

        assert ran["n"] == 1
    finally:
        reg.shutdown()


def test_failed_jobs_carry_error():
    reg = JobRegistry(max_workers=1)
    try:
        def boom():
            raise ValueError("nope")

        job = reg.submit(key="boom", kind="t", fn=boom)
        deadline = time.time() + 2.0
        while time.time() < deadline:
            j = reg.get(job.id)
            if j and j.status in ("complete", "failed"):
                break
            time.sleep(0.01)
        final = reg.get(job.id)
        assert final.status == "failed"
        assert "ValueError" in (final.error or "")
    finally:
        reg.shutdown()
