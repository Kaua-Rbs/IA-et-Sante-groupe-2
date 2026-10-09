import os

# Configure before api is imported: settings are read once at import time.
# Environment variables take precedence over kyst.env and kyst.local.env.
os.environ.update({
    "SECRET_KEY": "test-secret-key-with-enough-length-for-hs256",
    "DATABASE_URL": "sqlite://",
    "RATE_LIMIT_ENABLED": "false",
    "ACCOUNT_VALIDATION": "true",
    "FIRST_ADMIN_EMAIL": "admin@kyst.fr",
    "FIRST_ADMIN_PASSWORD": "admin-password",
    "AI_BACKEND": "fixtures",
    "EMERGENCY_MARGIN": "0.1",
    "PROPOSAL_COUNT": "2",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

from api.accounts.models import ROLE_IDS, Role  # noqa: E402
from api.db import engine  # noqa: E402
from api.main import app  # noqa: E402


@pytest.fixture
def client():
    SQLModel.metadata.drop_all(engine)
    with TestClient(app) as test_client:  # lifespan recreates tables, roles and admin
        yield test_client


def login(client: TestClient, login: str, password: str) -> dict[str, str]:
    response = client.post("/account/login", data={"username": login, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def admin(client) -> dict[str, str]:
    return login(client, "admin@kyst.fr", "admin-password")


@pytest.fixture
def make_user(client, admin):
    """Create a validated user with the given roles and return its auth headers."""

    def factory(name: str, *roles: Role) -> dict[str, str]:
        email = f"{name}@kyst.fr"
        response = client.post("/account/users/create", json={
            "username": email, "email": email, "full_name": f"Test {name}",
            "password": "password123",
        })
        assert response.status_code == 201, response.text
        user_id = response.json()["id"]
        client.post(f"/account/users/{user_id}/validate", headers=admin)
        for role in roles:
            client.post(f"/account/users/{user_id}/groups/{ROLE_IDS[role]}", headers=admin)
        return login(client, email, "password123")

    return factory
