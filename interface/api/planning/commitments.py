"""Report resource conflicts in confirmed bookings without moving them."""

import datetime as dt

from sqlmodel import Session, select

from api.clinical.models import Prediction, SurgicalRequest
from api.config import settings
from api.planning.capacity import bed_occupancy, stay_days, used_minutes
from api.planning.models import CaseStatus, PlannedCase, Proposal
from api.resources.models import BedUnit, OperatingRoom, Vacation


def confirmed_conflicts(session: Session, start: dt.date, end: dt.date) -> list[dict]:
    if end < start or (end - start).days > 60:
        raise ValueError("Choose a window of at most 60 days")
    rows = session.exec(
        select(PlannedCase, SurgicalRequest, Vacation, OperatingRoom, BedUnit, Prediction)
        .select_from(PlannedCase)
        .join(SurgicalRequest, SurgicalRequest.id == PlannedCase.request_id)
        # The prediction accepted with the booking fixes the care type it needs
        .join(Proposal, Proposal.id == PlannedCase.proposal_id)
        .join(Prediction, Prediction.id == Proposal.prediction_id)
        .join(Vacation, Vacation.id == PlannedCase.vacation_id)
        .join(OperatingRoom, OperatingRoom.id == Vacation.room_id)
        .join(BedUnit, BedUnit.id == PlannedCase.bed_unit_id)
        .where(PlannedCase.status == CaseStatus.planned,
               PlannedCase.admission_date <= end, PlannedCase.discharge_date >= start)
        .order_by(PlannedCase.admission_date, PlannedCase.id)
    ).all()
    if not rows:
        return []
    used = used_minutes(session, (vacation.id for _, _, vacation, _, _, _ in rows))
    occupancy = bed_occupancy(session, start, max(case.discharge_date for case, *_ in rows))
    conflicts = []
    for case, request, vacation, room, unit, prediction in rows:
        reasons = []
        if case.admission_date >= start:
            if not room.active:
                reasons.append("La salle a été désactivée.")
            if (vacation.date != case.admission_date
                    or vacation.specialty_id != request.specialty_id
                    or vacation.surgeon_id not in (None, request.surgeon_id)):
                reasons.append("La vacation ne correspond plus à l'intervention confirmée.")
            if used.get(vacation.id, 0) > vacation.duration_min * (1 - settings.EMERGENCY_MARGIN):
                reasons.append("La vacation dépasse sa capacité disponible.")
        if not unit.active:
            reasons.append("L'unité de lits a été désactivée.")
        if unit.care_type != prediction.care_type:
            reasons.append("Le type d'hébergement de l'unité ne correspond plus au séjour confirmé.")
        load = occupancy.get(unit.id, {})
        if any(load.get(day, 0) > unit.capacity
               for day in stay_days(max(start, case.admission_date), case.discharge_date)):
            reasons.append("La capacité de lits est dépassée pendant le séjour.")
        if reasons:
            conflicts.append({"case_id": case.id, "request_id": case.request_id,
                              "admission_date": case.admission_date, "reasons": reasons})
    return conflicts
