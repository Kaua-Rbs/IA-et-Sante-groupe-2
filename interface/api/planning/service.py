import datetime as dt
from collections.abc import Iterable
from math import ceil
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from api.accounts.models import User
from api.ai.contracts import (
    BedUnitLoad, MovableCase, SchedulingInput, Scheduler, VacationSlot, reserved_stay_days,
)
from api.ai.providers import Predictors
from api.ai.cohort import (
    CohortCase, CohortPreview, cohort_metrics, optimize_cohort, sequential_baseline,
)
from api.clinical import service as clinical
from api.clinical.models import Patient, Prediction, RequestStatus, SurgicalRequest
from api.config import settings
from api.db import utcnow
from api.planning.availability import load_unavailabilities, open_minutes, surgeon_absences
from api.planning.capacity import bed_occupancy, stay_days, used_minutes
from api.planning.models import CaseStatus, PlannedCase, Proposal, ProposalStatus
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


def margin(request: SurgicalRequest) -> float:
    """Share of each vacation the request may not use: none for an urgent one."""
    return 0.0 if request.urgent else settings.EMERGENCY_MARGIN


def movable_cases(
    session: Session, vacation_ids: Iterable[int], care_type, start: dt.date, end: dt.date,
) -> tuple[MovableCase, ...]:
    """Confirmed cases an urgent request may postpone: future days only, never urgent ones.

    Those of the candidate vacations free operating time; those holding a bed of the
    needed type during [start, end] free a bed."""
    ids = list(vacation_ids)
    if not ids:
        return ()
    rows = session.exec(
        select(PlannedCase)
        .join(SurgicalRequest, SurgicalRequest.id == PlannedCase.request_id)
        .join(BedUnit, BedUnit.id == PlannedCase.bed_unit_id)
        .where(PlannedCase.status == CaseStatus.planned,
               PlannedCase.admission_date > dt.date.today(),
               SurgicalRequest.urgent == False,  # noqa: E712
               or_(PlannedCase.vacation_id.in_(ids),
                   (BedUnit.care_type == care_type)
                   & (PlannedCase.admission_date <= end) & (PlannedCase.discharge_date >= start)))
        .order_by(PlannedCase.id)
    ).all()
    return tuple(MovableCase(str(c.id), c.vacation_id, c.bed_unit_id, c.admission_date,
                             c.discharge_date, c.planned_minutes) for c in rows)


def scheduling_input(
    session: Session, request: SurgicalRequest, prediction: Prediction,
) -> SchedulingInput:
    """Snapshot of the free capacity a solver may use for this request.

    Room closures shorten the vacations; a fully closed one, or one during which
    the surgeon is absent, is left out."""
    start, end = _window(request)
    rows = session.exec(
        select(Vacation, OperatingRoom)
        .join(OperatingRoom, Vacation.room_id == OperatingRoom.id)
        .where(
            Vacation.specialty_id == request.specialty_id,
            Vacation.date >= start, Vacation.date <= end,
            Vacation.active == True, OperatingRoom.active == True,  # noqa: E712
        )
    ).all()
    used = used_minutes(session, (v.id for v, _ in rows))
    excluded = rejected_dates(session, (request.id,)).get(request.id, set())
    unavailable = load_unavailabilities(session, start, end)
    vacations = []
    for v, room in rows:
        open_min = open_minutes(v, unavailable)
        if (v.date not in excluded and open_min > 0
                and not surgeon_absences(v, unavailable, request.surgeon_id)):
            vacations.append(VacationSlot(v.id, v.date, room.name, v.specialty_id, v.surgeon_id,
                                          open_min, used.get(v.id, 0)))
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
        vacations=tuple(vacations),
        bed_units=bed_units,
        emergency_margin=margin(request),
        urgent=request.urgent,
        movable_cases=movable_cases(
            session, (v.id for v in vacations), prediction.care_type,
            start, end + dt.timedelta(days=prediction.los_days),
        ) if request.urgent else (),
    )


