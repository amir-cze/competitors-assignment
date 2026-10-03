"""End-to-end pipeline with no network and no model: fixture HTML in, assessments and Slack posts out."""

from __future__ import annotations

from sqlalchemy import select

from radar.assess.scoring import ItemAssessmentOut, TeamScore
from radar.models import Assessment, Competitor, Delivery, Item, ItemSource, PageSnapshot, Source, utcnow
from radar.security import encrypt

LISTING = """
<html><body><main>
  <article><h2><a href="/blog/mcp-gateway-launch">We launched an MCP gateway with per-tool policies</a></h2><time datetime="2026-09-20">Sep 20, 2026</time></article>
  <article><h2><a href="/blog/webinar-invite">Join our webinar on AI security next Thursday</a></h2><time datetime="2026-09-18">Sep 18, 2026</time></article>
  <article><h2><a href="/blog/series-b">Acme raises $40M Series B to secure AI agents</a></h2><time datetime="2026-09-15">Sep 15, 2026</time></article>
</main></body></html>
"""


def article(title: str, body: str) -> str:
    filler = body * 12
    return f"<html><head><title>{title}</title></head><body><main><h1>{title}</h1><p>{filler}</p></main></body></html>"


def scripted(headline: str, category: str, scores: dict[str, int], substantive: bool = True) -> ItemAssessmentOut:
    return ItemAssessmentOut(
        headline=headline,
        summary="Two factual sentences.",
        category=category,
        is_substantive=substantive,
        teams=[TeamScore(team_key=k, relevance=v, why=f"why for {k}", evidence_quote="quote", topics_matched=["MCP"]) for k, v in scores.items()],
    )


def make_competitor(db, *, muted=False):
    comp = Competitor(name="Acme", homepage_url="https://acme.test", muted=muted)
    db.add(comp)
    db.flush()
    src = Source(competitor_id=comp.id, kind="html_list", url="https://acme.test/blog", label="Blog", interval_minutes=60, next_run_at=utcnow())
    db.add(src)
    db.flush()
    return comp, src


def test_listing_to_assessments_to_slack(db, deps, fake_llm, fetcher, notifier, teams):
    comp, src = make_competitor(db)
    teams[2].slack_enabled = True
    teams[2].slack_webhook_encrypted = encrypt("https://hooks.slack.com/services/T/B/rnd")
    db.flush()

    fetcher.pages["https://acme.test/blog"] = LISTING
    fetcher.pages["https://acme.test/blog/mcp-gateway-launch"] = article("MCP gateway launch", "Every tool call is checked against YAML policy. ")
    fetcher.pages["https://acme.test/blog/webinar-invite"] = article("Webinar", "Register now for our webinar. ")
    fetcher.pages["https://acme.test/blog/series-b"] = article("Series B", "We raised forty million dollars led by investors. ")
    fake_llm.scripted[ItemAssessmentOut] = [
        scripted("Acme ships MCP gateway", "product_launch", {"marketing": 55, "product": 82, "rnd": 90}),
        scripted("Acme webinar", "event_or_webinar", {"marketing": 20, "product": 10, "rnd": 5}, substantive=False),
        scripted("Acme raises $40M", "funding", {"marketing": 80, "product": 60, "rnd": 15}),
    ]

    run = deps.pipeline.process_source(db, src.id, trigger="manual")

    assert run.status == "ok"
    assert run.items_found == 3 and run.items_new == 3 and run.items_assessed == 3
    assert run.llm_cost_usd > 0

    items = db.scalars(select(Item).where(Item.competitor_id == comp.id).order_by(Item.title)).all()
    assert {i.status for i in items} == {"assessed"}
    gateway = next(i for i in items if "gateway" in i.canonical_url)
    routes = {a.team.key: a.route for a in gateway.assessments}
    assert routes == {"marketing": "digest", "product": "immediate", "rnd": "immediate"}

    # Only R&D has Slack configured: one real post, one skipped delivery row for Product.
    deliveries = db.scalars(select(Delivery).where(Delivery.item_id == gateway.id)).all()
    by_team = {d.team_id: d for d in deliveries}
    assert by_team[teams[2].id].status == "sent"
    assert by_team[teams[1].id].status == "skipped"
    assert len(notifier.sent) == 1  # only R&D has Slack; funding scores 15 for R&D so it stays off Slack
    src_health = db.get(Source, src.id)
    assert src_health.health == "healthy" and src_health.consecutive_failures == 0
    assert src_health.baseline_items_per_run == 3.0

    # The prompt the model saw contains the business's lenses and our own profile, not just the item.
    system = fake_llm.calls[0]["system"].lower()
    assert "positioning" in system and "technical" in system
    assert "about us" in system and "runtime protection" in system  # default profile until the business edits it


