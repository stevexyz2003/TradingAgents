"""HTTP helpers of the archive: CA bundle from the environment, session, rate limit, retry."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

USER_AGENT = "TradingEngineX-archive/0.1 (+https://github.com/stevexyz2003/TradingAgents)"


class CaBundleMissing(Exception):
    """REQUESTS_CA_BUNDLE is set but points to no file."""


def resolve_ca_bundle(environ) -> str | bool:
    """The ``verify`` value for requests.

    A set REQUESTS_CA_BUNDLE must exist (a silent fallback would hide a broken TLS setup,
    see scripts/PAPER_RUN.md on AVG HTTPS interception); unset means the certifi default.
    """
    value = (environ.get("REQUESTS_CA_BUNDLE") or "").strip()
    if value:
        if Path(value).is_file():
            return value
        raise CaBundleMissing(f"REQUESTS_CA_BUNDLE points to a missing file: {value}")
    log.warning(
        "REQUESTS_CA_BUNDLE not set; using the certifi default "
        "(see scripts/PAPER_RUN.md if HTTPS is intercepted)"
    )
    return True


def make_session(verify) -> requests.Session:
    session = requests.Session()
    session.verify = verify
    session.headers["User-Agent"] = USER_AGENT
    return session


class RateLimiter:
    """Keeps at least ``min_interval`` seconds between calls of ``wait()``."""

    def __init__(self, min_interval: float, *, clock=time.monotonic, sleep=time.sleep):
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        now = self._clock()
        if self._last is not None:
            remaining = self.min_interval - (now - self._last)
            if remaining > 0:
                self._sleep(remaining)
                now += remaining
        self._last = now


class FetchError(Exception):
    """A request failed; ``kind`` is rate_limited | server | timeout | connection | client."""

    def __init__(self, kind: str, message: str, status_code: int | None = None):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.status_code = status_code


def get_with_retry(
    get,
    url,
    *,
    params=None,
    limiter=None,
    attempts: int = 3,
    backoff: float = 5.0,
    sleep=time.sleep,
    timeout=(10, 60),
):
    """GET with retries on 429/5xx/timeout/connection errors and exponential backoff.

    Any other 4xx fails at once with kind ``client``. The caller checks the content type.
    """
    last: FetchError | None = None
    for attempt in range(attempts):
        if limiter is not None:
            limiter.wait()
        try:
            response = get(url, params=params, timeout=timeout)
        except requests.Timeout as exc:
            last = FetchError("timeout", str(exc))
        except requests.RequestException as exc:
            last = FetchError("connection", f"{type(exc).__name__}: {exc}")
        else:
            code = response.status_code
            if code == 429:
                last = FetchError("rate_limited", f"HTTP 429 for {url}", code)
            elif code >= 500:
                last = FetchError("server", f"HTTP {code} for {url}", code)
            elif code >= 400:
                raise FetchError("client", f"HTTP {code} for {url}", code)
            else:
                return response
        if attempt < attempts - 1:
            sleep(backoff * 2**attempt)
    assert last is not None
    raise last