def cohort_snapshot(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, max_cases: int = 50,
) -> tuple[tuple[CohortCase, ...], tuple[VacationSlot, ...], tuple[BedUnitLoad, ...]]:
    """Read pending requests and current resources without creating predictions."""
    if end < start or (end - start).days > 60 or start < dt.date.today():
        raise ValueError("Choose a future planning window of at most 60 days")
    if not 1 <= max_cases <= 500:
        raise ValueError("Unsupported cohort size limit")
    from api.planning.disruptions import deprogrammed_filter
    # Urgent and deprogrammed requests keep their individual dates A/B
    requests = session.exec(select(SurgicalRequest).where(
        SurgicalRequest.status == RequestStatus.pending,
        SurgicalRequest.urgent == False,  # noqa: E712
        ~deprogrammed_filter(),
        SurgicalRequest.earliest_date <= end,
        or_(SurgicalRequest.latest_date == None, SurgicalRequest.latest_date >= start),  # noqa: E711
    ).order_by(SurgicalRequest.created_at, SurgicalRequest.id).limit(max_cases + 1)).all()
    if len(requests) > max_cases:
        raise ValueError(f"Limit the cohort to {max_cases} pending requests per run")

    excluded = rejected_dates(session, (request.id for request in requests))
    unavailable = load_unavailabilities(session, start, end)
    rows = session.exec(select(Vacation, OperatingRoom).join(
        OperatingRoom, Vacation.room_id == OperatingRoom.id,
    ).where(Vacation.date >= start, Vacation.date <= end, Vacation.active == True,  # noqa: E712
            OperatingRoom.active == True)).all()  # noqa: E712
    cases = []
    for request in requests:
        features = clinical.prediction_input(session, request)
        room = predictors.room_duration.predict(features)
        los = predictors.los.predict(features)
        if room.unit != "minutes" or los.unit != "inclusive_calendar_days":
            raise ValueError("Prediction units do not match the scheduling contract")
        care_type = predictors.care_type.predict(features)
        days = reserved_stay_days(los, care_type)
        if days > 365:
            raise ValueError("Predicted stay exceeds the supported planning horizon")
        cases.append(CohortCase(
            request.id, request.specialty_id, request.surgeon_id, room.value, days,
            care_type, max(start, request.earliest_date),
            min(end, request.latest_date or end),
            tuple(sorted(excluded.get(request.id, ()))),
            # Vacations during which the surgeon is absent, even partly
            tuple(vacation.id for vacation, _ in rows
                  if surgeon_absences(vacation, unavailable, request.surgeon_id)),
        ))

    used = used_minutes(session, (vacation.id for vacation, _ in rows))
    vacations = tuple(VacationSlot(
        vacation.id, vacation.date, room.name, vacation.specialty_id,
        vacation.surgeon_id, open_min, used.get(vacation.id, 0),
    ) for vacation, room in rows
        if (open_min := open_minutes(vacation, unavailable)) > 0)
    max_stay = max((case.los_days for case in cases), default=1)
    occupancy = bed_occupancy(session, start, end + dt.timedelta(days=max_stay - 1))
    units = session.exec(select(BedUnit).where(BedUnit.active == True)).all()  # noqa: E712
    bed_units = tuple(BedUnitLoad(unit.id, unit.name, unit.care_type, unit.capacity,
                                  dict(occupancy.get(unit.id, {}))) for unit in units)
    return tuple(cases), vacations, bed_units


def preview_cohort(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, seed: int = 0, budget_seconds: float = 1.0, max_cases: int = 50,
) -> CohortPreview:
    """Optimize pending requests together without changing proposals or bookings."""
    cases, vacations, bed_units = cohort_snapshot(
        session, start, end, predictors, max_cases=max_cases)
    return optimize_cohort(cases, vacations, bed_units,
                           emergency_margin=settings.EMERGENCY_MARGIN,
                           seed=seed, budget_seconds=budget_seconds)


