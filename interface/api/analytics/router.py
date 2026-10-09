"""Aggregated indicators only: no patient-level rows leave these endpoints."""

import datetime as dt

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from api.accounts.security import CurrentUser, StaffUser
from api.clinical.models import Prediction
from api.db import SessionDep
from api.planning.capacity import bed_occupancy, stay_days, used_minutes
from api.planning.models import CaseStatus, PlannedCase, Proposal
from api.resources.models import BedUnit, CareType, OperatingRoom, Vacation

router = APIRouter(prefix="/analytics", tags=["analytics"])

MAX_PERIOD_DAYS = 366


class DayOccupancy(BaseModel):
    date: dt.date
    occupied: int
    rate: float


class UnitOccupancy(BaseModel):
    bed_unit_id: int
    name: str
    care_type: CareType
    capacity: int
    days: list[DayOccupancy]


class VacationFill(BaseModel):
    vacation_id: int
    date: dt.date
    room_id: int
    room_name: str
    specialty_id: int
    duration_min: int
    planned_minutes: int
    fill_rate: float


class PredictionAccuracy(BaseModel):
    evaluated_cases: int
    room_minutes_mae: float | None
    room_minutes_overestimated: int
    room_minutes_underestimated: int
    los_days_mae: float | None


def _period(start: dt.date | None, end: dt.date | None) -> tuple[dt.date, dt.date]:
    start = start or dt.date.today()
    end = end or start + dt.timedelta(days=13)
    if end < start or (end - start).days >= MAX_PERIOD_DAYS:
        raise HTTPException(status_code=422, detail=f"Period must be 1 to {MAX_PERIOD_DAYS} days")
    return start, end


@router.get("/occupancy", response_model=list[UnitOccupancy])
def occupancy(
    session: SessionDep, current_user: CurrentUser,
    start: dt.date | None = None, end: dt.date | None = None,
):
    """Planned bed occupancy per unit and per day (default: the next 14 days)."""
    start, end = _period(start, end)
    load = bed_occupancy(session, start, end)
    units = session.exec(select(BedUnit).order_by(BedUnit.name)).all()
    return [
        UnitOccupancy(
            bed_unit_id=u.id, name=u.name, care_type=u.care_type, capacity=u.capacity,
            days=[
                DayOccupancy(date=day, occupied=load.get(u.id, {}).get(day, 0),
                             rate=round(load.get(u.id, {}).get(day, 0) / u.capacity, 4))
                for day in stay_days(start, end)
            ],
        )
        for u in units
    ]


@router.get("/vacations", response_model=list[VacationFill])
def vacation_fill(
    session: SessionDep, current_user: CurrentUser,
    start: dt.date | None = None, end: dt.date | None = None,
):
    """Planned minutes against vacation length (default: the next 14 days)."""
    start, end = _period(start, end)
    rows = session.exec(
        select(Vacation, OperatingRoom)
        .join(OperatingRoom, Vacation.room_id == OperatingRoom.id)
        .where(Vacation.date >= start, Vacation.date <= end)
        .order_by(Vacation.date, Vacation.start_time, OperatingRoom.name)
    ).all()
    used = used_minutes(session, (v.id for v, _ in rows))
    return [
        VacationFill(
            vacation_id=v.id, date=v.date, room_id=room.id, room_name=room.name,
            specialty_id=v.specialty_id, duration_min=v.duration_min,
            planned_minutes=used.get(v.id, 0),
            fill_rate=round(used.get(v.id, 0) / v.duration_min, 4),
        )
        for v, room in rows
    ]


def _accuracy(session: Session) -> PredictionAccuracy:
    rows = session.exec(
        select(PlannedCase, Prediction)
        .join(Proposal, PlannedCase.proposal_id == Proposal.id)
        .join(Prediction, Proposal.prediction_id == Prediction.id)
        .where(PlannedCase.status == CaseStatus.done)
    ).all()
    room_errors = [p.room_minutes - c.actual_room_minutes for c, p in rows]
    los_errors = [p.los_days - c.actual_los_days for c, p in rows]
    return PredictionAccuracy(
        evaluated_cases=len(rows),
        room_minutes_mae=round(sum(map(abs, room_errors)) / len(rows), 2) if rows else None,
        room_minutes_overestimated=sum(e > 0 for e in room_errors),
        room_minutes_underestimated=sum(e < 0 for e in room_errors),
        los_days_mae=round(sum(map(abs, los_errors)) / len(rows), 2) if rows else None,
    )


@router.get("/predictions", response_model=PredictionAccuracy)
def prediction_accuracy(session: SessionDep, current_user: StaffUser):
    """Error of the predictions used for completed cases."""
    return _accuracy(session)
