"""What lets several worker replicas share one database without a coordinator."""

from __future__ import annotations

from datetime import timedelta

from radar.models import Competitor, Source, SystemState, utcnow
from radar.pipeline import claim_once, due_source_ids


def test_claim_once_first_wins_rest_lose(db):
    assert claim_once(db, "nightly_eval", period="2026-10-03") is True
    assert claim_once(db, "nightly_eval", period="2026-10-03") is False
    assert claim_once(db, "nightly_eval", period="2026-10-03") is False
    # A new period is a fresh claim, and the row doubles as the "it ran" record.
    assert claim_once(db, "nightly_eval", period="2026-10-04") is True
    row = db.get(SystemState, "job:nightly_eval:2026-10-03")
    assert row is not None and "claimed_at" in row.value


def test_claim_once_is_scoped_by_job_name(db):
    assert claim_once(db, "nightly_eval", period="2026-10-03") is True
    assert claim_once(db, "weekly_report", period="2026-10-03") is True


def test_due_source_ids_hands_each_source_out_once(db):
    comp = Competitor(name="Acme", homepage_url="https://acme.test")
    db.add(comp)
    db.flush()
    now = utcnow()
    due = [
        Source(
            competitor_id=comp.id,
            kind="feed",
            url=f"https://acme.test/{i}.xml",
            label=str(i),
            interval_minutes=60,
            next_run_at=now - timedelta(minutes=i),
        )
        for i in range(3)
    ]
    not_due = Source(
        competitor_id=comp.id,
        kind="feed",
        url="https://acme.test/later.xml",
        label="later",
        interval_minutes=60,
        next_run_at=now + timedelta(hours=1),
    )
    disabled = Source(
        competitor_id=comp.id,
        kind="feed",
        url="https://acme.test/off.xml",
        label="off",
        interval_minutes=60,
        next_run_at=now - timedelta(hours=1),
        enabled=False,
    )
    db.add_all([*due, not_due, disabled])
    db.flush()

    first = due_source_ids(db, limit=2)
    second = due_source_ids(db, limit=2)
    third = due_source_ids(db, limit=2)

    # Oldest-due first, every source handed out exactly once, nothing not-due or disabled.
    assert first == [due[2].id, due[1].id]
    assert second == [due[0].id]
    assert third == []
    for src in due:
        assert db.get(Source, src.id).claimed_at is not None
