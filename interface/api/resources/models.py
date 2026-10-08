"""Hospital resources: specialties, operating rooms, vacations, bed units and surgeons."""

import datetime as dt
from enum import Enum
from uuid import UUID

from pydantic import model_validator
from sqlmodel import Field, SQLModel, UniqueConstraint


class CareType(str, Enum):
    """Kind of accommodation a stay needs."""

    ambulatory = "ambulatory"  # same-day discharge, ambulatory places
    conventional = "conventional"  # at least one night, inpatient beds


# --- Specialty ---

class SpecialtyBase(SQLModel):
    name: str = Field(index=True, unique=True, min_length=1, max_length=100)


class Specialty(SpecialtyBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class SpecialtyCreate(SpecialtyBase):
    pass


class SpecialtyUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)


class SpecialtyPublic(SpecialtyBase):
    id: int


# --- Operating room ---

class OperatingRoomBase(SQLModel):
    name: str = Field(index=True, unique=True, min_length=1, max_length=100)
    # Specialty usually operated in this room; each vacation sets its own specialty
    default_specialty_id: int | None = Field(default=None, foreign_key="specialty.id")
    active: bool = True


class OperatingRoom(OperatingRoomBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class OperatingRoomCreate(OperatingRoomBase):
    pass


class OperatingRoomUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    default_specialty_id: int | None = None
    active: bool | None = None


class OperatingRoomPublic(OperatingRoomBase):
    id: int


# --- Bed unit ---

class BedUnitBase(SQLModel):
    name: str = Field(index=True, unique=True, min_length=1, max_length=100)
    care_type: CareType
    capacity: int = Field(gt=0, description="Beds (conventional) or places (ambulatory)")
    active: bool = True


class BedUnit(BedUnitBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class BedUnitCreate(BedUnitBase):
    pass


class BedUnitUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    care_type: CareType | None = None
    capacity: int | None = Field(default=None, gt=0)
    active: bool | None = None


class BedUnitPublic(BedUnitBase):
    id: int


# --- Surgeon ---

class SurgeonBase(SQLModel):
    # Display name or pseudonymous code; staff data is personal data too
    name: str = Field(min_length=1, max_length=100)
    specialty_id: int = Field(foreign_key="specialty.id")
    user_id: UUID | None = Field(default=None, foreign_key="user.id", unique=True)


class Surgeon(SurgeonBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class SurgeonCreate(SurgeonBase):
    pass


class SurgeonUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    specialty_id: int | None = None
    user_id: UUID | None = None


class SurgeonPublic(SurgeonBase):
    id: int


# --- Vacation (operating-room session) ---

class VacationBase(SQLModel):
    """A time slot of one room given to one specialty (and optionally one surgeon)."""

    room_id: int = Field(foreign_key="operatingroom.id", index=True)
    specialty_id: int = Field(foreign_key="specialty.id", index=True)
    surgeon_id: int | None = Field(default=None, foreign_key="surgeon.id", index=True)
    date: dt.date = Field(index=True)
    start_time: dt.time
    duration_min: int = Field(default=240, gt=0, le=24 * 60)

    @model_validator(mode="after")
    def check_same_day(self):
        if self.start_time is not None and self.duration_min is not None:
            start = dt.datetime.combine(dt.date.min, self.start_time)
            if (start + dt.timedelta(minutes=self.duration_min)).date() != dt.date.min:
                raise ValueError("A vacation must end on the day it starts")
        return self

    @property
    def end_time(self) -> dt.time:
        start = dt.datetime.combine(self.date, self.start_time)
        return (start + dt.timedelta(minutes=self.duration_min)).time()


class Vacation(VacationBase, table=True):
    __table_args__ = (UniqueConstraint("room_id", "date", "start_time"),)
    id: int | None = Field(default=None, primary_key=True)


class VacationCreate(VacationBase):
    pass


class VacationUpdate(SQLModel):
    room_id: int | None = None
    specialty_id: int | None = None
    surgeon_id: int | None = None
    date: dt.date | None = None
    start_time: dt.time | None = None
    duration_min: int | None = Field(default=None, gt=0, le=24 * 60)


class VacationPublic(VacationBase):
    id: int
