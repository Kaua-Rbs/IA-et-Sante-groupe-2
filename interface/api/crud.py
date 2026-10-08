"""Small helpers shared by the CRUD routers."""

from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel

ModelT = TypeVar("ModelT", bound=SQLModel)


def get_or_404(session: Session, model: type[ModelT], obj_id: object) -> ModelT:
    obj = session.get(model, obj_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"{model.__name__} not found")
    return obj


def save(session: Session, obj: ModelT) -> ModelT:
    """Commit `obj`; unique or foreign-key violations become a 409."""
    try:
        session.add(obj)
        session.commit()
        session.refresh(obj)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Conflicts with existing data")
    return obj


def remove(session: Session, obj: SQLModel) -> dict:
    try:
        session.delete(obj)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Still referenced by other data")
    return {"ok": True}


def require_exists(session: Session, model: type[SQLModel], obj_id: object | None) -> None:
    """422 when an optional foreign key points to nothing (SQLite does not enforce them)."""
    if obj_id is not None and session.get(model, obj_id) is None:
        raise HTTPException(status_code=422, detail=f"Unknown {model.__name__} {obj_id}")
