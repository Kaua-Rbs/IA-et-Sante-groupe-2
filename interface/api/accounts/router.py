from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import delete, select

from api.accounts.models import (
    Group, GroupPublic, PasswordChange, RefreshToken, User, UserCreate, UserPublic,
    UserSelfUpdate, UserUpdate,
)
from api.accounts.security import (
    AdminUser, CurrentUser, authenticate_user, create_access_token, create_refresh_token,
    get_password_hash, revoke_user_refresh_tokens, verify_password, verify_refresh_token,
)
from api.config import limiter, settings
from api.db import SessionDep

router = APIRouter(prefix="/account", tags=["account"])


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


def _issue_tokens(session: SessionDep, user: User) -> Token:
    return Token(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(session, user.id),
    )


def _get_user_or_404(session: SessionDep, user_id: UUID) -> User:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# --- Authentication ---

@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request,
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    """OAuth2 password flow; `username` accepts the username or the email."""
    user = authenticate_user(session, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    if not user.validated:
        raise HTTPException(status_code=403, detail="Account pending validation")
    return _issue_tokens(session, user)


@router.post("/token/refresh")
@limiter.limit("10/minute")
async def refresh_access_token(
    request: Request, session: SessionDep, body: RefreshTokenRequest,
) -> Token:
    """Exchange a valid refresh token for a new access + refresh token pair (rotation)."""
    db_token = verify_refresh_token(session, body.refresh_token)
    if not db_token:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = session.get(User, db_token.user_id)
    if not user or user.disabled or not user.validated:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    db_token.revoked = True
    session.add(db_token)
    session.commit()
    return _issue_tokens(session, user)


@router.post("/logout")
async def logout(session: SessionDep, current_user: CurrentUser, body: RefreshTokenRequest):
    """Revoke the provided refresh token."""
    db_token = verify_refresh_token(session, body.refresh_token)
    if db_token and db_token.user_id == current_user.id:
        db_token.revoked = True
        session.add(db_token)
        session.commit()
    return {"detail": "Successfully logged out"}


@router.post("/change-password")
async def change_password(session: SessionDep, current_user: CurrentUser, body: PasswordChange):
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.hashed_password = get_password_hash(body.new_password)
    session.add(current_user)
    revoke_user_refresh_tokens(session, current_user.id)
    return {"detail": "Password changed successfully"}


# --- Users ---

@router.post("/users/create", response_model=UserPublic, status_code=201)
def create_user(user: UserCreate, session: SessionDep):
    """Public registration. With ACCOUNT_VALIDATION, an admin must validate the account."""
    db_user = User.model_validate(user, update={
        "hashed_password": get_password_hash(user.password),
        "validated": not settings.ACCOUNT_VALIDATION,
    })
    try:
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    return db_user


@router.get("/users/me", response_model=UserPublic)
def read_current_user(current_user: CurrentUser):
    return current_user


@router.patch("/users/me", response_model=UserPublic)
def update_current_user(body: UserSelfUpdate, session: SessionDep, current_user: CurrentUser):
    current_user.sqlmodel_update(body.model_dump(exclude_unset=True))
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return current_user


@router.get("/users/", response_model=list[UserPublic])
def read_users(
    session: SessionDep,
    current_user: AdminUser,
    offset: int = 0,
    limit: Annotated[int, Query(le=100)] = 100,
    validated: bool | None = None,
):
    """List users (admin). `validated=false` lists the accounts waiting for validation."""
    statement = select(User)
    if validated is not None:
        statement = statement.where(User.validated == validated)
    return session.exec(statement.offset(offset).limit(limit)).all()


@router.get("/users/{user_id}", response_model=UserPublic)
def read_user(user_id: UUID, session: SessionDep, current_user: AdminUser):
    return _get_user_or_404(session, user_id)


@router.patch("/users/{user_id}", response_model=UserPublic)
def update_user(user_id: UUID, user: UserUpdate, session: SessionDep, current_user: AdminUser):
    user_db = _get_user_or_404(session, user_id)
    user_db.sqlmodel_update(user.model_dump(exclude_unset=True))
    try:
        session.add(user_db)
        session.commit()
        session.refresh(user_db)
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Username or email already exists")
    return user_db


@router.post("/users/{user_id}/validate", response_model=UserPublic)
def validate_user(user_id: UUID, session: SessionDep, current_user: AdminUser):
    user = _get_user_or_404(session, user_id)
    user.validated = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(user_id: UUID, session: SessionDep, current_user: AdminUser):
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = _get_user_or_404(session, user_id)
    try:
        session.exec(delete(RefreshToken).where(RefreshToken.user_id == user_id))
        session.delete(user)
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="User is referenced by planning data; disable it instead",
        )
    return {"ok": True}


# --- Roles (fixed groups) ---

@router.get("/groups/", response_model=list[GroupPublic])
def read_groups(session: SessionDep, current_user: AdminUser):
    return session.exec(select(Group).order_by(Group.id)).all()


def _get_group_or_404(session: SessionDep, group_id: int) -> Group:
    group = session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.post("/users/{user_id}/groups/{group_id}", response_model=UserPublic)
def add_user_to_group(user_id: UUID, group_id: int, session: SessionDep, current_user: AdminUser):
    user = _get_user_or_404(session, user_id)
    group = _get_group_or_404(session, group_id)
    if group not in user.groups:
        user.groups.append(group)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@router.delete("/users/{user_id}/groups/{group_id}", response_model=UserPublic)
def remove_user_from_group(
    user_id: UUID, group_id: int, session: SessionDep, current_user: AdminUser,
):
    user = _get_user_or_404(session, user_id)
    group = _get_group_or_404(session, group_id)
    if user_id == current_user.id and group.name == "admin":
        raise HTTPException(status_code=400, detail="Cannot remove your own admin role")
    if group in user.groups:
        user.groups.remove(group)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
