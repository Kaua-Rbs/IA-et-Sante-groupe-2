"""After a disruption, deprogram the future cases left without a valid slot, then offer dates A/B.

Today and the past are frozen: a case of today that no longer fits stays booked and is
listed as a conflict for the team. A future case is deprogrammed only when it must be:
in a shortened vacation, or a bed unit over capacity, the first booked keep their place.
Nothing new is booked: the surgeon confirms one of the dates A/B.
"""

import datetime as dt
import logging
from collections import defaultdict
from uuid import UUID

from sqlalchemy import exists, or_
from sqlmodel import Session, select

from api.accounts.models import User
from api.ai.contracts import Scheduler
from api.ai.providers import Predictors
from api.clinical.models import Patient, Prediction, RequestStatus, SurgicalRequest
from api.planning import service
from api.planning.availability import (
    describe, load_unavailabilities, open_minutes, room_closures, surgeon_absences,
)
from api.planning.capacity import bed_occupancy, stay_days
from api.planning.models import CaseStatus, PlannedCase, Proposal, ProposalStatus
from api.planning.replanning import record_change
from api.resources.models import BedUnit, OperatingRoom, Surgeon, Vacation

logger = logging.getLogger(__name__)


def deprogrammed_filter():
    """SQL condition: the request lost a booking to a disruption, an emergency or a move."""
    return exists().where(
        PlannedCase.request_id == SurgicalRequest.id,
        PlannedCase.status == CaseStatus.cancelled,
        PlannedCase.cancel_reason != None,  # noqa: E711
    )


def invalid_bookings(session: Session, start: dt.date) -> list[tuple[PlannedCase, str]]:
    """Planned cases from `start` on that must leave their slot, with the reason."""
    rows = session.exec(
        select(PlannedCase, SurgicalRequest, Vacation, OperatingRoom, BedUnit, Prediction)
        .select_from(PlannedCase)
        .join(SurgicalRequest, SurgicalRequest.id == PlannedCase.request_id)
        .join(Proposal, Proposal.id == PlannedCase.proposal_id)
        .join(Prediction, Prediction.id == Proposal.prediction_id)
        .join(Vacation, Vacation.id == PlannedCase.vacation_id)
        .join(OperatingRoom, OperatingRoom.id == Vacation.room_id)
        .join(BedUnit, BedUnit.id == PlannedCase.bed_unit_id)
        .where(PlannedCase.status == CaseStatus.planned, PlannedCase.admission_date >= start)
        # First booked, first kept
        .order_by(PlannedCase.created_at, PlannedCase.id)
    ).all()
    if not rows:
        return []
    unavailable = load_unavailabilities(session, start, max(v.date for _, _, v, *_ in rows))
    names = {("room", r.id): r.name for r in session.exec(select(OperatingRoom)).all()}
    names |= {("surgeon", s.id): s.name for s in session.exec(select(Surgeon)).all()}

    released: list[tuple[PlannedCase, str]] = []
    kept = []
    for case, request, vacation, room, unit, prediction in rows:
        absences = surgeon_absences(vacation, unavailable, request.surgeon_id)
        if not vacation.active:
            reason = "Vacation supprimée."
        elif not room.active:
            reason = f"{room.name} fermée."
        elif (vacation.date != case.admission_date or vacation.specialty_id != request.specialty_id
              or vacation.surgeon_id not in (None, request.surgeon_id)):
            reason = "Vacation modifiée."
        elif absences:
            reason = f"{describe(absences[0], names)}."
        elif not unit.active or unit.care_type != prediction.care_type:
            reason = f"{unit.name} n'accueille plus ce séjour."
        else:
            kept.append((case, vacation))
            continue
        released.append((case, reason))

    # Shortened vacations: the cases that no longer fit leave, latest booked first
    by_vacation = defaultdict(list)
    for case, vacation in kept:
        by_vacation[vacation.id].append((case, vacation))
    still = []
    for cases in by_vacation.values():
        vacation = cases[0][1]
        capacity, used = open_minutes(vacation, unavailable), 0
        closures = room_closures(vacation, unavailable)
        reason = (f"{describe(closures[0], names)} : plus de place dans la vacation."
                  if closures else "Vacation raccourcie : plus de place.")
        for case, _ in cases:
            if used + case.planned_minutes <= capacity:
                used += case.planned_minutes
                still.append(case)
            else:
                released.append((case, reason))

    # Bed units over capacity: release the latest booked future stays on the saturated days
    gone = {case.id for case, _ in released}
    last = max(case.discharge_date for case in still) if still else start
    occupancy = bed_occupancy(session, start, last)
    load = {unit: dict(days) for unit, days in occupancy.items()}
    for case, _ in released:
        for day in stay_days(max(start, case.admission_date), case.discharge_date):
            if day in load.get(case.bed_unit_id, {}):
                load[case.bed_unit_id][day] -= 1
    units = {unit.id: unit for unit in session.exec(select(BedUnit)).all()}
    for case in sorted(still, key=lambda c: (c.created_at, c.id), reverse=True):
        unit = units[case.bed_unit_id]
        days = stay_days(case.admission_date, case.discharge_date)
        if case.id not in gone and any(load.get(unit.id, {}).get(d, 0) > unit.capacity for d in days):
            released.append((case, f"Plus assez de lits en {unit.name}."))
            gone.add(case.id)
            for day in days:
                if day in load.get(unit.id, {}):
                    load[unit.id][day] -= 1
    return released


