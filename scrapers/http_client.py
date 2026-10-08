"""Reusable, polite HTTP layer: one Session, timeouts, retries and rate limiting."""

from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import RETRY_STATUS_CODES

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """Raised when a URL could not be fetched after all retries."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{url}: {reason}")
        self.url = url
        self.reason = reason


class HttpClient:
    """Thin wrapper around ``requests.Session``.

    * Retries connection errors, read timeouts and HTTP 429/500/502/503/504 with
      exponential backoff (and honours ``Retry-After``).
    * Waits at least ``delay`` seconds between consecutive requests.
    * Turns every final failure into a :class:`FetchError` so callers handle a
      single exception type.
    """

    def __init__(
        self,
        user_agent: str,
        timeout: float = 10.0,
        delay: float = 0.5,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self._last_request_at: float | None = None
        self.requests_made = 0
        self.failed_requests = 0

        retry = Retry(
            total=max_retries,
            connect=max_retries,
            read=max_retries,
            status=max_retries,
            backoff_factor=backoff_factor,
            status_forcelist=RETRY_STATUS_CODES,
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,  # we call raise_for_status() ourselves
        )
        adapter = HTTPAdapter(max_retries=retry)

        self.session = requests.Session()
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en",
            }
        )

    def _throttle(self) -> None:
        # perf_counter is high-resolution (monotonic() ticks every ~15 ms on
        # Windows), and the loop guards against sleep() waking up early.
        if self._last_request_at is not None:
            while (wait := self.delay - (time.perf_counter() - self._last_request_at)) > 0:
                time.sleep(wait)
        self._last_request_at = time.perf_counter()

    def get(self, url: str) -> requests.Response:
        """GET ``url`` or raise :class:`FetchError`."""
        self._throttle()
        self.requests_made += 1
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            reason = f"timeout after retries ({exc.__class__.__name__})"
        except requests.exceptions.ConnectionError as exc:
            reason = f"connection error after retries ({exc.__class__.__name__})"
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            reason = f"HTTP {status}"
        except requests.exceptions.RequestException as exc:
            reason = f"request failed ({exc.__class__.__name__}: {exc})"
        else:
            return response

        self.failed_requests += 1
        logger.error("Request failed for %s: %s", url, reason)
        raise FetchError(url, reason)

    def close(self) -> None:
        self.session.close()
