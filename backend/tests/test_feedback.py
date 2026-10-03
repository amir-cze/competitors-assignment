"""Feedback → golden set rules: disagreements become test cases, agreements do not, and undo is clean."""

from __future__ import annotations

from sqlalchemy import select

from radar.assess.scoring import ItemAssessmentOut
from radar.models import EvalItem, Feedback, Item
from radar.services import inbox as inbox_svc
from tests.test_pipeline import LISTING, article, make_competitor, scripted


def _scored_item(db, deps, fake_llm, fetcher):
    """One scored item: 82 for product (flagged), 20 for marketing (filed)."""
    comp, src = make_competitor(db)
    fetcher.pages["https://acme.test/blog"] = LISTING
    for slug in ("mcp-gateway-launch", "series-b", "webinar-invite"):
        fetcher.pages[f"https://acme.test/blog/{slug}"] = article(slug, f"Body for {slug}. ")
    fake_llm.scripted[ItemAssessmentOut] = [
        scripted("x", "product_launch", {"marketing": 20, "product": 82, "rnd": 10})
    ] * 3
    deps.pipeline.process_source(db, src.id)
    return db.scalar(select(Item.id).where(Item.competitor_id == comp.id).order_by(Item.title).limit(1))


def golden_for(db, item_id):
    return db.scalar(select(EvalItem).where(EvalItem.item_id == item_id))


def test_agreement_is_recorded_but_not_promoted(db, deps, fake_llm, fetcher, teams):
    item_id = _scored_item(db, deps, fake_llm, fetcher)
    fb = inbox_svc.give_feedback(db, item_id, team_key="product", verdict="useful", reason=None)
    assert fb.verdict == "useful" and fb.promoted_to_golden is False
    assert golden_for(db, item_id) is None  # Radar flagged it, the human agreed: nothing to test


def test_disagreement_is_promoted_and_undo_removes_it(db, deps, fake_llm, fetcher, teams):
    item_id = _scored_item(db, deps, fake_llm, fetcher)

    # Marketing was filed (20); marking it useful overrules the model → golden.
    fb = inbox_svc.give_feedback(db, item_id, team_key="marketing", verdict="useful", reason="we need this")
    assert fb.promoted_to_golden is True
    golden = golden_for(db, item_id)
    assert golden is not None and golden.origin == "feedback" and golden.labels == {"marketing": True}

    # A second team's disagreement merges into the same golden item.
    inbox_svc.give_feedback(db, item_id, team_key="product", verdict="not_useful", reason=None)
    assert golden_for(db, item_id).labels == {"marketing": True, "product": False}

    # Changing your mind to an agreement withdraws the stale label.
    inbox_svc.give_feedback(db, item_id, team_key="product", verdict="useful", reason=None)
    assert golden_for(db, item_id).labels == {"marketing": True}

    # Withdrawing the last feedback-derived label deletes the golden item entirely.
    inbox_svc.clear_feedback(db, item_id, "marketing")
    assert golden_for(db, item_id) is None
    assert (
        db.scalar(select(Feedback).where(Feedback.item_id == item_id, Feedback.team_id == teams[0].id))
        is None
    )


def test_undo_never_touches_seeded_golden_items(db, deps, fake_llm, fetcher, teams):
    item_id = _scored_item(db, deps, fake_llm, fetcher)
    seeded = EvalItem(
        item_id=item_id,
        competitor_name="Acme",
        title="t",
        content_text="c",
        kind="post",
        labels={"marketing": True},
        origin="seed",
    )
    db.add(seeded)
    db.flush()

    inbox_svc.give_feedback(db, item_id, team_key="marketing", verdict="useful", reason=None)
    inbox_svc.clear_feedback(db, item_id, "marketing")
    assert golden_for(db, item_id).origin == "seed" and golden_for(db, item_id).labels == {"marketing": True}
