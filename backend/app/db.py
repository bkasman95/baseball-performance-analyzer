from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import get_settings


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    # Imported for side effects so SQLAlchemy sees the models before create_all.
    from app.models import user, cache_entry  # noqa: F401

    Base.metadata.create_all(bind=engine)
