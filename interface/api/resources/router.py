import datetime as dt

from fastapi import APIRouter, HTTPException
from sqlmodel import Session, select

from api.accounts.models import User
from api.accounts.security import CurrentUser, PlannerUser
from api.crud import get_or_404, remove, require_exists, save
from api.db import SessionDep
from api.resources.models import (
    BedUnit, BedUnitCreate, BedUnitPublic, BedUnitUpdate,
    OperatingRoom, OperatingRoomCreate, OperatingRoomPublic, OperatingRoomUpdate,
    Specialty, SpecialtyCreate, SpecialtyPublic, SpecialtyUpdate,
    Surgeon, SurgeonCreate, SurgeonPublic, SurgeonUpdate,
    Vacation, VacationCreate, VacationPublic, VacationUpdate,
)

router = APIRouter(tags=["resources"])


# --- Specialties ---

@router.get("/specialties", response_model=list[SpecialtyPublic])
def list_specialties(session: SessionDep, current_user: CurrentUser):
    return session.exec(select(Specialty).order_by(Specialty.name)).all()


@router.post("/specialties", response_model=SpecialtyPublic, status_code=201)
def create_specialty(body: SpecialtyCreate, session: SessionDep, current_user: PlannerUser):
    return save(session, Specialty.model_validate(body))


@router.patch("/specialties/{specialty_id}", response_model=SpecialtyPublic)
def update_specialty(
    specialty_id: int, body: SpecialtyUpdate, session: SessionDep, current_user: PlannerUser,
):
    specialty = get_or_404(session, Specialty, specialty_id)
    specialty.sqlmodel_update(body.model_dump(exclude_unset=True))
    return save(session, specialty)


@router.delete("/specialties/{specialty_id}")
def delete_specialty(specialty_id: int, session: SessionDep, current_user: PlannerUser):
    return remove(session, get_or_404(session, Specialty, specialty_id))


# --- Operating rooms ---

@router.get("/rooms", response_model=list[OperatingRoomPublic])
def list_rooms(session: SessionDep, current_user: CurrentUser, active: bool | None = None):
    statement = select(OperatingRoom).order_by(OperatingRoom.name)
    if active is not None:
        statement = statement.where(OperatingRoom.active == active)
    return session.exec(statement).all()


@router.post("/rooms", response_model=OperatingRoomPublic, status_code=201)
def create_room(body: OperatingRoomCreate, session: SessionDep, current_user: PlannerUser):
    require_exists(session, Specialty, body.default_specialty_id)
    return save(session, OperatingRoom.model_validate(body))


@router.patch("/rooms/{room_id}", response_model=OperatingRoomPublic)
def update_room(
    room_id: int, body: OperatingRoomUpdate, session: SessionDep, current_user: PlannerUser,
):
    room = get_or_404(session, OperatingRoom, room_id)
    require_exists(session, Specialty, body.default_specialty_id)
    room.sqlmodel_update(body.model_dump(exclude_unset=True))
    return save(session, room)


@router.delete("/rooms/{room_id}")
def delete_room(room_id: int, session: SessionDep, current_user: PlannerUser):
    """Delete a room without history; deactivate it (`active=false`) otherwise."""
    return remove(session, get_or_404(session, OperatingRoom, room_id))


# --- Bed units ---

@router.get("/bed-units", response_model=list[BedUnitPublic])
def list_bed_units(session: SessionDep, current_user: CurrentUser):
    return session.exec(select(BedUnit).order_by(BedUnit.name)).all()


@router.post("/bed-units", response_model=BedUnitPublic, status_code=201)
def create_bed_unit(body: BedUnitCreate, session: SessionDep, current_user: PlannerUser):
    return save(session, BedUnit.model_validate(body))


@router.patch("/bed-units/{unit_id}", response_model=BedUnitPublic)
def update_bed_unit(
    unit_id: int, body: BedUnitUpdate, session: SessionDep, current_user: PlannerUser,
):
    unit = get_or_404(session, BedUnit, unit_id)
    unit.sqlmodel_update(body.model_dump(exclude_unset=True))
    return save(session, unit)


@router.delete("/bed-units/{unit_id}")
def delete_bed_unit(unit_id: int, session: SessionDep, current_user: PlannerUser):
    return remove(session, get_or_404(session, BedUnit, unit_id))


# --- Surgeons ---

