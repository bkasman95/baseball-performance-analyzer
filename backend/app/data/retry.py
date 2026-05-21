"""Shared retry/backoff decorator for Savant/pybaseball network calls.

Treats HTTP 429 / 5xx and generic network errors as transient (worth
retrying). HTTP 401 / 403 / 404 are PermanentFetchError — those signal a
block or missing resource, not a flaky network, so retrying just wastes
time and the upstream's patience.
"""

import logging
import re
from typing import Callable, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)


log = logging.getLogger(__name__)
T = TypeVar("T")


class TransientFetchError(RuntimeError):
    """Wraps recoverable errors so tenacity can retry them."""


class PermanentFetchError(RuntimeError):
    """Upstream said no (403/401/404) — don't retry, fail fast."""


_STATUS_RE = re.compile(r"status code (\d{3})")


def classify_pybaseball_error(exc: Exception) -> Exception:
    """Translate a raw pybaseball exception into a Transient or Permanent
    FetchError. pybaseball doesn't expose the status code as an attribute
    on its exceptions, but the message includes 'status code XXX' for HTTP
    errors, which we parse out.
    """
    msg = str(exc)
    m = _STATUS_RE.search(msg)
    if m:
        code = int(m.group(1))
        if code in (401, 403, 404):
            return PermanentFetchError(f"upstream blocked ({code}): {msg}")
        if code == 429 or 500 <= code < 600:
            return TransientFetchError(f"upstream {code}: {msg}")
    # Network-level or unknown — treat as transient (worth a couple retries).
    return TransientFetchError(msg)


def with_retry(fn: Callable[..., T]) -> Callable[..., T]:
    return retry(
        retry=retry_if_exception_type((TransientFetchError, ConnectionError, TimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )(fn)
