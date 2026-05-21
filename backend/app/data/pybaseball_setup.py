"""Centralized pybaseball configuration.

Enables pybaseball's own cache (separate from our Parquet layer; pybaseball
caches raw HTTP responses, we cache the cleaned DataFrames). Import this
module before any pybaseball call.

Also installs a realistic browser User-Agent on every outbound `requests`
call. FanGraphs in particular tends to 403 the default python-requests UA
when it comes from cloud provider IP ranges.
"""

import logging
import os
from pathlib import Path

from app.config import get_settings


log = logging.getLogger(__name__)
_initialized = False


_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
}

_ua_installed = False


def _install_browser_headers() -> None:
    """Monkey-patch requests so every outgoing call carries browser-like
    headers. pybaseball doesn't expose a session hook, so the cleanest way
    to set headers globally is to wrap requests.Session.request itself.
    """
    global _ua_installed
    if _ua_installed:
        return

    try:
        import requests

        original = requests.Session.request

        def patched(self, method, url, **kwargs):  # type: ignore[no-untyped-def]
            headers = kwargs.get("headers") or {}
            # Don't overwrite explicit caller headers — only fill missing ones.
            for k, v in _BROWSER_HEADERS.items():
                headers.setdefault(k, v)
            kwargs["headers"] = headers
            return original(self, method, url, **kwargs)

        requests.Session.request = patched  # type: ignore[assignment]
        _ua_installed = True
        log.info("installed browser headers on requests.Session")
    except Exception as e:
        log.warning("could not install browser headers: %s", e)


def setup_pybaseball() -> None:
    global _initialized
    if _initialized:
        return

    _install_browser_headers()

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