@router.get("/surgeons", response_model=list[SurgeonPublic])
def list_surgeons(
    session: SessionDep, current_user: CurrentUser, specialty_id: int | None = None,
):
    statement = select(Surgeon).order_by(Surgeon.name)
    if specialty_id is not None:
        statement = statement.where(Surgeon.specialty_id == specialty_id)
    return session.exec(statement).all()


@router.get("/surgeons/{surgeon_id}", response_model=SurgeonPublic)
def read_surgeon(surgeon_id: int, session: SessionDep, current_user: CurrentUser):
    return get_or_404(session, Surgeon, surgeon_id)


@router.post("/surgeons", response_model=SurgeonPublic, status_code=201)
def create_surgeon(body: SurgeonCreate, session: SessionDep, current_user: PlannerUser):
    require_exists(session, Specialty, body.specialty_id)
    require_exists(session, User, body.user_id)
    return save(session, Surgeon.model_validate(body))


@router.patch("/surgeons/{surgeon_id}", response_model=SurgeonPublic)
def update_surgeon(
    surgeon_id: int, body: SurgeonUpdate, session: SessionDep, current_user: PlannerUser,
):
    surgeon = get_or_404(session, Surgeon, surgeon_id)
    require_exists(session, Specialty, body.specialty_id)
    require_exists(session, User, body.user_id)
    surgeon.sqlmodel_update(body.model_dump(exclude_unset=True))
    return save(session, surgeon)


@router.delete("/surgeons/{surgeon_id}")
def delete_surgeon(surgeon_id: int, session: SessionDep, current_user: PlannerUser):
    return remove(session, get_or_404(session, Surgeon, surgeon_id))


# --- Vacations ---

def _minutes(t: dt.time) -> int:
    return t.hour * 60 + t.minute


def _check_vacation(session: Session, vacation: VacationCreate, exclude_id: int | None = None):
    require_exists(session, OperatingRoom, vacation.room_id)
    require_exists(session, Specialty, vacation.specialty_id)
    require_exists(session, Surgeon, vacation.surgeon_id)
    start = _minutes(vacation.start_time)
    end = start + vacation.duration_min
    same_day = session.exec(select(Vacation).where(
        Vacation.room_id == vacation.room_id, Vacation.date == vacation.date,
    )).all()
    for other in same_day:
        other_start = _minutes(other.start_time)
        if other.id != exclude_id and start < other_start + other.duration_min and other_start < end:
            raise HTTPException(status_code=409, detail=f"Overlaps vacation {other.id} in this room")


@router.get("/vacations", response_model=list[VacationPublic])
def list_vacations(
    session: SessionDep,
    current_user: CurrentUser,
    start: dt.date | None = None,
    end: dt.date | None = None,
    room_id: int | None = None,
    specialty_id: int | None = None,
    surgeon_id: int | None = None,
):
    """Vacations between `start` and `end` (inclusive), optionally filtered."""
    statement = select(Vacation).order_by(Vacation.date, Vacation.start_time, Vacation.room_id)
    if start is not None:
        statement = statement.where(Vacation.date >= start)
    if end is not None:
        statement = statement.where(Vacation.date <= end)
    if room_id is not None:
        statement = statement.where(Vacation.room_id == room_id)
    if specialty_id is not None:
        statement = statement.where(Vacation.specialty_id == specialty_id)
    if surgeon_id is not None:
        statement = statement.where(Vacation.surgeon_id == surgeon_id)
    return session.exec(statement).all()


@router.get("/vacations/{vacation_id}", response_model=VacationPublic)
def read_vacation(vacation_id: int, session: SessionDep, current_user: CurrentUser):
    return get_or_404(session, Vacation, vacation_id)


@router.post("/vacations", response_model=VacationPublic, status_code=201)
def create_vacation(body: VacationCreate, session: SessionDep, current_user: PlannerUser):
    _check_vacation(session, body)
    return save(session, Vacation.model_validate(body))


@router.patch("/vacations/{vacation_id}", response_model=VacationPublic)
def update_vacation(
    vacation_id: int, body: VacationUpdate, session: SessionDep, current_user: PlannerUser,
):
    vacation = get_or_404(session, Vacation, vacation_id)
    merged = VacationCreate.model_validate(
        vacation.model_dump() | body.model_dump(exclude_unset=True)
    )
    _check_vacation(session, merged, exclude_id=vacation_id)
    vacation.sqlmodel_update(merged.model_dump())
    return save(session, vacation)


@router.delete("/vacations/{vacation_id}")
def delete_vacation(vacation_id: int, session: SessionDep, current_user: PlannerUser):
    return remove(session, get_or_404(session, Vacation, vacation_id))
