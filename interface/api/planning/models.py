"""Date proposals and the planned cases they become once a human accepts them."""

import datetime as dt
from enum import Enum
from uuid import UUID, uuid4

from pydantic import NaiveDatetime, field_validator
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
    # Urgent requests only: planned cases postponed if this proposal is accepted
    displaced_case_ids: list[str] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=True),
    )

    @field_validator("displaced_case_ids", mode="before")
    @classmethod
    def none_as_empty(cls, value):
        # Rows written before the column existed hold NULL
        return value or []


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
    # Why the case was deprogrammed (disruption, emergency, move); None for a plain cancellation
    cancel_reason: str | None = Field(default=None, max_length=300)


class PlannedCasePublic(PlannedCaseBase):
    id: UUID
    status: CaseStatus
    actual_room_minutes: int | None
    actual_los_days: int | None
    created_at: NaiveDatetime
    cancel_reason: str | None


class CaseOutcome(SQLModel):
    """What really happened, recorded after the stay."""

    actual_room_minutes: int = Field(gt=0, le=24 * 60)
    actual_los_days: int = Field(gt=0)


class ReplanRun(SQLModel, table=True):
    """Durable history of proposal refreshes; never stores clinical inputs."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    status: str = Field(default="running", index=True)
    method: str
    start: dt.date
    end: dt.date
    event_count: int = 0
    proposals_count: int = 0
    failure_type: str | None = None
    started_at: NaiveDatetime = Field(default_factory=utcnow)
    finished_at: NaiveDatetime | None = None


class PlanningChange(SQLModel, table=True):
    """A committed change needing a fresh view of the pending workload."""

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    kind: str = Field(max_length=64)
    actor_id: UUID | None = Field(default=None, foreign_key="user.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow, index=True)
    run_id: UUID | None = Field(default=None, foreign_key="replanrun.id", index=True)
