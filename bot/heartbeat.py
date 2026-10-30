"""Optional "dead man's switch" pings (e.g. healthchecks.io).

The bot's own alerts cannot fire if the bot or its server is down. With
HEARTBEAT_URL set, the bot pings that URL after every healthy cycle (at most once
a minute) and pings `<url>/fail` when a cycle crashes. The monitoring service
alerts you when the pings stop arriving or a failure is reported.
"""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


class Heartbeat:
    def __init__(self, url: str, min_interval_sec: float = 60.0) -> None:
        self.url = (url or "").strip().rstrip("/")
        self.min_interval_sec = min_interval_sec
        self._last_ok = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    def ok(self) -> None:
        if not self.enabled or time.monotonic() - self._last_ok < self.min_interval_sec:
            return
        if self._send(self.url):
            self._last_ok = time.monotonic()

    def fail(self, reason: str = "") -> None:
        if self.enabled:
            self._send(f"{self.url}/fail", reason[:1000])

    def _send(self, url: str, body: str = "") -> bool:
        try:
            requests.post(url, data=body.encode("utf-8"), timeout=5)
            return True
        except requests.RequestException as exc:
            logger.debug("Heartbeat ping failed: %s", exc)
            return False
