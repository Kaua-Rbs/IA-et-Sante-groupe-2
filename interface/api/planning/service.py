import datetime as dt
from math import ceil

from sqlmodel import Session, select

from api.accounts.models import User
from api.ai.contracts import BedUnitLoad, SchedulingInput, Scheduler, VacationSlot
from api.ai.providers import Predictors
from api.clinical import service as clinical
from api.clinical.models import Prediction, RequestStatus, SurgicalRequest
from api.config import settings
from api.db import utcnow
from api.planning.capacity import bed_occupancy, stay_days, used_minutes
from api.planning.models import PlannedCase, Proposal, ProposalStatus
from api.resources.models import BedUnit, OperatingRoom, Vacation


def _window(request: SurgicalRequest) -> tuple[dt.date, dt.date]:
    start = max(request.earliest_date, dt.date.today())
    end = request.latest_date or start + dt.timedelta(days=settings.SCHEDULING_HORIZON_DAYS)
    return start, end


def scheduling_input(
    session: Session, request: SurgicalRequest, prediction: Prediction,
) -> SchedulingInput:
    """Snapshot of the free capacity a solver may use for this request."""
    start, end = _window(request)
    rows = session.exec(
        select(Vacation, OperatingRoom)
        .join(OperatingRoom, Vacation.room_id == OperatingRoom.id)
        .where(
            Vacation.specialty_id == request.specialty_id,
            Vacation.date >= start, Vacation.date <= end,
            OperatingRoom.active == True,  # noqa: E712
        )
    ).all()
    used = used_minutes(session, (v.id for v, _ in rows))
    vacations = tuple(
        VacationSlot(v.id, v.date, room.name, v.specialty_id, v.surgeon_id,
                     v.duration_min, used.get(v.id, 0))
        for v, room in rows
    )
    occupancy = bed_occupancy(session, start, end + dt.timedelta(days=prediction.los_days))
    units = session.exec(select(BedUnit).where(BedUnit.active == True)).all()  # noqa: E712
    bed_units = tuple(
        BedUnitLoad(u.id, u.name, u.care_type, u.capacity, dict(occupancy.get(u.id, {})))
        for u in units
    )
    return SchedulingInput(
        specialty_id=request.specialty_id,
        surgeon_id=request.surgeon_id,
        room_minutes=prediction.room_minutes,
        los_days=prediction.los_days,
        care_type=prediction.care_type,
        earliest_date=start,
        latest_date=end,
        vacations=vacations,
        bed_units=bed_units,
        emergency_margin=settings.EMERGENCY_MARGIN,
    )


def _open_proposals(session: Session, request: SurgicalRequest) -> list[Proposal]:
    return list(session.exec(select(Proposal).where(
        Proposal.request_id == request.id, Proposal.status == ProposalStatus.proposed,
    )).all())


def propose(
    session: Session, request: SurgicalRequest, predictors: Predictors, scheduler: Scheduler,
) -> list[Proposal]:
    """Replace the open proposals of a pending request with fresh ones (best first).

    Always predicts again so the proposals match the request as it is now."""
    prediction = clinical.predict(session, request, predictors)
    candidates = scheduler.propose(
        scheduling_input(session, request, prediction), settings.PROPOSAL_COUNT,
    )
    for old in _open_proposals(session, request):
        old.status = ProposalStatus.superseded
        session.add(old)
    proposals = [
        Proposal(
            request_id=request.id,
            prediction_id=prediction.id,
            rank=rank,
            vacation_id=c.vacation_id,
            bed_unit_id=c.bed_unit_id,
            admission_date=c.admission_date,
            discharge_date=c.discharge_date,
            planned_minutes=ceil(prediction.room_minutes),
            score=c.score,
            reasons=list(c.reasons),
            scheduler=scheduler.name,
        )
        for rank, c in enumerate(candidates, start=1)
    ]
    session.add_all(proposals)
    session.commit()
    for proposal in proposals:
        session.refresh(proposal)
    return proposals


def check_still_feasible(session: Session, proposal: Proposal) -> list[str]:
    """Shared validator: why the proposal can no longer be applied (empty when it can)."""
    problems = []
    vacation = session.get(Vacation, proposal.vacation_id)
    unit = session.get(BedUnit, proposal.bed_unit_id)
    if vacation is None:
        return ["La vacation proposée n'existe plus."]
    if unit is None or not unit.active:
        return ["L'unité de lits proposée n'est plus disponible."]
    usable = vacation.duration_min * (1 - settings.EMERGENCY_MARGIN)
    if used_minutes(session, [vacation.id]).get(vacation.id, 0) + proposal.planned_minutes > usable:
        problems.append("La vacation n'a plus assez de temps libre.")
    occupancy = bed_occupancy(session, proposal.admission_date, proposal.discharge_date)
    load = occupancy.get(unit.id, {})
    if any(load.get(day, 0) + 1 > unit.capacity
           for day in stay_days(proposal.admission_date, proposal.discharge_date)):
        problems.append(f"{unit.name} serait saturée pendant le séjour.")
    return problems


def accept(session: Session, proposal: Proposal, user: User) -> PlannedCase:
    """Turn the proposal into a planned case; the caller has checked feasibility."""
    request = session.get(SurgicalRequest, proposal.request_id)
    now = utcnow()
    for other in _open_proposals(session, request):
        if other.id != proposal.id:
            other.status = ProposalStatus.superseded
            session.add(other)
    proposal.status = ProposalStatus.accepted
    proposal.decided_by = user.id
    proposal.decided_at = now
    request.status = RequestStatus.scheduled
    case = PlannedCase(
        request_id=request.id,
        proposal_id=proposal.id,
        vacation_id=proposal.vacation_id,
        bed_unit_id=proposal.bed_unit_id,
        admission_date=proposal.admission_date,
        discharge_date=proposal.discharge_date,
        planned_minutes=proposal.planned_minutes,
    )
    session.add_all([proposal, request, case])
    session.commit()
    session.refresh(case)
    return case
