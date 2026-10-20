from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, select

from api.ai.contracts import PredictionInput, reserved_stay_days
from api.ai.providers import Predictors
from api.clinical.models import Patient, Prediction, SurgicalRequest
from api.resources.models import Specialty


def supersede_proposals(session: Session, request_ids: Iterable[UUID]) -> None:
    """Invalidate dates and reset rejections when clinical inputs change."""
    from api.planning.models import Proposal, ProposalStatus
    ids = tuple(request_ids)
    if not ids:
        return
    for proposal in session.exec(select(Proposal).where(
        Proposal.request_id.in_(ids),
        Proposal.status.in_((ProposalStatus.proposed, ProposalStatus.rejected)),
    )).all():
        proposal.status = ProposalStatus.superseded
        session.add(proposal)


def prediction_input(session: Session, request: SurgicalRequest) -> PredictionInput:
    patient = session.get(Patient, request.patient_id)
    specialty = session.get(Specialty, request.specialty_id)
    return PredictionInput(
        age=request.earliest_date.year - patient.birth_year,
        sex=patient.sex,
        principal_diagnosis=request.principal_diagnosis,
        ccam_codes=tuple(request.ccam_codes),
        specialty=specialty.name,
        intervention_type=request.intervention_type,
    )


def build_prediction(session: Session, request: SurgicalRequest, predictors: Predictors) -> Prediction:
    """Build a prediction without committing, for single or cohort transactions."""
    inputs = prediction_input(session, request)
    room = predictors.room_duration.predict(inputs)
    los = predictors.los.predict(inputs)
    if room.unit != "minutes" or los.unit != "inclusive_calendar_days":
        raise ValueError("Predictor returned an unexpected unit")
    care_type = predictors.care_type.predict(inputs)
    prediction = Prediction(
        request_id=request.id,
        room_minutes=room.value,
        room_minutes_low=room.interval[0] if room.interval else None,
        room_minutes_high=room.interval[1] if room.interval else None,
        los_days=reserved_stay_days(los, care_type),
        los_days_low=los.interval[0] if los.interval else None,
        los_days_high=los.interval[1] if los.interval else None,
        care_type=care_type,
        model_version=" / ".join(sorted({
            predictors.room_duration.model_version, predictors.los.model_version,
            predictors.care_type.model_version,
        })),
        source=predictors.source,
    )
    return prediction


def predict(session: Session, request: SurgicalRequest, predictors: Predictors) -> Prediction:
    """Run every predictor on the request and store the result."""
    prediction = build_prediction(session, request, predictors)
    session.add(prediction)
    session.commit()
    session.refresh(prediction)
    return prediction
