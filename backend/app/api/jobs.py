from fastapi import APIRouter, HTTPException

from app.api.schemas import JobView
from app.jobs.registry import get_registry


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobView)
def get_job(job_id: str) -> JobView:
    job = get_registry().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job not found: {job_id}")
    return JobView(**job.to_dict())
