from fastapi import APIRouter

from app.api import auth, players, jobs, analyses, history


api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(players.router)
api_router.include_router(jobs.router)
api_router.include_router(analyses.router)
api_router.include_router(history.router)
