from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlmodel import desc, select

from api.accounts.security import ClinicalUser, StaffUser
from api.ai.providers import PredictorsDep
from api.clinical import service
from api.clinical.models import (
    Patient, PatientCreate, PatientPublic, PatientUpdate, Prediction, PredictionPublic,
    RequestStatus, SurgicalRequest, SurgicalRequestCreate, SurgicalRequestPublic,
    SurgicalRequestUpdate,
)
from api.crud import get_or_404, remove, require_exists, save
from api.db import SessionDep
from api.resources.models import Surgeon

router = APIRouter(tags=["clinical"])

# --- Patients ---

@router.get("/patients", response_model=list[PatientPublic])
def list_patients(
    session: SessionDep,
    current_user: StaffUser,
    external_ref: str | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    statement = select(Patient).order_by(desc(Patient.created_at))
    if external_ref is not None:
        statement = statement.where(Patient.external_ref == external_ref)
    return session.exec(statement.offset(offset).limit(limit)).all()


@router.get("/patients/{patient_id}", response_model=PatientPublic)
def read_patient(patient_id: UUID, session: SessionDep, current_user: StaffUser):
    return get_or_404(session, Patient, patient_id)


@router.post("/patients", response_model=PatientPublic, status_code=201)
def create_patient(body: PatientCreate, session: SessionDep, current_user: ClinicalUser):
    return save(session, Patient.model_validate(body))


@router.patch("/patients/{patient_id}", response_model=PatientPublic)
def update_patient(
    patient_id: UUID, body: PatientUpdate, session: SessionDep, current_user: ClinicalUser,
):
    patient = get_or_404(session, Patient, patient_id)
    patient.sqlmodel_update(body.model_dump(exclude_unset=True))
    return save(session, patient)


@router.delete("/patients/{patient_id}")
def delete_patient(patient_id: UUID, session: SessionDep, current_user: ClinicalUser):
    return remove(session, get_or_404(session, Patient, patient_id))


# --- Surgical requests ---

@router.get("/requests", response_model=list[SurgicalRequestPublic])
def list_requests(
    session: SessionDep,
    current_user: StaffUser,
    status: RequestStatus | None = None,
    surgeon_id: int | None = None,
    patient_id: UUID | None = None,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
):
    statement = select(SurgicalRequest).order_by(desc(SurgicalRequest.created_at))
    if status is not None:
        statement = statement.where(SurgicalRequest.status == status)
    if surgeon_id is not None:
        statement = statement.where(SurgicalRequest.surgeon_id == surgeon_id)
    if patient_id is not None:
        statement = statement.where(SurgicalRequest.patient_id == patient_id)
    return session.exec(statement.offset(offset).limit(limit)).all()


@router.get("/requests/{request_id}", response_model=SurgicalRequestPublic)
def read_request(request_id: UUID, session: SessionDep, current_user: StaffUser):
    return get_or_404(session, SurgicalRequest, request_id)


@router.post("/requests", response_model=SurgicalRequestPublic, status_code=201)
def create_request(body: SurgicalRequestCreate, session: SessionDep, current_user: ClinicalUser):
    require_exists(session, Patient, body.patient_id)
    surgeon = session.get(Surgeon, body.surgeon_id)
    if surgeon is None:
        raise HTTPException(status_code=422, detail=f"Unknown Surgeon {body.surgeon_id}")
    request = SurgicalRequest.model_validate(body, update={
        "specialty_id": surgeon.specialty_id,
        "created_by": current_user.id,
    })
    return save(session, request)


def _get_pending(session: SessionDep, request_id: UUID) -> SurgicalRequest:
    request = get_or_404(session, SurgicalRequest, request_id)
    if request.status != RequestStatus.pending:
        raise HTTPException(status_code=409, detail=f"Request is {request.status.value}")
    return request


@router.patch("/requests/{request_id}", response_model=SurgicalRequestPublic)
def update_request(
    request_id: UUID, body: SurgicalRequestUpdate, session: SessionDep, current_user: ClinicalUser,
):
    """Only pending requests can change; their predictions and proposals must then be redone."""
    request = _get_pending(session, request_id)
    merged = SurgicalRequestCreate.model_validate(
        request.model_dump() | body.model_dump(exclude_unset=True)
    )
    request.sqlmodel_update(merged.model_dump())
    return save(session, request)


@router.post("/requests/{request_id}/cancel", response_model=SurgicalRequestPublic)
def cancel_request(request_id: UUID, session: SessionDep, current_user: ClinicalUser):
    """Cancel a pending request. A scheduled one is cancelled through its case."""
    request = _get_pending(session, request_id)
    request.status = RequestStatus.cancelled
    return save(session, request)


# --- Predictions ---

@router.get("/requests/{request_id}/predictions", response_model=list[PredictionPublic])
def list_predictions(request_id: UUID, session: SessionDep, current_user: StaffUser):
    get_or_404(session, SurgicalRequest, request_id)
    statement = (
        select(Prediction).where(Prediction.request_id == request_id)
        .order_by(desc(Prediction.created_at))
    )
    return session.exec(statement).all()


@router.post("/requests/{request_id}/predictions", response_model=PredictionPublic, status_code=201)
def run_prediction(
    request_id: UUID, session: SessionDep, current_user: ClinicalUser, predictors: PredictorsDep,
):
    """Predict room time, length of stay and care type for the request."""
    request = get_or_404(session, SurgicalRequest, request_id)
    return service.predict(session, request, predictors)
