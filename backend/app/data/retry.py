"""Shared retry/backoff decorator for Savant/pybaseball network calls.

Treats HTTP 429 / 403 / 5xx and generic network errors as retryable. Uses
exponential backoff capped at ~60s. Wraps any callable.
"""

import logging
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


def with_retry(fn: Callable[..., T]) -> Callable[..., T]:
    return retry(
        retry=retry_if_exception_type((TransientFetchError, ConnectionError, TimeoutError)),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        stop=stop_after_attempt(5),
        before_sleep=before_sleep_log(log, logging.WARNING),
        reraise=True,
    )(fn)
