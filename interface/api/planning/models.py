"""Date proposals and the planned cases they become once a human accepts them."""

import datetime as dt
from enum import Enum
from uuid import UUID, uuid4

from pydantic import NaiveDatetime
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from api.db import utcnow


class ProposalStatus(str, Enum):
    proposed = "proposed"
    accepted = "accepted"
    rejected = "rejected"
    superseded = "superseded"  # replaced by a newer run or by the acceptance of another one


class ProposalBase(SQLModel):
    request_id: UUID = Field(foreign_key="surgicalrequest.id", index=True)
    rank: int = Field(description="1 = best (date A), 2 = alternative (date B)...")
    vacation_id: int = Field(foreign_key="vacation.id")
    bed_unit_id: int = Field(foreign_key="bedunit.id")
    admission_date: dt.date
    discharge_date: dt.date = Field(description="Expected, last day of the stay (inclusive)")
    planned_minutes: int
    score: float
    reasons: list[str] = Field(sa_column=Column(JSON, nullable=False))
    scheduler: str = Field(description="Implementation that produced it")


class Proposal(ProposalBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    prediction_id: UUID = Field(foreign_key="prediction.id")
    status: ProposalStatus = Field(default=ProposalStatus.proposed, index=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    decided_by: UUID | None = Field(default=None, foreign_key="user.id")
    decided_at: NaiveDatetime | None = None


class ProposalPublic(ProposalBase):
    id: UUID
    prediction_id: UUID
    status: ProposalStatus
    created_at: NaiveDatetime
    decided_by: UUID | None
    decided_at: NaiveDatetime | None


class CaseStatus(str, Enum):
    planned = "planned"
    done = "done"
    cancelled = "cancelled"


class PlannedCaseBase(SQLModel):
    request_id: UUID = Field(foreign_key="surgicalrequest.id", index=True)
    proposal_id: UUID = Field(foreign_key="proposal.id")
    vacation_id: int = Field(foreign_key="vacation.id", index=True)
    bed_unit_id: int = Field(foreign_key="bedunit.id", index=True)
    admission_date: dt.date = Field(index=True)
    discharge_date: dt.date = Field(index=True)
    planned_minutes: int


class PlannedCase(PlannedCaseBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: CaseStatus = Field(default=CaseStatus.planned, index=True)
    # Observed values, fed back to evaluate and retrain the models
    actual_room_minutes: int | None = Field(default=None, gt=0)
    actual_los_days: int | None = Field(default=None, gt=0)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class PlannedCasePublic(PlannedCaseBase):
    id: UUID
    status: CaseStatus
    actual_room_minutes: int | None
    actual_los_days: int | None
    created_at: NaiveDatetime


class CaseOutcome(SQLModel):
    """What really happened, recorded after the stay."""

    actual_room_minutes: int = Field(gt=0, le=24 * 60)
    actual_los_days: int = Field(gt=0)
