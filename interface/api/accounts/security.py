import hashlib
import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pwdlib import PasswordHash
from sqlmodel import Session, or_, select

from api.accounts.models import RefreshToken, Role, User
from api.config import settings
from api.db import SessionDep, utcnow

ISSUER = "kyst-api"
AUDIENCE = "kyst-app"

password_hash = PasswordHash.recommended()
DUMMY_HASH = password_hash.hash("dummy-constant-value-for-timing-attack-prevention")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="account/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hash.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


# --- User lookup ---

def get_user(session: Session, login: str) -> User | None:
    """Find a user by username or email (the frontend logs in with the email)."""
    statement = select(User).where(or_(User.username == login, User.email == login))
    return session.exec(statement).first()


def authenticate_user(session: Session, login: str, password: str) -> User | None:
    user = get_user(session, login)
    if not user:
        # Constant time: always run a hash verification to prevent user enumeration
        verify_password(password, DUMMY_HASH)
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


# --- Tokens ---

def create_access_token(user: User) -> str:
    """Signed JWT; the frontend reads `full_name`, `admin` and `doctor` to adapt its menus."""
    now = utcnow()
    claims = {
        "sub": user.username,
        "full_name": user.full_name,
        "admin": user.has_role(Role.admin),
        "doctor": user.has_role(Role.doctor),
        "roles": sorted(g.name for g in user.groups),
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
        "iss": ISSUER,
        "aud": AUDIENCE,
        "type": "access",
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_refresh_token(session: Session, user_id: UUID) -> str:
    """Create an opaque refresh token, store its hash, return the raw token."""
    raw_token = secrets.token_urlsafe(64)
    session.add(RefreshToken(
        token_hash=_hash_token(raw_token),
        user_id=user_id,
        expires_at=utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    ))
    session.commit()
    return raw_token


def verify_refresh_token(session: Session, raw_token: str) -> RefreshToken | None:
    statement = select(RefreshToken).where(
        RefreshToken.token_hash == _hash_token(raw_token),
        RefreshToken.revoked == False,  # noqa: E712
    )
    db_token = session.exec(statement).first()
    if not db_token:
        return None
    if db_token.expires_at < utcnow():
        db_token.revoked = True
        session.add(db_token)
        session.commit()
        return None
    return db_token


def revoke_user_refresh_tokens(session: Session, user_id: UUID) -> None:
    statement = select(RefreshToken).where(
        RefreshToken.user_id == user_id,
        RefreshToken.revoked == False,  # noqa: E712
    )
    for token in session.exec(statement).all():
        token.revoked = True
        session.add(token)
    session.commit()


# --- Dependencies ---

async def get_current_user(
    session: SessionDep,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM],
            issuer=ISSUER, audience=AUDIENCE,
        )
    except InvalidTokenError:
        raise credentials_exception
    username = payload.get("sub")
    if username is None or payload.get("type") != "access":
        raise credentials_exception
    user = session.exec(select(User).where(User.username == username)).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if current_user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    if not current_user.validated:
        raise HTTPException(status_code=403, detail="Account pending validation")
    return current_user


def require_roles(*roles: Role):
    """Dependency factory: the user needs one of `roles`; admins always pass."""

    async def checker(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
        if not current_user.has_role(Role.admin, *roles):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return current_user

    return checker


CurrentUser = Annotated[User, Depends(get_current_active_user)]
AdminUser = Annotated[User, Depends(require_roles(Role.admin))]
# Operating-room and bed managers configure resources and vacations
PlannerUser = Annotated[User, Depends(require_roles(Role.planner))]
# Surgeons and their secretariat create requests and decide on proposals
ClinicalUser = Annotated[User, Depends(require_roles(Role.doctor, Role.secretary))]
# Read access to patients and planning: clinicians and operating-room / bed managers
StaffUser = Annotated[User, Depends(require_roles(Role.doctor, Role.secretary, Role.planner))]
