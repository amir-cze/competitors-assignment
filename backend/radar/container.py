"""Composition root. The only place that decides which implementation of each boundary is used.

    deps = build_deps()                      # production: real OpenAI, real HTTP, real Slack
    deps = build_deps(llm_client=FakeLLM(),  # tests: everything in-process
                      fetcher=FixtureFetcher(), notifier=RecordingNotifier())

FastAPI gets the process-wide instance through `get_deps`; the worker builds its own at startup.
"""

from __future__ import annotations

from dataclasses import dataclass

from radar.assess.llm import LLM, LLMClient, OpenAIClient
from radar.assess.scoring import Scorer
from radar.config import Settings, get_settings
from radar.deliver.digest import DigestSender
from radar.deliver.notifier import Notifier, SlackWebhookNotifier
from radar.deliver.slack import SlackDeliverer
from radar.eval.metrics import Evaluator
from radar.ingest.adapters import AdapterRegistry
from radar.ingest.http import Fetcher, HttpFetcher
from radar.pipeline import Pipeline


@dataclass(frozen=True)
class Deps:
    settings: Settings
    llm: LLM
    fetcher: Fetcher
    notifier: Notifier
    adapters: AdapterRegistry
    scorer: Scorer
    deliverer: SlackDeliverer
    digests: DigestSender
    evaluator: Evaluator
    pipeline: Pipeline


def build_deps(
    settings: Settings | None = None,
    *,
    llm_client: LLMClient | None | object = ...,
    fetcher: Fetcher | None = None,
    notifier: Notifier | None = None,
) -> Deps:
    settings = settings or get_settings()
    if llm_client is ...:
        llm_client = (
            OpenAIClient(settings.openai_api_key, settings.openai_model, settings.openai_embedding_model)
            if settings.openai_api_key
            else None
        )
    llm = LLM(llm_client, settings)  # type: ignore[arg-type]
    fetcher = fetcher or HttpFetcher()
    notifier = notifier or SlackWebhookNotifier()
    adapters = AdapterRegistry(llm)
    scorer = Scorer(llm)
    deliverer = SlackDeliverer(notifier, settings)
    pipeline = Pipeline(
        settings=settings, fetcher=fetcher, adapters=adapters, scorer=scorer, deliverer=deliverer
    )
    return Deps(
        settings=settings,
        llm=llm,
        fetcher=fetcher,
        notifier=notifier,
        adapters=adapters,
        scorer=scorer,
        deliverer=deliverer,
        digests=DigestSender(deliverer, settings),
        evaluator=Evaluator(scorer, settings.eval_max_items),
        pipeline=pipeline,
    )


_deps: Deps | None = None


def get_deps() -> Deps:
    """FastAPI dependency. Built lazily once per process."""
    global _deps
    if _deps is None:
        _deps = build_deps()
    return _deps


def set_deps(deps: Deps | None) -> None:
    """Test hook: override the process-wide instance."""
    global _deps
    _deps = deps
