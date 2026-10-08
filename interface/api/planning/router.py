import datetime as dt
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlmodel import select

from api.accounts.security import ClinicalUser, StaffUser
from api.ai.providers import PredictorsDep, SchedulerDep
from api.clinical.models import RequestStatus, SurgicalRequest
from api.crud import get_or_404, save
from api.db import SessionDep, utcnow
from api.planning import service
from api.planning.models import (
    CaseOutcome, CaseStatus, PlannedCase, PlannedCasePublic, Proposal, ProposalPublic,
    ProposalStatus,
)

router = APIRouter(tags=["planning"])

# --- Proposals ---

@router.post(
    "/requests/{request_id}/proposals", response_model=list[ProposalPublic], status_code=201,
)
def generate_proposals(
    request_id: UUID,
    session: SessionDep,
    current_user: ClinicalUser,
    predictors: PredictorsDep,
    scheduler: SchedulerDep,
):
    """Predict, then propose dates (best first). An empty list means no slot was found
    in the window, not that none exists: widen `latest_date` or add vacations."""
    request = get_or_404(session, SurgicalRequest, request_id)
    if request.status != RequestStatus.pending:
        raise HTTPException(status_code=409, detail=f"Request is {request.status.value}")
    return service.propose(session, request, predictors, scheduler)


@router.get("/requests/{request_id}/proposals", response_model=list[ProposalPublic])
def list_proposals(
    request_id: UUID,
    session: SessionDep,
    current_user: StaffUser,
    status: ProposalStatus | None = None,
):
    get_or_404(session, SurgicalRequest, request_id)
    statement = (
        select(Proposal).where(Proposal.request_id == request_id)
        .order_by(Proposal.created_at.desc(), Proposal.rank)
    )
    if status is not None:
        statement = statement.where(Proposal.status == status)
    return session.exec(statement).all()


def _get_open_proposal(session: SessionDep, proposal_id: UUID) -> Proposal:
    proposal = get_or_404(session, Proposal, proposal_id)
    if proposal.status != ProposalStatus.proposed:
        raise HTTPException(status_code=409, detail=f"Proposal is {proposal.status.value}")
    return proposal


@router.post("/proposals/{proposal_id}/accept", response_model=PlannedCasePublic, status_code=201)
def accept_proposal(proposal_id: UUID, session: SessionDep, current_user: ClinicalUser):
    """Human decision: book the slot. Capacity is checked again, since it may have
    been taken after the proposal was made."""
    proposal = _get_open_proposal(session, proposal_id)
    problems = service.check_still_feasible(session, proposal)
    if problems:
        raise HTTPException(status_code=409, detail={
            "message": "Proposal is no longer feasible; generate new proposals",
            "reasons": problems,
        })
    return service.accept(session, proposal, current_user)


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalPublic)
def reject_proposal(proposal_id: UUID, session: SessionDep, current_user: ClinicalUser):
    proposal = _get_open_proposal(session, proposal_id)
    proposal.status = ProposalStatus.rejected
    proposal.decided_by = current_user.id
    proposal.decided_at = utcnow()
    return save(session, proposal)


# --- Planned cases ---

@router.get("/cases", response_model=list[PlannedCasePublic])
def list_cases(
    session: SessionDep,
    current_user: StaffUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
    vacation_id: int | None = None,
    request_id: UUID | None = None,
    status: CaseStatus | None = None,
):
    """Cases whose stay overlaps [`start`, `end`]."""
    statement = select(PlannedCase).order_by(PlannedCase.admission_date)
    if start is not None:
        statement = statement.where(PlannedCase.discharge_date >= start)
    if end is not None:
        statement = statement.where(PlannedCase.admission_date <= end)
    if vacation_id is not None:
        statement = statement.where(PlannedCase.vacation_id == vacation_id)
    if request_id is not None:
        statement = statement.where(PlannedCase.request_id == request_id)
    if status is not None:
        statement = statement.where(PlannedCase.status == status)
    return session.exec(statement).all()


@router.get("/cases/{case_id}", response_model=PlannedCasePublic)
def read_case(case_id: UUID, session: SessionDep, current_user: StaffUser):
    return get_or_404(session, PlannedCase, case_id)


def _get_planned_case(session: SessionDep, case_id: UUID) -> PlannedCase:
    case = get_or_404(session, PlannedCase, case_id)
    if case.status != CaseStatus.planned:
        raise HTTPException(status_code=409, detail=f"Case is {case.status.value}")
    return case


@router.post("/cases/{case_id}/cancel", response_model=PlannedCasePublic)
def cancel_case(case_id: UUID, session: SessionDep, current_user: ClinicalUser):
    """Free the slot and the bed; the request goes back to pending to be rescheduled."""
    case = _get_planned_case(session, case_id)
    request = session.get(SurgicalRequest, case.request_id)
    case.status = CaseStatus.cancelled
    request.status = RequestStatus.pending
    session.add(request)
    return save(session, case)


@router.post("/cases/{case_id}/outcome", response_model=PlannedCasePublic)
def record_outcome(
    case_id: UUID, body: CaseOutcome, session: SessionDep, current_user: StaffUser,
):
    """Record the observed room time and stay; feeds the evaluation of the models."""
    case = _get_planned_case(session, case_id)
    request = session.get(SurgicalRequest, case.request_id)
    case.sqlmodel_update(body.model_dump())
    case.status = CaseStatus.done
    request.status = RequestStatus.done
    session.add(request)
    return save(session, case)
