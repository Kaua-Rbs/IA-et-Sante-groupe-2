import datetime as dt
from collections.abc import Iterable
from math import ceil
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.accounts.models import User
from api.ai.contracts import BedUnitLoad, SchedulingInput, Scheduler, VacationSlot
from api.ai.providers import Predictors
from api.ai.cohort import CohortCase, CohortPreview, optimize_cohort
from api.clinical import service as clinical
from api.clinical.models import Prediction, RequestStatus, SurgicalRequest
from api.config import settings
from api.db import utcnow
from api.planning.capacity import bed_occupancy, stay_days, used_minutes
from api.planning.models import PlannedCase, Proposal, ProposalStatus
from api.planning.replanning import record_change
from api.resources.models import BedUnit, OperatingRoom, Vacation


def _window(request: SurgicalRequest) -> tuple[dt.date, dt.date]:
    start = max(request.earliest_date, dt.date.today())
    end = request.latest_date or start + dt.timedelta(days=settings.SCHEDULING_HORIZON_DAYS)
    return start, end


def rejected_dates(session: Session, request_ids: Iterable[UUID]) -> dict[UUID, set[dt.date]]:
    dates = {}
    for proposal in session.exec(select(Proposal).where(
        Proposal.request_id.in_(tuple(request_ids)),
        Proposal.status == ProposalStatus.rejected,
    )).all():
        dates.setdefault(proposal.request_id, set()).add(proposal.admission_date)
    return dates


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
    excluded = rejected_dates(session, (request.id,)).get(request.id, set())
    vacations = tuple(
        VacationSlot(v.id, v.date, room.name, v.specialty_id, v.surgeon_id,
                     v.duration_min, used.get(v.id, 0))
        for v, room in rows if v.date not in excluded
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


def cohort_snapshot(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, occupancy_extension: float = 1.0, max_cases: int = 50,
) -> tuple[tuple[CohortCase, ...], tuple[VacationSlot, ...], tuple[BedUnitLoad, ...]]:
    """Read pending requests and current resources without creating predictions."""
    if end < start or (end - start).days > 60 or start < dt.date.today():
        raise ValueError("Choose a future planning window of at most 60 days")
    if not 1 <= occupancy_extension <= 2:
        raise ValueError("Occupancy extension must be between 1 and 2")
    if not 1 <= max_cases <= 500:
        raise ValueError("Unsupported cohort size limit")
    requests = session.exec(select(SurgicalRequest).where(
        SurgicalRequest.status == RequestStatus.pending,
        SurgicalRequest.earliest_date <= end,
        or_(SurgicalRequest.latest_date == None, SurgicalRequest.latest_date >= start),  # noqa: E711
    ).order_by(SurgicalRequest.created_at, SurgicalRequest.id).limit(max_cases + 1)).all()
    if len(requests) > max_cases:
        raise ValueError(f"Limit the cohort to {max_cases} pending requests per run")

    excluded = rejected_dates(session, (request.id for request in requests))
    cases = []
    for request in requests:
        features = clinical.prediction_input(session, request)
        room = predictors.room_duration.predict(features)
        los = predictors.los.predict(features)
        if room.unit != "minutes" or los.unit != "inclusive_calendar_days":
            raise ValueError("Prediction units do not match the scheduling contract")
        days = ceil(los.value)
        if days > 365:
            raise ValueError("Predicted stay exceeds the supported planning horizon")
        cases.append(CohortCase(
            request.id, request.specialty_id, request.surgeon_id, room.value, days,
            predictors.care_type.predict(features), max(start, request.earliest_date),
            min(end, request.latest_date or end),
            tuple(sorted(excluded.get(request.id, ()))),
        ))

    rows = session.exec(select(Vacation, OperatingRoom).join(
        OperatingRoom, Vacation.room_id == OperatingRoom.id,
    ).where(Vacation.date >= start, Vacation.date <= end,
            OperatingRoom.active == True)).all()  # noqa: E712
    used = used_minutes(session, (vacation.id for vacation, _ in rows))
    vacations = tuple(VacationSlot(
        vacation.id, vacation.date, room.name, vacation.specialty_id,
        vacation.surgeon_id, vacation.duration_min, used.get(vacation.id, 0),
    ) for vacation, room in rows)
    max_stay = ceil(max((case.los_days for case in cases), default=1) * occupancy_extension)
    occupancy = bed_occupancy(session, start, end + dt.timedelta(days=max_stay - 1))
    units = session.exec(select(BedUnit).where(BedUnit.active == True)).all()  # noqa: E712
    bed_units = tuple(BedUnitLoad(unit.id, unit.name, unit.care_type, unit.capacity,
                                  dict(occupancy.get(unit.id, {}))) for unit in units)
    return tuple(cases), vacations, bed_units


def preview_cohort(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, method: str, seed: int = 0, budget_seconds: float = 1.0, max_cases: int = 50,
) -> CohortPreview:
    """Optimize pending requests together without changing proposals or bookings."""
    cases, vacations, bed_units = cohort_snapshot(
        session, start, end, predictors, max_cases=max_cases)
    return optimize_cohort(cases, vacations, bed_units, method=method,
                           emergency_margin=settings.EMERGENCY_MARGIN,
                           seed=seed, budget_seconds=budget_seconds)


class CohortConflict(ValueError):
    """The resource snapshot changed while cohort proposals were prepared."""


def publish_cohort_proposals(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, method: str, seed: int = 0, budget_seconds: float = 1.0, max_cases: int = 50,
) -> list[Proposal]:
    """Recompute and publish one proposal per feasible cohort assignment.

    Publication does not reserve capacity. Clinicians confirm each proposal
    through the usual endpoint, which locks and checks resources again.
    """
    preview = preview_cohort(session, start, end, predictors, method=method,
                             seed=seed, budget_seconds=budget_seconds, max_cases=max_cases)
    if not preview.evaluated_cases:
        return []
    request_ids = sorted(
        {row.request_id for row in preview.assignments} | set(preview.unassigned), key=str,
    )
    vacation_ids = sorted({row.vacation_id for row in preview.assignments})
    unit_ids = sorted({row.bed_unit_id for row in preview.assignments})
    # PostgreSQL row locks serialize confirmation and publication for shared
    # resources. SQLite ignores FOR UPDATE and is suitable only for local demo.
    requests = {row.id: row for row in session.exec(
        select(SurgicalRequest).where(SurgicalRequest.id.in_(request_ids))
        .order_by(SurgicalRequest.id).with_for_update()
        .execution_options(populate_existing=True)
    ).all()}
    vacations = {row.id: row for row in session.exec(
        select(Vacation).where(Vacation.id.in_(vacation_ids))
        .order_by(Vacation.id).with_for_update()
        .execution_options(populate_existing=True)
    ).all()}
    units = {row.id: row for row in session.exec(
        select(BedUnit).where(BedUnit.id.in_(unit_ids))
        .order_by(BedUnit.id).with_for_update()
        .execution_options(populate_existing=True)
    ).all()}
    room_ids = {vacation.room_id for vacation in vacations.values()}
    active_rooms = {row.id for row in session.exec(
        select(OperatingRoom).where(OperatingRoom.id.in_(room_ids),
                                     OperatingRoom.active == True)  # noqa: E712
        .order_by(OperatingRoom.id).with_for_update()
        .execution_options(populate_existing=True)
    ).all()}
    used = used_minutes(session, vacation_ids)
    occupancy = bed_occupancy(
        session, min(row.admission_date for row in preview.assignments),
        max(row.discharge_date for row in preview.assignments),
    ) if preview.assignments else {}
    predictions = {}
    for row in preview.assignments:
        request = requests.get(row.request_id)
        vacation = vacations.get(row.vacation_id)
        unit = units.get(row.bed_unit_id)
        if request is None or request.status != RequestStatus.pending:
            raise CohortConflict("A request is no longer pending")
        if vacation is None or unit is None or not unit.active or vacation.room_id not in active_rooms:
            raise CohortConflict("A vacation, room or bed unit is no longer available")
        if (vacation.specialty_id != request.specialty_id
                or vacation.surgeon_id not in (None, request.surgeon_id)
                or vacation.date != row.admission_date
                or row.admission_date < request.earliest_date
                or (request.latest_date is not None and row.admission_date > request.latest_date)):
            raise CohortConflict("A request no longer matches its vacation or date window")
        if row.admission_date in rejected_dates(session, (request.id,)).get(request.id, ()):
            raise CohortConflict("The proposed date has been rejected")
        prediction = clinical.build_prediction(session, request, predictors)
        if (prediction.care_type != unit.care_type
                or row.planned_minutes != ceil(prediction.room_minutes)
                or row.discharge_date != row.admission_date + dt.timedelta(days=prediction.los_days - 1)):
            raise CohortConflict("A prediction changed while the cohort was prepared")
        usable = int(vacation.duration_min * (1 - settings.EMERGENCY_MARGIN))
        if used.get(vacation.id, 0) + row.planned_minutes > usable:
            raise CohortConflict("Vacation capacity changed while the cohort was prepared")
        for day in stay_days(row.admission_date, row.discharge_date):
            if occupancy.get(unit.id, {}).get(day, 0) + 1 > unit.capacity:
                raise CohortConflict("Bed capacity changed while the cohort was prepared")
        used[vacation.id] = used.get(vacation.id, 0) + row.planned_minutes
        for day in stay_days(row.admission_date, row.discharge_date):
            occupancy.setdefault(unit.id, {})[day] = occupancy.get(unit.id, {}).get(day, 0) + 1
        predictions[row.request_id] = prediction

    for old in session.exec(select(Proposal).where(
        Proposal.request_id.in_(request_ids),
        Proposal.status == ProposalStatus.proposed,
    )).all():
        old.status = ProposalStatus.superseded
        session.add(old)
    proposals = []
    for row in preview.assignments:
        prediction = predictions[row.request_id]
        session.add(prediction)
        proposals.append(Proposal(
            request_id=row.request_id, prediction_id=prediction.id, rank=1,
            vacation_id=row.vacation_id, bed_unit_id=row.bed_unit_id,
            admission_date=row.admission_date, discharge_date=row.discharge_date,
            planned_minutes=row.planned_minutes, score=0.0,
            reasons=[f"Proposition de cohorte : {method}.",
                     "Capacités revérifiées à la publication ; elles seront revérifiées à la confirmation."],
            scheduler=f"cohort:{method}",
        ))
    try:
        session.add_all(proposals)
        session.commit()
        for proposal in proposals:
            session.refresh(proposal)
    except IntegrityError as exc:
        session.rollback()
        raise CohortConflict("The cohort could not be published atomically") from exc
    return proposals


def _open_proposals(session: Session, request: SurgicalRequest) -> list[Proposal]:
    return list(session.exec(select(Proposal).where(
        Proposal.request_id == request.id, Proposal.status == ProposalStatus.proposed,
    )).all())


def propose(
    session: Session, request: SurgicalRequest, predictors: Predictors, scheduler: Scheduler,
) -> list[Proposal]:
    """Replace the open proposals of a pending request with fresh ones (best first).

    Always predicts again so the proposals match the request as it is now."""
    prediction = clinical.build_prediction(session, request, predictors)
    session.add(prediction)
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


def lock_proposal_resources(session: Session, proposal: Proposal) -> None:
    """Serialize decisions sharing a request, vacation or bed unit on PostgreSQL."""
    for model, key in ((SurgicalRequest, proposal.request_id),
                       (Vacation, proposal.vacation_id),
                       (BedUnit, proposal.bed_unit_id)):
        session.exec(select(model).where(model.id == key).with_for_update()
                     .execution_options(populate_existing=True)).first()
    vacation = session.get(Vacation, proposal.vacation_id)
    if vacation is not None:
        session.exec(select(OperatingRoom).where(OperatingRoom.id == vacation.room_id)
                     .with_for_update().execution_options(populate_existing=True)).first()
    session.refresh(proposal)


def check_still_feasible(session: Session, proposal: Proposal) -> list[str]:
    """Shared validator: why the proposal can no longer be applied (empty when it can)."""
    problems = []
    request = session.get(SurgicalRequest, proposal.request_id)
    prediction = session.get(Prediction, proposal.prediction_id)
    vacation = session.get(Vacation, proposal.vacation_id)
    unit = session.get(BedUnit, proposal.bed_unit_id)
    if request is None or request.status != RequestStatus.pending:
        return ["La demande n'est plus en attente."]
    if prediction is None or prediction.request_id != request.id:
        return ["La prédiction de cette proposition n'est plus disponible."]
    if vacation is None:
        return ["La vacation proposée n'existe plus."]
    if unit is None or not unit.active:
        return ["L'unité de lits proposée n'est plus disponible."]
    room = session.get(OperatingRoom, vacation.room_id)
    if room is None or not room.active:
        problems.append("La salle n'est plus disponible.")
    if (vacation.specialty_id != request.specialty_id
            or vacation.surgeon_id not in (None, request.surgeon_id)):
        problems.append("La vacation ne correspond plus à la spécialité ou au chirurgien.")
    if (vacation.date != proposal.admission_date
            or proposal.admission_date < max(request.earliest_date, dt.date.today())
            or (request.latest_date is not None and proposal.admission_date > request.latest_date)):
        problems.append("La date proposée n'est plus admissible.")
    if proposal.admission_date in rejected_dates(session, (request.id,)).get(request.id, ()):
        problems.append("Cette date a été écartée pour la demande.")
    if unit.care_type != prediction.care_type:
        problems.append("Le type d'hébergement ne correspond plus à la prédiction.")
    if (proposal.planned_minutes != ceil(prediction.room_minutes)
            or proposal.discharge_date != proposal.admission_date
            + dt.timedelta(days=prediction.los_days - 1)):
        problems.append("La durée de la proposition ne correspond plus à sa prédiction.")
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
    record_change(session, "case_confirmed", user.id)
    session.commit()
    session.refresh(case)
    return case
