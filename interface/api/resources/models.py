"""Hospital resources: specialties, operating rooms, vacations, bed units and surgeons."""

import datetime as dt
from enum import Enum
from uuid import UUID

from pydantic import model_validator
from sqlalchemy import true
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
    # A deleted vacation that cases or proposals still reference is kept, inactive
    active: bool = Field(default=True, index=True, sa_column_kwargs={"server_default": true()})


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
    active: bool


# --- Unavailability (room closure or surgeon absence) ---

class UnavailabilityBase(SQLModel):
    """A room closed or a surgeon absent, whole days or one time window each day."""

    room_id: int | None = Field(default=None, foreign_key="operatingroom.id", index=True)
    surgeon_id: int | None = Field(default=None, foreign_key="surgeon.id", index=True)
    start_date: dt.date = Field(index=True)
    end_date: dt.date = Field(index=True, description="Last day concerned (inclusive)")
    # Both empty: the whole day; otherwise the same window on every day of the period
    start_time: dt.time | None = None
    end_time: dt.time | None = None
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def check_target_and_period(self):
        if (self.room_id is None) == (self.surgeon_id is None):
            raise ValueError("Give either a room or a surgeon")
        if self.end_date < self.start_date:
            raise ValueError("end_date cannot be before start_date")
        if (self.start_time is None) != (self.end_time is None):
            raise ValueError("Give both start_time and end_time, or neither")
        if self.start_time is not None and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self

    def overlap(self, vacation: "VacationBase") -> tuple[int, int] | None:
        """Minutes of the day [start, end) the vacation loses to it, or None."""
        if not self.start_date <= vacation.date <= self.end_date:
            return None
        start = vacation.start_time.hour * 60 + vacation.start_time.minute
        end = start + vacation.duration_min
        if self.start_time is not None:
            start = max(start, self.start_time.hour * 60 + self.start_time.minute)
            end = min(end, self.end_time.hour * 60 + self.end_time.minute)
        return (start, end) if start < end else None

    def describe(self) -> str:
        days = (f"le {self.start_date:%d/%m}" if self.start_date == self.end_date
                else f"du {self.start_date:%d/%m} au {self.end_date:%d/%m}")
        hours = (f" de {self.start_time:%Hh%M} à {self.end_time:%Hh%M}"
                 if self.start_time is not None else "")
        return f"{days}{hours}"


class Unavailability(UnavailabilityBase, table=True):
    id: int | None = Field(default=None, primary_key=True)


class UnavailabilityCreate(UnavailabilityBase):
    pass


class UnavailabilityPublic(UnavailabilityBase):
    id: int
