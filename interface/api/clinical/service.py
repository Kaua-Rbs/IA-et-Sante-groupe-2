from math import ceil

from sqlmodel import Session

from api.ai.contracts import PredictionInput
from api.ai.providers import Predictors
from api.clinical.models import Patient, Prediction, SurgicalRequest
from api.config import settings
from api.resources.models import Specialty


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


def predict(session: Session, request: SurgicalRequest, predictors: Predictors) -> Prediction:
    """Run every predictor on the request and store the result."""
    inputs = prediction_input(session, request)
    room = predictors.room_duration.predict(inputs)
    los = predictors.los.predict(inputs)
    if room.unit != "minutes" or los.unit != "inclusive_calendar_days":
        raise ValueError("Predictor returned an unexpected unit")
    prediction = Prediction(
        request_id=request.id,
        room_minutes=room.value,
        room_minutes_low=room.interval[0] if room.interval else None,
        room_minutes_high=room.interval[1] if room.interval else None,
        los_days=ceil(los.value),
        los_days_low=los.interval[0] if los.interval else None,
        los_days_high=los.interval[1] if los.interval else None,
        care_type=predictors.care_type.predict(inputs),
        model_version=" / ".join(sorted({
            predictors.room_duration.model_version, predictors.los.model_version,
            predictors.care_type.model_version,
        })),
        source=settings.AI_BACKEND,
    )
    session.add(prediction)
    session.commit()
    session.refresh(prediction)
    return prediction

