"""Durable change queue for refreshing proposals from current database state.

The API runs one process/worker. Database events survive restarts; a failed
refresh preserves earlier proposals and never changes confirmed bookings.
"""

import asyncio
from contextlib import asynccontextmanager
import datetime as dt
import logging
from threading import Lock
from uuid import UUID

from sqlmodel import Session, func, select

from api.ai.cohort import METHOD
from api.ai.providers import get_predictors, get_scheduler
from api.config import settings
from api.db import engine, utcnow
from api.planning.models import PlanningChange, ReplanRun

logger = logging.getLogger(__name__)
_run_lock = Lock()


def record_change(session: Session, kind: str, actor_id: UUID | None = None) -> None:
    """Commit the event together with the resource/request mutation."""
    session.add(PlanningChange(kind=kind, actor_id=actor_id))


def recover_interrupted_runs() -> None:
    """One API process owns the queue; retry interrupted work after restart."""
    with Session(engine) as session:
        interrupted = session.exec(select(ReplanRun).where(
            ReplanRun.status == "running",
        )).all()
        for run in interrupted:
            run.status = "interrupted"
            run.failure_type = "ProcessRestart"
            run.finished_at = utcnow()
            session.add(run)
        if interrupted:
            record_change(session, "restart_retry")
        session.commit()


def queue_status(session: Session) -> dict:
    pending = session.exec(select(func.count()).select_from(PlanningChange).where(
        PlanningChange.run_id == None,  # noqa: E711
    )).one()
    runs = session.exec(select(ReplanRun).order_by(
        ReplanRun.started_at.desc(), ReplanRun.id,
    ).limit(10)).all()
    return {
        "automatic": settings.AUTO_REPLAN_ENABLED,
        "method": METHOD,
        "horizon_days": settings.REPLAN_HORIZON_DAYS,
        "pending_changes": pending,
        "runs": runs,
    }


def process_pending_changes() -> dict | None:
    """Claim a batch once; failures stay visible until a later change/retry."""
    if not _run_lock.acquire(blocking=False):
        return None
    try:
        # No run in this API process owns the lock now. Recover a prior run
        # whose final status could not be saved during a database interruption.
        recover_interrupted_runs()
        with Session(engine) as session:
            events = session.exec(select(PlanningChange).where(
                PlanningChange.run_id == None,  # noqa: E711
            ).order_by(PlanningChange.created_at, PlanningChange.id).limit(1000)).all()
            if not events:
                return None
            start = dt.date.today()
            run = ReplanRun(
                method=METHOD, start=start,
                end=start + dt.timedelta(days=settings.REPLAN_HORIZON_DAYS - 1),
                event_count=len(events),
            )
            session.add(run)
            # No relationship orders the flush: insert the run before the events
            # point to it, or PostgreSQL rejects the foreign key.
            session.flush()
            for event in events:
                event.run_id = run.id
                session.add(event)
            session.commit()
            session.refresh(run)
            run_id = run.id
        # Publication has a separate atomic transaction. A crash after its
        # commit can cause a later proposal refresh, but cannot duplicate bookings.
        # The two steps fail independently: urgent and deprogrammed requests still get
        # their dates when the cohort cannot be solved, and the reverse.
        from api.planning.disruptions import refresh_individual
        from api.planning.service import publish_cohort_proposals
        count, failure = 0, None
        try:
            with Session(engine) as session:
                count += len(publish_cohort_proposals(
                    session, start, run.end, get_predictors(),
                    budget_seconds=settings.REPLAN_BUDGET_SECONDS,
                    max_cases=settings.REPLAN_MAX_CASES,
                ))
        except Exception as exc:
            # Never persist exception messages: model/DB errors can include inputs.
            failure = type(exc).__name__
            logger.warning("Cohort refresh failed: %s", failure)
        try:
            with Session(engine) as session:
                # Urgent and deprogrammed requests: renew their dates A/B if stale
                count += refresh_individual(session, get_predictors(), get_scheduler())
        except Exception as exc:
            failure = failure or type(exc).__name__
            logger.warning("Individual refresh failed: %s", type(exc).__name__)
        status = "failed" if failure else "succeeded"
        with Session(engine) as session:
            run = session.get(ReplanRun, run_id)
            run.status, run.failure_type = status, failure
            run.proposals_count, run.finished_at = count, utcnow()
            session.add(run)
            session.commit()
            session.refresh(run)
            return run.model_dump()
    finally:
        _run_lock.release()


@asynccontextmanager
async def change_worker():
    """Optional background refresh; the event queue is always recorded."""
    recover_interrupted_runs()
    stop = asyncio.Event()

    async def work() -> None:
        while not stop.is_set():
            try:
                await asyncio.to_thread(process_pending_changes)
            except Exception as exc:
                logger.error("Replanning worker error: %s", type(exc).__name__)
            try:
                await asyncio.wait_for(stop.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    task = asyncio.create_task(work()) if settings.AUTO_REPLAN_ENABLED else None
    try:
        yield
    finally:
        stop.set()
        if task is not None:
            await task
