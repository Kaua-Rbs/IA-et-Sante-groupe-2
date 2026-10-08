"""Create the tables, the fixed roles and the optional first administrator."""

import logging

from sqlmodel import Session, SQLModel, select

# Import every table module so SQLModel registers them before create_all
import api.clinical.models  # noqa: F401
import api.planning.models  # noqa: F401
import api.resources.models  # noqa: F401
from api.accounts.models import ROLE_IDS, Group, Role, User
from api.accounts.security import get_password_hash
from api.config import settings
from api.db import engine

logger = logging.getLogger(__name__)


def create_roles(session: Session) -> None:
    for role, role_id in ROLE_IDS.items():
        if session.get(Group, role_id) is None:
            session.add(Group(id=role_id, name=role.value))
    session.commit()


def create_first_admin(session: Session) -> None:
    email, password = settings.FIRST_ADMIN_EMAIL, settings.FIRST_ADMIN_PASSWORD
    if not email or not password:
        return
    if session.exec(select(User).where(User.email == email)).first():
        return
    admin = User(
        username=email, email=email, full_name="Administrateur",
        hashed_password=get_password_hash(password), validated=True,
        groups=[session.get(Group, ROLE_IDS[Role.admin])],
    )
    session.add(admin)
    session.commit()
    logger.info("First administrator %s created", email)


def init_db() -> None:
    # TODO: replace create_all with Alembic migrations before the schema stabilises
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        create_roles(session)
        create_first_admin(session)
