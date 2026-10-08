"""Patients, surgical requests and the predictions attached to them."""

import datetime as dt
from enum import Enum
from uuid import UUID, uuid4

from pydantic import NaiveDatetime, model_validator
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from api.db import utcnow
from api.resources.models import CareType


# --- Patient ---

class PatientBase(SQLModel):
    """Pseudonymised patient: no name, no birth date, only what the predictions need."""

    external_ref: str | None = Field(
        default=None, index=True, unique=True, max_length=64,
        description="Pseudonymous identifier from the hospital information system",
    )
    birth_year: int = Field(ge=1900, le=2100)
    sex: int = Field(ge=1, le=2, description="1 = male, 2 = female")


class Patient(PatientBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class PatientCreate(PatientBase):
    @model_validator(mode="after")
    def check_birth_year(self):
        if self.birth_year > dt.date.today().year:
            raise ValueError("Birth year cannot be in the future")
        return self


class PatientUpdate(SQLModel):
    external_ref: str | None = Field(default=None, max_length=64)
    birth_year: int | None = Field(default=None, ge=1900, le=2100)
    sex: int | None = Field(default=None, ge=1, le=2)


class PatientPublic(PatientBase):
    id: UUID
    created_at: NaiveDatetime


# --- Surgical request ---

class RequestStatus(str, Enum):
    pending = "pending"  # waiting for a date
    scheduled = "scheduled"  # a proposal was accepted
    done = "done"
    cancelled = "cancelled"


class SurgicalRequestBase(SQLModel):
    """An intervention to schedule, as described at the preparatory consultation."""

    patient_id: UUID = Field(foreign_key="patient.id", index=True)
    surgeon_id: int = Field(foreign_key="surgeon.id", index=True)
    principal_diagnosis: str = Field(min_length=1, max_length=16, description="CIM-10 code")
    ccam_codes: list[str] = Field(
        min_length=1, max_length=4, sa_column=Column(JSON, nullable=False),
        description="Planned CCAM procedure codes",
    )
    intervention_type: str | None = Field(default=None, max_length=100)
    earliest_date: dt.date = Field(description="No admission before this date")
    latest_date: dt.date | None = Field(default=None, description="Wished deadline")


class SurgicalRequest(SurgicalRequestBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    # Copied from the surgeon at creation; vacations are matched on it
    specialty_id: int = Field(foreign_key="specialty.id", index=True)
    status: RequestStatus = Field(default=RequestStatus.pending, index=True)
    created_by: UUID = Field(foreign_key="user.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class SurgicalRequestCreate(SurgicalRequestBase):
    @model_validator(mode="after")
    def check_window(self):
        if self.latest_date is not None and self.latest_date < self.earliest_date:
            raise ValueError("latest_date cannot be before earliest_date")
        return self


class SurgicalRequestUpdate(SQLModel):
    principal_diagnosis: str | None = Field(default=None, min_length=1, max_length=16)
    ccam_codes: list[str] | None = Field(default=None, min_length=1, max_length=4)
    intervention_type: str | None = Field(default=None, max_length=100)
    earliest_date: dt.date | None = None
    latest_date: dt.date | None = None


class SurgicalRequestPublic(SurgicalRequestBase):
    id: UUID
    specialty_id: int
    status: RequestStatus
    created_by: UUID
    created_at: NaiveDatetime


# --- Prediction ---

class PredictionBase(SQLModel):
    room_minutes: float = Field(description="Room entry-to-exit minutes, excluding turnover")
    room_minutes_low: float | None = None
    room_minutes_high: float | None = None
    los_days: int = Field(description="Total stay in inclusive calendar days (ambulatory = 1)")
    los_days_low: float | None = None
    los_days_high: float | None = None
    care_type: CareType
    model_version: str
    source: str = Field(description="Implementation that produced it, e.g. 'fixtures'")


class Prediction(PredictionBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    request_id: UUID = Field(foreign_key="surgicalrequest.id", index=True)
    created_at: NaiveDatetime = Field(default_factory=utcnow)


class PredictionPublic(PredictionBase):
    id: UUID
    request_id: UUID
    created_at: NaiveDatetime
