"""Notification boundary. Slack today; the protocol is what the pipeline depends on."""

from __future__ import annotations

from typing import Protocol

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


class NotifyError(RuntimeError):
    """Transient failure (network, 429, 5xx). Worth retrying."""


class NotifyRejected(RuntimeError):
    """Permanent failure (bad webhook, invalid payload). Retrying will not help."""


class Notifier(Protocol):
    def post(self, destination: str, payload: dict) -> None:
        """Deliver `payload` to `destination` (a webhook URL). Raises NotifyError or NotifyRejected."""
        ...


class SlackWebhookNotifier:
    def __init__(self, timeout: float = 10.0):
        self._timeout = timeout

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(NotifyError),
    )
    def post(self, destination: str, payload: dict) -> None:
        try:
            resp = httpx.post(destination, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            raise NotifyError(str(exc)) from exc
        if resp.status_code == 429 or resp.status_code >= 500:
            raise NotifyError(f"Slack HTTP {resp.status_code}")
        if resp.status_code >= 400:
            raise NotifyRejected(f"Slack rejected the message: HTTP {resp.status_code} {resp.text[:200]}")


class RecordingNotifier:
    """Test double: records every post; can be told to fail."""

    def __init__(self, fail_with: Exception | None = None):
        self.sent: list[tuple[str, dict]] = []
        self.fail_with = fail_with

    def post(self, destination: str, payload: dict) -> None:
        if self.fail_with:
            raise self.fail_with
        self.sent.append((destination, payload))
