"""Create the tables, the fixed roles and the optional first administrator."""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn
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


def add_missing_columns() -> None:
    """create_all never alters a table: add the optional columns of newer versions.

    Only nullable columns or columns with a server default are added, so
    existing rows stay valid.
    """
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in SQLModel.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing or not (column.nullable or column.server_default):
                    continue
                ddl = CreateColumn(column).compile(dialect=engine.dialect)
                connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                logger.info("Column %s.%s added", table.name, column.name)


def init_db() -> None:
    # TODO: replace create_all with Alembic migrations before the schema stabilises
    SQLModel.metadata.create_all(engine)
    add_missing_columns()
    with Session(engine) as session:
        create_roles(session)
        create_first_admin(session)
