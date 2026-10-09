import jwt

from api.accounts.models import Role


def register(client, email="new@kyst.fr"):
    # Same payload as the SvelteKit registration action
    return client.post("/account/users/create", json={
        "username": email, "full_name": "Jeanne Martin", "email": email,
        "password": "password123",
    })


def test_new_account_waits_for_admin_validation(client, admin):
    user = register(client).json()
    assert user["validated"] is False

    pending = client.post("/account/login", data={"username": "new@kyst.fr", "password": "password123"})
    assert pending.status_code == 403

    client.post(f"/account/users/{user['id']}/validate", headers=admin)
    ok = client.post("/account/login", data={"username": "new@kyst.fr", "password": "password123"})
    assert ok.status_code == 200


def test_duplicate_registration_is_a_conflict(client):
    register(client)
    assert register(client).status_code == 409


def test_access_token_carries_the_claims_the_frontend_reads(client, make_user):
    headers = make_user("surgeon", Role.doctor)
    claims = jwt.decode(headers["Authorization"].split()[1], options={"verify_signature": False})
    assert claims["full_name"] == "Test surgeon"
    assert claims["doctor"] is True
    assert claims["admin"] is False
    assert claims["roles"] == ["doctor"]


def test_wrong_password_is_rejected(client):
    response = client.post("/account/login", data={"username": "admin@kyst.fr", "password": "nope"})
    assert response.status_code == 401


def test_refresh_token_is_rotated(client):
    tokens = client.post(
        "/account/login", data={"username": "admin@kyst.fr", "password": "admin-password"},
    ).json()
    refreshed = client.post("/account/token/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refreshed.status_code == 200
    reused = client.post("/account/token/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert reused.status_code == 401


def test_admin_group_has_the_id_the_frontend_expects(client, admin):
    me = client.get("/account/users/me", headers=admin).json()
    assert [g["id"] for g in me["groups"]] == [2]


def test_user_listing_requires_admin(client, make_user):
    headers = make_user("reader")
    assert client.get("/account/users/", headers=headers).status_code == 403