def test_company_profile_edit_reaches_the_prompt(db, deps, fake_llm, fetcher, teams):
    """The business, not an engineer, decides what "we sell" means; the next item is scored against it."""
    from radar.services import company

    assert company.is_default(db)
    company.set_profile(db, "Acme Corp: we sell a firewall for LLM prompts. We do not sell agent runtime security.")
    assert not company.is_default(db)

    comp, src = make_competitor(db)
    fetcher.pages["https://acme.test/blog"] = LISTING
    for slug in ("mcp-gateway-launch", "series-b", "webinar-invite"):
        fetcher.pages[f"https://acme.test/blog/{slug}"] = article(slug, f"Body for {slug}. ")
    fake_llm.scripted[ItemAssessmentOut] = [scripted("x", "other", {"marketing": 10, "product": 10, "rnd": 10})] * 3
    deps.pipeline.process_source(db, src.id)

    system = fake_llm.calls[0]["system"]
    assert "ABOUT US" in system and "firewall for LLM prompts" in system
    assert "Noma Security" not in system  # the hard-coded default is gone once the business writes its own


def test_rerun_is_idempotent(db, deps, fake_llm, fetcher, teams):
    comp, src = make_competitor(db)
    fetcher.pages["https://acme.test/blog"] = LISTING
    for slug in ("mcp-gateway-launch", "webinar-invite", "series-b"):
        fetcher.pages[f"https://acme.test/blog/{slug}"] = article(slug, f"Body for {slug}. ")
    fake_llm.scripted[ItemAssessmentOut] = [scripted("x", "other", {"marketing": 10, "product": 10, "rnd": 10})] * 3

    deps.pipeline.process_source(db, src.id)
    first_calls = len(fake_llm.calls)
    run2 = deps.pipeline.process_source(db, src.id)

    assert run2.items_new == 0
    assert len(fake_llm.calls) == first_calls  # nothing re-scored
    assert db.scalar(select(Item).where(Item.competitor_id == comp.id).with_only_columns(Item.id).limit(1)) is not None
    assert len(db.scalars(select(Item).where(Item.competitor_id == comp.id)).all()) == 3


def test_duplicate_alias_is_not_refetched_on_rerun(db, deps, fake_llm, fetcher, teams):
    """A URL linked to an existing item as a duplicate must be recognised by URL next time, so the
    hourly run does not download and embed the same page over and over."""
    comp, src = make_competitor(db)
    # State left by an earlier run: series-b exists, and webinar-invite was linked to it as a near-duplicate.
    existing = Item(
        competitor_id=comp.id,
        canonical_url="https://acme.test/blog/series-b",
        title="Series B",
        content_text="We raised forty million dollars.",
        content_hash="deadbeef",
        status="assessed",
    )
    db.add(existing)
    db.flush()
    db.add(ItemSource(item_id=existing.id, source_id=src.id, url="https://acme.test/blog/webinar-invite"))
    db.flush()

    fetcher.pages["https://acme.test/blog"] = LISTING
    fetcher.pages["https://acme.test/blog/mcp-gateway-launch"] = article("Gateway", "Policy checks on every call. ")
    fake_llm.scripted[ItemAssessmentOut] = [scripted("x", "other", {"marketing": 10, "product": 10, "rnd": 10})]

    run = deps.pipeline.process_source(db, src.id)

    assert run.items_found == 3 and run.items_new == 1  # only the gateway post is genuinely new
    assert "https://acme.test/blog/mcp-gateway-launch" in fetcher.requests
    assert "https://acme.test/blog/series-b" not in fetcher.requests  # known by canonical URL
    assert "https://acme.test/blog/webinar-invite" not in fetcher.requests  # known by alias URL
    assert len(db.scalars(select(Item).where(Item.competitor_id == comp.id)).all()) == 2


