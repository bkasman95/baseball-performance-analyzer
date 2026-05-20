"""Centralized pybaseball configuration.

Enables pybaseball's own cache (separate from our Parquet layer; pybaseball
caches raw HTTP responses, we cache the cleaned DataFrames). Import this
module before any pybaseball call.
"""

import logging
import os
from pathlib import Path

from app.config import get_settings


log = logging.getLogger(__name__)
_initialized = False


def setup_pybaseball() -> None:
    global _initialized
    if _initialized:
        return

    try:
        import pybaseball

        cache_dir = Path(get_settings().cache_dir) / "pybaseball"
        cache_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("PYBASEBALL_CACHE", str(cache_dir))
        pybaseball.cache.enable()
        log.info("pybaseball cache enabled at %s", cache_dir)
    except Exception as e:
        log.warning("pybaseball setup partial: %s", e)

    _initialized = True
