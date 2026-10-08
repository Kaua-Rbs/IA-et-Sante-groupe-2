"""Capacity already committed by planned cases, shared by proposals, acceptance and analytics."""

import datetime as dt
from collections import defaultdict
from collections.abc import Iterable

from sqlmodel import Session, func, select

from api.planning.models import CaseStatus, PlannedCase

# Cases that hold capacity
ACTIVE_STATUSES = (CaseStatus.planned, CaseStatus.done)


def stay_days(admission: dt.date, discharge: dt.date) -> list[dt.date]:
    return [admission + dt.timedelta(days=i) for i in range((discharge - admission).days + 1)]


def used_minutes(session: Session, vacation_ids: Iterable[int]) -> dict[int, int]:
    """Planned minutes per vacation (vacations without cases are absent)."""
    ids = list(vacation_ids)
    if not ids:
        return {}
    statement = (
        select(PlannedCase.vacation_id, func.sum(PlannedCase.planned_minutes))
        .where(PlannedCase.vacation_id.in_(ids), PlannedCase.status.in_(ACTIVE_STATUSES))
        .group_by(PlannedCase.vacation_id)
    )
    return {vacation_id: int(total) for vacation_id, total in session.exec(statement).all()}


def bed_occupancy(
    session: Session, start: dt.date, end: dt.date,
) -> dict[int, dict[dt.date, int]]:
    """Occupied beds per unit and per day between `start` and `end` (inclusive)."""
    statement = select(PlannedCase).where(
        PlannedCase.status.in_(ACTIVE_STATUSES),
        PlannedCase.admission_date <= end,
        PlannedCase.discharge_date >= start,
    )
    occupancy: dict[int, dict[dt.date, int]] = defaultdict(lambda: defaultdict(int))
    for case in session.exec(statement).all():
        for day in stay_days(max(case.admission_date, start), min(case.discharge_date, end)):
            occupancy[case.bed_unit_id][day] += 1
    return occupancy