def test_failure_backs_off_and_recovers(db, deps, fetcher, teams):
    comp, src = make_competitor(db)
    # Unknown URL -> 404 from the fixture fetcher.
    for _ in range(3):
        run = deps.pipeline.process_source(db, src.id)
        assert run.status == "error"
    src = db.get(Source, src.id)
    assert src.health == "failing" and src.consecutive_failures == 3
    assert src.next_run_at > utcnow()

    fetcher.pages["https://acme.test/blog"] = "<html><body><main></main></body></html>"
    src.next_run_at = utcnow()
    run = deps.pipeline.process_source(db, src.id)
    assert run.status == "ok"
    assert db.get(Source, src.id).health == "healthy"


def test_no_llm_parks_items_instead_of_failing(db, unconfigured_deps, fetcher, teams):
    comp, src = make_competitor(db)
    fetcher.pages["https://acme.test/blog"] = LISTING
    for slug in ("mcp-gateway-launch", "webinar-invite", "series-b"):
        fetcher.pages[f"https://acme.test/blog/{slug}"] = article(slug, f"Body for {slug}. ")

    run = unconfigured_deps.pipeline.process_source(db, src.id)

    assert run.status == "ok" and run.items_new == 3 and run.items_assessed == 0
    statuses = {i.status for i in db.scalars(select(Item).where(Item.competitor_id == comp.id)).all()}
    assert statuses == {"budget_hold"}


def test_page_watch_detects_meaningful_change_only(db, deps, fake_llm, fetcher, teams):
    comp = Competitor(name="Acme", homepage_url="https://acme.test")
    db.add(comp)
    db.flush()
    src = Source(competitor_id=comp.id, kind="page_watch", url="https://acme.test", label="Homepage", interval_minutes=360, next_run_at=utcnow())
    db.add(src)
    db.flush()

    before = "<html><body><h1>Security for AI models</h1><p>Protect your models from adversarial attacks.</p><footer>© 2025 Acme</footer></body></html>"
    fetcher.pages["https://acme.test"] = before
    run = deps.pipeline.process_source(db, src.id)
    assert run.items_new == 0  # baseline
    assert db.scalar(select(PageSnapshot).where(PageSnapshot.source_id == src.id)) is not None

    # Cosmetic: only the copyright year changed.
    fetcher.pages["https://acme.test"] = before.replace("2025", "2026")
    run = deps.pipeline.process_source(db, src.id)
    assert run.items_new == 0

    # Substantive: repositioning.
    fetcher.pages["https://acme.test"] = "<html><body><h1>Total AI Security Platform</h1><p>Discover, protect and govern every agent, model and application in your enterprise.</p><footer>© 2026 Acme</footer></body></html>"
    fake_llm.scripted[ItemAssessmentOut] = scripted("Acme repositions as platform", "positioning_shift", {"marketing": 88, "product": 70, "rnd": 20})
    run = deps.pipeline.process_source(db, src.id)
    assert run.items_new == 1
    item = db.scalar(select(Item).where(Item.competitor_id == comp.id))
    assert item.kind == "page_change"
    assert any("Total AI Security" in line for line in item.page_diff["added"])
    marketing = next(a for a in item.assessments if a.team.key == "marketing")
    assert marketing.route == "immediate"


def test_muted_competitor_never_alerts(db, deps, fake_llm, fetcher, teams):
    comp, src = make_competitor(db, muted=True)
    fetcher.pages["https://acme.test/blog"] = LISTING
    for slug in ("mcp-gateway-launch", "webinar-invite", "series-b"):
        fetcher.pages[f"https://acme.test/blog/{slug}"] = article(slug, f"Body for {slug}. ")
    fake_llm.scripted[ItemAssessmentOut] = [scripted("x", "product_launch", {"marketing": 99, "product": 99, "rnd": 99})] * 3

    deps.pipeline.process_source(db, src.id)

    routes = {a.route for a in db.scalars(select(Assessment)).all()}
    assert routes == {"muted"}
    assert db.scalars(select(Delivery)).all() == []
