from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import api_router
from app.config import get_settings
from app.db import init_db


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("diamondscope")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting DiamondScope API")
    try:
        init_db()
        log.info("DB schema ready")
    except Exception as e:
        log.exception("DB init failed: %s", e)

    try:
        from app.auth.bootstrap import seed_admin_if_empty
        seed_admin_if_empty()
    except Exception as e:
        log.exception("admin seed failed: %s", e)

    try:
        from app.jobs.scheduler import start_scheduler
        start_scheduler()
    except Exception as e:
        log.exception("scheduler start failed: %s", e)

    yield

    try:
        from app.jobs.scheduler import stop_scheduler
        stop_scheduler()
    except Exception:
        pass
    log.info("Shutting down DiamondScope API")


settings = get_settings()
app = FastAPI(title="DiamondScope API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/api/health")
def health():
    """Liveness/readiness probe. Reports DB connectivity. Open (no auth)."""
    from sqlalchemy import text
    from app.db import engine

    db_ok = True
    db_error = None
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_ok = False
        db_error = str(e)

    return {
        "status": "ok" if db_ok else "degraded",
        "db": {"ok": db_ok, "error": db_error},
        "version": app.version,
    }


@app.get("/")
def root():
    return {"name": "DiamondScope API", "docs": "/docs", "health": "/api/health"}
