"""LLM boundary.

- `LLMClient` is the protocol for a model provider. `OpenAIClient` is the real one; tests use a fake.
- `LLM` is what the application code talks to. It adds what a provider does not know about: the daily
  budget, cost accounting into `llm_usage`, and a "not configured" mode that degrades gracefully.

Nothing outside this module imports the OpenAI SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from radar.config import Settings
from radar.logging import get_logger
from radar.models import LLMUsage

log = get_logger(__name__)


class BudgetExceeded(RuntimeError):
    """Raised when our daily budget is spent *or* the provider says the account has no quota.

    Both mean the same thing to callers: stop spending, park the work, tell an operator once."""


class LLMUnavailable(RuntimeError):
    pass


QUOTA_MARKERS = ("insufficient_quota", "credit_balance_exhausted", "no credits remaining", "billing")
PROVIDER_QUOTA_COOLDOWN = timedelta(minutes=15)


def is_quota_error(exc: BaseException) -> bool:
    """Provider-side 'you cannot spend' signals, as opposed to transient rate limits."""
    code = getattr(exc, "code", None) or ""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        code = code or err.get("code") or err.get("type") or ""
    text = f"{code} {exc}".lower()
    return any(marker in text for marker in QUOTA_MARKERS)


@dataclass(frozen=True)
class Usage:
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMClient(Protocol):
    """A model provider. Stateless, knows nothing about budgets or databases."""

    model: str
    embedding_model: str

    def complete_structured[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, temperature: float = 0.2
    ) -> tuple[T, Usage]: ...

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]: ...

    def ping(self) -> tuple[bool, str]: ...


class OpenAIClient:
    def __init__(self, api_key: str, model: str, embedding_model: str):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model
        self.embedding_model = embedding_model

    def complete_structured[T: BaseModel](
        self, schema: type[T], *, system: str, user: str, temperature: float = 0.2
    ) -> tuple[T, Usage]:
        completions = self._client.chat.completions
        parse = getattr(completions, "parse", None) or self._client.beta.chat.completions.parse
        response = parse(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            temperature=temperature,
        )
        choice = response.choices[0]
        if choice.message.parsed is None:
            raise RuntimeError(
                f"Model refused or returned no structured output: {choice.message.refusal or 'unknown'}"
            )
        u = response.usage
        return choice.message.parsed, Usage(
            self.model, u.prompt_tokens if u else 0, u.completion_tokens if u else 0
        )

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        cleaned = [t[:8000] if t else " " for t in texts]
        response = self._client.embeddings.create(model=self.embedding_model, input=cleaned)
        u = response.usage
        return [d.embedding for d in response.data], Usage(
            self.embedding_model, u.prompt_tokens if u else 0, 0
        )

    def ping(self) -> tuple[bool, str]:
        try:
            self._client.models.retrieve(self.model)
            return True, "OpenAI reachable"
        except Exception as exc:
            return False, f"OpenAI error: {exc}"[:300]


class LLM:
    """Budgeted, metered access to a model. `client=None` means "not configured": every call raises
    LLMUnavailable and `configured` is False, so callers can park work instead of failing."""

    def __init__(self, client: LLMClient | None, settings: Settings):
        self._client = client
        self._settings = settings
        self._provider_blocked_until: datetime | None = None
        self._provider_block_reason: str | None = None

    @property
    def configured(self) -> bool:
        return self._client is not None

    # --- provider circuit breaker -------------------------------------------

    @property
    def provider_blocked_until(self) -> datetime | None:
        if self._provider_blocked_until and self._provider_blocked_until <= datetime.now(UTC):
            self._provider_blocked_until = None
            self._provider_block_reason = None
        return self._provider_blocked_until

    def _ensure_provider(self) -> None:
        until = self.provider_blocked_until
        if until:
            raise BudgetExceeded(
                f"{self._provider_block_reason}; retrying after {until.strftime('%H:%M')} UTC"
            )

    def _trip_provider(self, exc: BaseException) -> BudgetExceeded:
        """Open the breaker so the next N minutes of calls fail fast instead of hammering a 429."""
        self._provider_blocked_until = datetime.now(UTC) + PROVIDER_QUOTA_COOLDOWN
        self._provider_block_reason = "OpenAI account has no credits remaining (insufficient_quota)"
        log.warning("llm.provider_quota_exhausted", error=str(exc)[:200], cooldown_minutes=15)
        return BudgetExceeded(self._provider_block_reason)

    @property
    def model(self) -> str:
        return self._client.model if self._client else self._settings.openai_model

    # --- budget -------------------------------------------------------------

    @staticmethod
    def _today_start() -> datetime:
        return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)

    def spent_today(self, session: Session) -> float:
        total = session.scalar(
            select(func.coalesce(func.sum(LLMUsage.cost_usd), 0.0)).where(
                LLMUsage.created_at >= self._today_start()
            )
        )
        return float(total or 0.0)

    def budget_remaining(self, session: Session) -> float:
        return self._settings.llm_daily_budget_usd - self.spent_today(session)

    def ensure_budget(self, session: Session) -> None:
        if self.budget_remaining(session) <= 0:
            raise BudgetExceeded(f"Daily LLM budget of ${self._settings.llm_daily_budget_usd:.2f} exhausted")

    def _cost(self, usage: Usage) -> float:
        s = self._settings
        if "embedding" in usage.model:
            return usage.prompt_tokens / 1_000_000 * s.embedding_cost_per_1m
        return (
            usage.prompt_tokens / 1_000_000 * s.llm_input_cost_per_1m
            + usage.completion_tokens / 1_000_000 * s.llm_output_cost_per_1m
        )

    def _record(self, session: Session, usage: Usage, purpose: str) -> float:
        cost = self._cost(usage)
        session.add(
            LLMUsage(
                model=usage.model,
                purpose=purpose,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=cost,
            )
        )
        session.flush()
        return cost

    # --- calls --------------------------------------------------------------

    def _require(self) -> LLMClient:
        if self._client is None:
            raise LLMUnavailable("OPENAI_API_KEY is not set")
        return self._client

    def complete_structured[T: BaseModel](
        self,
        schema: type[T],
        *,
        system: str,
        user: str,
        purpose: str,
        session: Session,
        temperature: float = 0.2,
    ) -> tuple[T, float]:
        client = self._require()
        self._ensure_provider()
        self.ensure_budget(session)
        try:
            parsed, usage = client.complete_structured(
                schema, system=system, user=user, temperature=temperature
            )
        except Exception as exc:
            if is_quota_error(exc):
                raise self._trip_provider(exc) from exc
            raise
        return parsed, self._record(session, usage, purpose)

    def embed(self, texts: list[str], *, purpose: str, session: Session) -> tuple[list[list[float]], float]:
        if not texts:
            return [], 0.0
        client = self._require()
        self._ensure_provider()
        self.ensure_budget(session)
        try:
            vectors, usage = client.embed(texts)
        except Exception as exc:
            if is_quota_error(exc):
                raise self._trip_provider(exc) from exc
            raise
        return vectors, self._record(session, usage, purpose)

    def ping(self) -> tuple[bool, str]:
        if self._client is None:
            return False, "OPENAI_API_KEY is not set"
        return self._client.ping()

    # --- reporting ----------------------------------------------------------

    def usage_summary(self, session: Session, days: int = 7) -> dict:
        since = datetime.now(UTC) - timedelta(days=days)
        rows = session.execute(
            select(
                LLMUsage.purpose,
                func.count(),
                func.sum(LLMUsage.cost_usd),
                func.sum(LLMUsage.prompt_tokens),
                func.sum(LLMUsage.completion_tokens),
            )
            .where(LLMUsage.created_at >= since)
            .group_by(LLMUsage.purpose)
        ).all()
        return {
            "days": days,
            "by_purpose": [
                {
                    "purpose": p,
                    "calls": int(c),
                    "cost_usd": float(cost or 0),
                    "prompt_tokens": int(pt or 0),
                    "completion_tokens": int(ct or 0),
                }
                for p, c, cost, pt, ct in rows
            ],
            "total_usd": float(sum(float(r[2] or 0) for r in rows)),
            "today_usd": self.spent_today(session),
            "daily_budget_usd": self._settings.llm_daily_budget_usd,
            "provider_blocked_until": (
                self.provider_blocked_until.isoformat() if self.provider_blocked_until else None
            ),
            "provider_block_reason": self._provider_block_reason,
        }


# --------------------------------------------------------------------------- utility prompt: listing recipe


class ListRecipe(BaseModel):
    item_selector: str = Field(description="CSS selector matching one card/row per article in the listing")
    link_selector: str = Field(
        description="CSS selector, relative to the item, for the anchor that links to the article"
    )
    title_selector: str = Field(
        description="CSS selector, relative to the item, for the title text; empty string if the link text is the title"
    )
    date_selector: str = Field(
        description="CSS selector, relative to the item, for the published date; empty string if none"
    )
    confidence: float = Field(description="0-1 confidence that these selectors are stable")


RECIPE_SYSTEM = (
    "You are extracting a repeatable CSS recipe from an HTML listing page (blog index, newsroom, resources). "
    "Return selectors that match each article card and, inside it, the link, title and date. Prefer semantic, "
    "stable selectors (article, h2, time, class names that describe content) over positional ones. "
    "If the page is not a listing of articles, set confidence to 0."
)


def derive_list_recipe(llm: LLM, session: Session, html_sample: str, url: str) -> dict | None:
    """Ask the model for CSS selectors that turn a listing page into article links. Cached by the caller."""
    if not llm.configured:
        return None
    parsed, _ = llm.complete_structured(
        ListRecipe,
        system=RECIPE_SYSTEM,
        user=f"URL: {url}\n\nHTML sample (trimmed):\n{html_sample}",
        purpose="recipe",
        session=session,
        temperature=0,
    )
    if parsed.confidence < 0.3:
        return None
    recipe = {
        "item_selector": parsed.item_selector,
        "link_selector": parsed.link_selector or "a",
        "title_selector": parsed.title_selector or None,
        "date_selector": parsed.date_selector or None,
        "confidence": parsed.confidence,
    }
    log.info("html_list.recipe_derived", url=url, recipe=recipe)
    return recipe