def compare_cohort(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, seed: int = 0, budget_seconds: float = 1.0, max_cases: int = 50,
) -> dict:
    """Preview, side by side with the usual flow (each request takes its date A in turn)."""
    cases, vacations, bed_units = cohort_snapshot(
        session, start, end, predictors, max_cases=max_cases)
    preview = optimize_cohort(cases, vacations, bed_units,
                              emergency_margin=settings.EMERGENCY_MARGIN,
                              seed=seed, budget_seconds=budget_seconds)
    baseline = sequential_baseline(cases, vacations, bed_units,
                                   emergency_margin=settings.EMERGENCY_MARGIN)
    before = {row.request_id: row for row in baseline}
    after = {row.request_id: row for row in preview.assignments}
    patients = {request_id: {"id": patient_id, "external_ref": ref}
                for request_id, patient_id, ref in session.exec(
        select(SurgicalRequest.id, Patient.id, Patient.external_ref)
        .join(Patient, Patient.id == SurgicalRequest.patient_id)
        .where(SurgicalRequest.id.in_([case.request_id for case in cases]))
    ).all()}
    rows = [{
        "request_id": case.request_id,
        "patient": patients.get(case.request_id),
        "earliest_date": case.earliest_date,
        "baseline_date": before[case.request_id].admission_date if case.request_id in before else None,
        "optimized_date": after[case.request_id].admission_date if case.request_id in after else None,
    } for case in cases]
    return {
        "method": preview.method,
        "evaluated_cases": preview.evaluated_cases,
        "assignments": preview.assignments,
        "unassigned": preview.unassigned,
        "baseline": cohort_metrics(cases, vacations, bed_units, baseline),
        "optimized": cohort_metrics(cases, vacations, bed_units, preview.assignments),
        "rows": rows,
    }


class CohortConflict(ValueError):
    """The resource snapshot changed while cohort proposals were prepared."""


def publish_cohort_proposals(
    session: Session, start: dt.date, end: dt.date, predictors: Predictors,
    *, seed: int = 0, budget_seconds: float = 1.0, max_cases: int = 50,
) -> list[Proposal]:
    """Recompute and publish one proposal per feasible cohort assignment.

    Publication does not reserve capacity. Clinicians confirm each proposal
    through the usual endpoint, which locks and checks resources again.
    """
    preview = preview_cohort(session, start, end, predictors, seed=seed, budget_seconds=budget_seconds, max_cases=max_cases)
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
    unavailable = load_unavailabilities(session, start, end)
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
        if (vacation is None or not vacation.active or unit is None or not unit.active
                or vacation.room_id not in active_rooms):
            raise CohortConflict("A vacation, room or bed unit is no longer available")
        if (vacation.specialty_id != request.specialty_id
                or vacation.surgeon_id not in (None, request.surgeon_id)
                or vacation.date != row.admission_date
                or row.admission_date < request.earliest_date
                or (request.latest_date is not None and row.admission_date > request.latest_date)):
            raise CohortConflict("A request no longer matches its vacation or date window")
        if row.admission_date in rejected_dates(session, (request.id,)).get(request.id, ()):
            raise CohortConflict("The proposed date has been rejected")
        if surgeon_absences(vacation, unavailable, request.surgeon_id):
            raise CohortConflict("The surgeon is absent during the proposed vacation")
        prediction = clinical.build_prediction(session, request, predictors)
        if (prediction.care_type != unit.care_type
                or row.planned_minutes != ceil(prediction.room_minutes)
                or row.discharge_date != row.admission_date + dt.timedelta(days=prediction.los_days - 1)):
            raise CohortConflict("A prediction changed while the cohort was prepared")
        usable = int(open_minutes(vacation, unavailable) * (1 - settings.EMERGENCY_MARGIN))
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
            reasons=["Date choisie en plaçant ensemble toutes les demandes en attente "
                     "(optimisation de cohorte, recuit simulé).",
                     "Capacités revérifiées à la publication ; elles seront revérifiées à la confirmation."],
            scheduler=f"cohort:{preview.method}",
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


def build_proposals(
    session: Session, request: SurgicalRequest, predictors: Predictors, scheduler: Scheduler,
) -> list[Proposal]:
    """Predict again, supersede the open proposals and add fresh ones (best first).

    Nothing is committed, so a caller can drop everything when no date is found."""
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
            displaced_case_ids=list(c.displaced_case_ids),
        )
        for rank, c in enumerate(candidates, start=1)
    ]
    session.add_all(proposals)
    return proposals


def propose(
    session: Session, request: SurgicalRequest, predictors: Predictors, scheduler: Scheduler,
) -> list[Proposal]:
    """Replace the open proposals of a pending request with fresh ones (best first)."""
    proposals = build_proposals(session, request, predictors, scheduler)
    session.commit()
    for proposal in proposals:
        session.refresh(proposal)
    return proposals


