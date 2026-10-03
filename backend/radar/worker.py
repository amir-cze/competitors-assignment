"""The unattended part. One process, a few scheduled jobs, no external queue.

- every `worker_tick_seconds`: claim due sources (SKIP LOCKED) and process them on a small thread pool
- every minute: heartbeat (DB row + optional dead-man URL) and retry pending Slack deliveries
- every hour at :05: send team digests that are due
- nightly: golden-set evaluation, retention pruning

Run more replicas for more throughput. Source claiming is SKIP LOCKED, digests are
idempotent via Delivery.dedupe_key, the nightly eval is claimed once per day via
system_state; heartbeat and prune are harmless to repeat.
"""

from __future__ import annotations

import signal
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait

import httpx
from apscheduler.schedulers.background import BackgroundScheduler

from radar import __version__
from radar.container import Deps, build_deps
from radar.db import session_scope
from radar.logging import configure_logging, get_logger
from radar.models import SystemState, utcnow
from radar.pipeline import claim_once, due_source_ids, prune_retention

log = get_logger(__name__)


class Worker:
    def __init__(self, deps: Deps):
        self._deps = deps
        self._stop = threading.Event()
        self._tick_lock = threading.Lock()

    # ----------------------------------------------------------------------- jobs

    def heartbeat(self) -> None:
        try:
            with session_scope() as session:
                state = session.get(SystemState, "worker_heartbeat") or SystemState(
                    key="worker_heartbeat", value={}
                )
                state.value = {
                    "at": utcnow().isoformat(),
                    "version": __version__,
                    "pid": threading.get_native_id(),
                }
                session.add(state)
                retried = self._deps.deliverer.retry_pending(session)
                if retried:
                    log.info("worker.deliveries_retried", count=retried)
        except Exception as exc:
            log.error("worker.heartbeat_db_failed", error=str(exc))
            return
        url = self._deps.settings.healthcheck_url
        if url:
            try:
                httpx.get(url, timeout=5.0)
            except httpx.HTTPError as exc:
                log.warning("worker.healthcheck_ping_failed", error=str(exc))

    def tick(self) -> None:
        """Process everything that is due. Never overlaps with itself."""
        if not self._tick_lock.acquire(blocking=False):
            return
        try:
            concurrency = self._deps.settings.worker_concurrency
            with session_scope() as session:
                ids = due_source_ids(session, limit=concurrency * 2)
            if ids:
                log.info("worker.tick", due=len(ids))
                with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="src") as pool:
                    wait([pool.submit(self._process_one, sid) for sid in ids])
            with session_scope() as session:
                self._deps.pipeline.score_pending_items(session)
        except Exception as exc:
            log.exception("worker.tick_failed", error=str(exc))
        finally:
            self._tick_lock.release()

    def _process_one(self, source_id: uuid.UUID) -> None:
        try:
            with session_scope() as session:
                run = self._deps.pipeline.process_source(session, source_id, trigger="schedule")
                log.info(
                    "worker.source_done",
                    source_id=str(source_id),
                    status=run.status,
                    new=run.items_new,
                    cost=round(run.llm_cost_usd, 4),
                )
        except Exception as exc:
            log.exception("worker.source_crashed", source_id=str(source_id), error=str(exc))

    def digests(self) -> None:
        try:
            with session_scope() as session:
                results = self._deps.digests.run_due(session)
                sent = [r for r in results if r.get("status") == "sent"]
                if sent:
                    log.info("worker.digests_sent", results=sent)
        except Exception as exc:
            log.exception("worker.digest_failed", error=str(exc))

    def nightly(self) -> None:
        try:
            with session_scope() as session:
                log.info("worker.pruned", **prune_retention(session, self._deps.settings))
            # Prune is idempotent; the eval is not (it spends LLM budget and writes an EvalRun),
            # so with several worker replicas only the one that wins the claim runs it.
            today = utcnow().date().isoformat()
            with session_scope() as session:
                if not claim_once(session, "nightly_eval", period=today):
                    log.info("worker.eval_skipped", reason="claimed_by_other_replica", period=today)
                    return
            with session_scope() as session:
                run = self._deps.evaluator.run(session, trigger="schedule")
                log.info("worker.eval_done", n=run.n_items, metrics=run.metrics)
        except Exception as exc:
            log.exception("worker.nightly_failed", error=str(exc))

    # ----------------------------------------------------------------------- lifecycle

    def build_scheduler(self) -> BackgroundScheduler:
        s = self._deps.settings
        scheduler = BackgroundScheduler(
            timezone="UTC", job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 120}
        )
        scheduler.add_job(
            self.tick, "interval", seconds=s.worker_tick_seconds, id="tick", next_run_time=utcnow()
        )
        scheduler.add_job(self.heartbeat, "interval", seconds=60, id="heartbeat", next_run_time=utcnow())
        scheduler.add_job(self.digests, "cron", minute=5, id="digests")
        scheduler.add_job(self.nightly, "cron", hour=s.eval_hour_utc, minute=15, id="nightly")
        return scheduler

    def run_forever(self) -> None:
        s = self._deps.settings
        log.info(
            "worker.start",
            version=__version__,
            tick=s.worker_tick_seconds,
            concurrency=s.worker_concurrency,
            llm=self._deps.llm.configured,
        )
        scheduler = self.build_scheduler()
        scheduler.start()

        def _shutdown(*_):
            log.info("worker.stopping")
            self._stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _shutdown)
            except (ValueError, OSError):  # not main thread / unsupported platform
                pass
        try:
            while not self._stop.is_set():
                time.sleep(1)
        finally:
            scheduler.shutdown(wait=True)
            log.info("worker.stopped")


def run() -> None:
    configure_logging()
    Worker(build_deps()).run_forever()


if __name__ == "__main__":
    run()
