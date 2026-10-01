"""Provider-quota circuit breaker: a 429 insufficient_quota must park work, not be retried per item."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import BaseModel

from radar.assess.llm import LLM, BudgetExceeded, Usage, is_quota_error


class Out(BaseModel):
    ok: bool


class _Err(Exception):
    def __init__(self, message: str, code: str | None = None, body: dict | None = None):
        super().__init__(message)
        self.code = code
        self.body = body


class FailingClient:
    model = "gpt-test"
    embedding_model = "text-embedding-test"

    def __init__(self, exc: Exception):
        self.exc = exc
        self.calls = 0

    def complete_structured(self, schema, *, system, user, temperature=0.2):
        self.calls += 1
        raise self.exc

    def embed(self, texts):
        self.calls += 1
        raise self.exc

    def ping(self):
        return True, "ok"


class HealthyClient(FailingClient):
    def __init__(self):
        super().__init__(RuntimeError("unused"))

    def complete_structured(self, schema, *, system, user, temperature=0.2):
        self.calls += 1
        return schema(ok=True), Usage(self.model, 100, 10)


@pytest.mark.parametrize(
    "exc",
    [
        _Err("Error code: 429", code="insufficient_quota"),
        _Err("429", body={"error": {"code": "credit_balance_exhausted"}}),
        _Err("You exceeded your current quota, please check your plan and billing details."),
    ],
)
def test_quota_errors_are_recognised(exc):
    assert is_quota_error(exc)


@pytest.mark.parametrize(
    "exc",
    [
        _Err("Rate limit reached for requests", code="rate_limit_exceeded"),
        TimeoutError("read timed out"),
        _Err("500 internal server error"),
    ],
)
def test_transient_errors_are_not_quota(exc):
    assert not is_quota_error(exc)


def test_quota_error_trips_breaker_and_fails_fast(db, settings):
    client = FailingClient(_Err("Error code: 429", code="insufficient_quota"))
    llm = LLM(client, settings)

    with pytest.raises(BudgetExceeded):
        llm.complete_structured(Out, system="s", user="u", purpose="test", session=db)
    assert client.calls == 1
    assert llm.provider_blocked_until is not None
    assert llm.provider_blocked_until > datetime.now(UTC) + timedelta(minutes=10)

    # Subsequent calls (any kind) fail without touching the provider.
    with pytest.raises(BudgetExceeded, match="retrying after"):
        llm.embed(["x"], purpose="test", session=db)
    with pytest.raises(BudgetExceeded):
        llm.complete_structured(Out, system="s", user="u", purpose="test", session=db)
    assert client.calls == 1

    summary = llm.usage_summary(db)
    assert summary["provider_blocked_until"] is not None
    assert "insufficient_quota" in summary["provider_block_reason"]


def test_breaker_auto_clears_after_cooldown(db, settings):
    client = FailingClient(_Err("429", code="insufficient_quota"))
    llm = LLM(client, settings)
    with pytest.raises(BudgetExceeded):
        llm.embed(["x"], purpose="test", session=db)

    llm._provider_blocked_until = datetime.now(UTC) - timedelta(seconds=1)
    assert llm.provider_blocked_until is None
    # Half-open: the provider is tried once more; it still has no quota, so the breaker re-trips.
    with pytest.raises(BudgetExceeded):
        llm.embed(["x"], purpose="test", session=db)
    assert client.calls == 2
    assert llm.provider_blocked_until is not None


def test_transient_error_does_not_trip_breaker(db, settings):
    client = FailingClient(_Err("Rate limit reached", code="rate_limit_exceeded"))
    llm = LLM(client, settings)
    with pytest.raises(_Err):
        llm.complete_structured(Out, system="s", user="u", purpose="test", session=db)
    assert llm.provider_blocked_until is None


def test_healthy_call_records_cost(db, settings):
    client = HealthyClient()
    llm = LLM(client, settings)
    parsed, cost = llm.complete_structured(Out, system="s", user="u", purpose="test", session=db)
    assert parsed.ok
    assert cost > 0
    assert llm.spent_today(db) == pytest.approx(cost)
    assert llm.provider_blocked_until is None
