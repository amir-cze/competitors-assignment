"""In-process implementations of the three external boundaries."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from pydantic import BaseModel

from radar.assess.llm import Usage
from radar.ingest.http import FetchResult


@dataclass
class FakeLLM:
    """Scripted model. `responses` is consulted per schema class; falls back to a builder."""

    model: str = "fake-model"
    embedding_model: str = "fake-embedding"
    scripted: dict[type, BaseModel | list[BaseModel]] = field(default_factory=dict)
    calls: list[dict] = field(default_factory=list)
    embed_vector: list[float] = field(default_factory=lambda: [0.01] * 1536)

    def complete_structured[T: BaseModel](self, schema: type[T], *, system: str, user: str, temperature: float = 0.2) -> tuple[T, Usage]:
        self.calls.append({"schema": schema.__name__, "system": system, "user": user})
        scripted = self.scripted.get(schema)
        if scripted is None:
            raise AssertionError(f"FakeLLM has no scripted response for {schema.__name__}")
        response = scripted.pop(0) if isinstance(scripted, list) else scripted
        return response, Usage(self.model, prompt_tokens=1000, completion_tokens=200)

    def embed(self, texts: list[str]) -> tuple[list[list[float]], Usage]:
        vectors: list[list[float]] = []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            vectors.append([((digest[i % 32] / 255.0) - 0.5) for i in range(1536)])
        return vectors, Usage(self.embedding_model, prompt_tokens=100)

    def ping(self) -> tuple[bool, str]:
        return True, "fake"


@dataclass
class FixtureFetcher:
    """Serves canned responses by URL. Unknown URLs are 404."""

    pages: dict[str, str | FetchResult] = field(default_factory=dict)
    requests: list[str] = field(default_factory=list)

    def fetch(self, url: str, *, etag=None, last_modified=None, timeout=None, polite=True) -> FetchResult:
        self.requests.append(url)
        page = self.pages.get(url) or self.pages.get(url.rstrip("/"))
        if page is None:
            return FetchResult(url=url, final_url=url, status=404, body=None)
        if isinstance(page, FetchResult):
            return page
        return FetchResult(url=url, final_url=url, status=200, body=page, headers={"content-type": "text/html"})

    def fetch_rendered(self, url: str) -> FetchResult:
        return self.fetch(url)


@dataclass
class RecordingNotifier:
    sent: list[tuple[str, dict]] = field(default_factory=list)
    fail_with: Exception | None = None

    def post(self, destination: str, payload: dict) -> None:
        if self.fail_with:
            raise self.fail_with
        self.sent.append((destination, payload))