def offer_new_dates(
    session: Session, request_ids: list[UUID], predictors: Predictors, scheduler: Scheduler,
) -> None:
    """Dates A/B for each request; a failure leaves it pending for the next refresh."""
    for request_id in request_ids:
        try:
            request = session.get(SurgicalRequest, request_id)
            if request is not None and request.status == RequestStatus.pending:
                service.propose(session, request, predictors, scheduler)
        except Exception as exc:
            session.rollback()
            logger.warning("New dates for a deprogrammed request failed: %s", type(exc).__name__)


def deprogram_invalid_bookings(
    session: Session, user: User, predictors: Predictors, scheduler: Scheduler,
) -> list[UUID]:
    """Commit the disruption's consequences: deprogram, then offer dates A/B at once."""
    released = invalid_bookings(session, dt.date.today() + dt.timedelta(days=1))
    for case, reason in released:
        service.release_case(session, case, user, f"Déprogrammée : {reason}", exclude_date=False)
    if released:
        record_change(session, "cases_deprogrammed", user.id)
    session.commit()
    request_ids = [case.request_id for case, _ in released]
    offer_new_dates(session, request_ids, predictors, scheduler)
    return request_ids


def refresh_individual(session: Session, predictors: Predictors, scheduler: Scheduler) -> int:
    """Renew the dates A/B that became infeasible for requests outside the cohort.

    Urgent and deprogrammed requests keep individual proposals; a refresh only
    replaces them when none is left or one can no longer be confirmed."""
    requests = session.exec(select(SurgicalRequest).where(
        SurgicalRequest.status == RequestStatus.pending,
        or_(SurgicalRequest.urgent == True, deprogrammed_filter()),  # noqa: E712
    ).order_by(SurgicalRequest.created_at, SurgicalRequest.id)).all()
    stale = []
    for request in requests:
        open_ = session.exec(select(Proposal).where(
            Proposal.request_id == request.id, Proposal.status == ProposalStatus.proposed,
        )).all()
        if not open_ or any(service.check_still_feasible(session, p) for p in open_):
            stale.append(request.id)
    session.rollback()  # release the row locks taken by the checks
    offer_new_dates(session, stale, predictors, scheduler)
    return len(stale)


def deprogrammed(session: Session) -> list[dict]:
    """Pending requests that lost a booking, with the reason and their open dates A/B."""
    rows = session.exec(
        select(PlannedCase).join(SurgicalRequest, SurgicalRequest.id == PlannedCase.request_id)
        .where(PlannedCase.status == CaseStatus.cancelled,
               PlannedCase.cancel_reason != None,  # noqa: E711
               SurgicalRequest.status == RequestStatus.pending)
        .order_by(PlannedCase.admission_date, PlannedCase.id)
    ).all()
    latest: dict[UUID, PlannedCase] = {}
    for case in rows:
        if case.request_id not in latest or case.created_at > latest[case.request_id].created_at:
            latest[case.request_id] = case
    result = []
    for case in sorted(latest.values(), key=lambda c: (c.admission_date, str(c.id))):
        proposals = session.exec(select(Proposal).where(
            Proposal.request_id == case.request_id, Proposal.status == ProposalStatus.proposed,
        ).order_by(Proposal.rank)).all()
        patient = session.get(Patient, session.get(SurgicalRequest, case.request_id).patient_id)
        vacation = session.get(Vacation, case.vacation_id)
        result.append({"request_id": case.request_id, "case_id": case.id,
                       "former_date": case.admission_date, "reason": case.cancel_reason,
                       "proposals": proposals,
                       "patient": {"id": patient.id, "external_ref": patient.external_ref},
                       "room_name": session.get(OperatingRoom, vacation.room_id).name,
                       "start_time": vacation.start_time,
                       "planned_minutes": case.planned_minutes})
    return result
