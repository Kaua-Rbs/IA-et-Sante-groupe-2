from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, EmailStr, NaiveDatetime
from sqlmodel import Field, Relationship, SQLModel

from api.db import utcnow


class Role(str, Enum):
    """Fixed roles. Their ids are stable because the frontend relies on them (admin = 2)."""

    user = "user"  # read-only access
    doctor = "doctor"  # surgeon: requests, proposals, own planning
    admin = "admin"  # everything, including accounts
    secretary = "secretary"  # surgeon's secretariat: requests and proposals
    planner = "planner"  # operating-room / bed manager: resources and vacations


ROLE_IDS: dict[Role, int] = {
    Role.user: 0,
    Role.doctor: 1,
    Role.admin: 2,
    Role.secretary: 3,
    Role.planner: 4,
}


class UserGroupLink(SQLModel, table=True):
    user_id: UUID | None = Field(default=None, foreign_key="user.id", primary_key=True)
    group_id: int = Field(foreign_key="group.id", primary_key=True)


class GroupBase(SQLModel):
    name: str = Field(index=True, unique=True)


class Group(GroupBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    users: list["User"] = Relationship(back_populates="groups", link_model=UserGroupLink)


class GroupPublic(GroupBase):
    id: int


class UserBase(SQLModel):
    # The frontend uses the email as username
    username: str = Field(index=True, unique=True, min_length=3, max_length=254)
    email: EmailStr = Field(index=True, unique=True)
    full_name: str = Field(min_length=1, max_length=200)


class User(UserBase, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    hashed_password: str
    disabled: bool = False
    # False while the account waits for an admin's validation (see ACCOUNT_VALIDATION)
    validated: bool = True
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    groups: list[Group] = Relationship(back_populates="users", link_model=UserGroupLink)

    def has_role(self, *roles: Role) -> bool:
        names = {g.name for g in self.groups}
        return any(r.value in names for r in roles)


class UserPublic(UserBase):
    id: UUID
    disabled: bool
    validated: bool
    groups: list[GroupPublic] = []


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)


class UserUpdate(SQLModel):
    """Admin update schema. Password changes use /account/change-password."""

    username: str | None = Field(default=None, min_length=3, max_length=254)
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    disabled: bool | None = None


class UserSelfUpdate(SQLModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=200)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class RefreshToken(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    token_hash: str = Field(index=True, unique=True)
    user_id: UUID = Field(foreign_key="user.id", index=True)
    expires_at: NaiveDatetime
    revoked: bool = False
    created_at: NaiveDatetime = Field(default_factory=utcnow)