def release_case(
    session: Session, case: PlannedCase, user: User, reason: str, *, exclude_date: bool = True,
) -> None:
    """Deprogram a confirmed case, without committing: the request goes back to pending.

    With `exclude_date`, the date the patient leaves is kept as a rejected proposal,
    so neither the next proposals nor a cohort refresh offer it again. A disruption
    does not exclude it: what remains open that day may still suit the patient."""
    request = session.get(SurgicalRequest, case.request_id)
    case.status = CaseStatus.cancelled
    case.cancel_reason = reason
    request.status = RequestStatus.pending
    session.add_all([case, request])
    if not exclude_date:
        return
    accepted = session.get(Proposal, case.proposal_id)
    session.add(Proposal(
        request_id=request.id, prediction_id=accepted.prediction_id, rank=accepted.rank,
        vacation_id=case.vacation_id, bed_unit_id=case.bed_unit_id,
        admission_date=case.admission_date, discharge_date=case.discharge_date,
        planned_minutes=case.planned_minutes, score=0.0, reasons=[reason],
        scheduler="release", status=ProposalStatus.rejected,
        decided_by=user.id, decided_at=utcnow(),
    ))


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


def check_still_feasible(
    session: Session, proposal: Proposal, displaced: list[PlannedCase] | None = None,
) -> list[str]:
    """Shared validator: why the proposal can no longer be applied (empty when it can).

    `displaced`: the cases it postpones, as returned by `displaced_cases`."""
    problems = []
    request = session.get(SurgicalRequest, proposal.request_id)
    prediction = session.get(Prediction, proposal.prediction_id)
    vacation = session.get(Vacation, proposal.vacation_id)
    unit = session.get(BedUnit, proposal.bed_unit_id)
    if request is None or request.status != RequestStatus.pending:
        return ["La demande n'est plus en attente."]
    if prediction is None or prediction.request_id != request.id:
        return ["La prédiction de cette proposition n'est plus disponible."]
    if vacation is None or not vacation.active:
        return ["La vacation proposée a été supprimée."]
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
    unavailable = load_unavailabilities(session, vacation.date, vacation.date)
    if surgeon_absences(vacation, unavailable, request.surgeon_id):
        problems.append("Le chirurgien est absent pendant cette vacation.")
    if displaced is None:
        displaced = displaced_cases(session, proposal)
    if len(displaced) != len(proposal.displaced_case_ids or ()):
        problems.append("Une intervention à reporter a déjà changé ou n'est plus reportable.")
    usable = open_minutes(vacation, unavailable) * (1 - margin(request))
    used = used_minutes(session, [vacation.id]).get(vacation.id, 0)
    used -= sum(case.planned_minutes for case in displaced if case.vacation_id == vacation.id)
    if used + proposal.planned_minutes > usable:
        problems.append("La vacation n'a plus assez de temps libre.")
    occupancy = bed_occupancy(session, proposal.admission_date, proposal.discharge_date)
    load = dict(occupancy.get(unit.id, {}))
    for case in displaced:
        if case.bed_unit_id == unit.id:
            for day in stay_days(case.admission_date, case.discharge_date):
                if day in load:
                    load[day] -= 1
    if any(load.get(day, 0) + 1 > unit.capacity
           for day in stay_days(proposal.admission_date, proposal.discharge_date)):
        problems.append(f"{unit.name} serait saturée pendant le séjour.")
    return problems


def displaced_cases(session: Session, proposal: Proposal) -> list[PlannedCase]:
    """Cases an urgent proposal postpones that still can be: planned, after today (locked)."""
    ids = [UUID(case_id) for case_id in proposal.displaced_case_ids or ()]
    if not ids:
        return []
    return list(session.exec(select(PlannedCase).where(
        PlannedCase.id.in_(ids), PlannedCase.status == CaseStatus.planned,
        PlannedCase.admission_date > dt.date.today(),
    ).order_by(PlannedCase.id).with_for_update()).all())


def accept(
    session: Session, proposal: Proposal, user: User, displaced: list[PlannedCase] | None = None,
) -> PlannedCase:
    """Turn the proposal into a planned case; the caller has checked feasibility.

    The `displaced` cases (urgent proposals, looked up when not given) are released in
    the same transaction: their requests go back to pending, without their former date."""
    request = session.get(SurgicalRequest, proposal.request_id)
    now = utcnow()
    if displaced is None:
        displaced = displaced_cases(session, proposal)
    for case in displaced:
        release_case(session, case, user, "Date libérée pour une urgence.")
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
