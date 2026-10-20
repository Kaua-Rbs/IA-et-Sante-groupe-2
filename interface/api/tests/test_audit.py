import json
import logging

import pytest

from api.accounts.models import Role
from api.audit import JsonFormatter


@pytest.fixture
def trail(caplog):
    caplog.set_level(logging.INFO, logger="kyst.audit")

    def events(name: str) -> list[logging.LogRecord]:
        return [r for r in caplog.records if r.name == "kyst.audit" and r.event == name]

    return events


def test_access_trail_names_the_user_the_route_and_the_browser(client, make_user, trail):
    doctor = make_user("surgeon", Role.doctor)
    patient = client.post("/patients", json={"birth_year": 1960, "sex": 2}, headers=doctor).json()
    client.get(f"/patients/{patient['id']}", headers={**doctor, "X-Forwarded-For": "203.0.113.7"})
    client.get("/patients", params={"external_ref": "IPP-123"}, headers=doctor)

    read, listed = trail("http.access")[-2:]
    assert read.user == "surgeon@kyst.fr"
    assert read.client == "203.0.113.7"
    assert read.route == "/patients/{patient_id}"
    assert read.params == {"patient_id": patient["id"]}
    assert read.status == 200
    # Query strings may hold patient identifiers: they stay out of the logs
    assert "IPP-123" not in json.dumps(vars(listed), default=str)


def test_login_attempts_are_logged_without_the_password(client, trail):
    client.post("/account/login", data={"username": "admin@kyst.fr", "password": "wrong-password"})
    client.post("/account/login", data={"username": "admin@kyst.fr", "password": "admin-password"})

    [failed] = trail("auth.login_failed")
    assert failed.login == "admin@kyst.fr"
    assert failed.reason == "bad_credentials"
    [success] = trail("auth.login")
    assert success.user == "admin@kyst.fr"
    logged = json.dumps([vars(failed), vars(success)], default=str)
    assert "wrong-password" not in logged and "admin-password" not in logged


def test_anonymous_and_rejected_requests_are_logged(client, trail):
    client.get("/patients", headers={"Authorization": "Bearer forged"})
    [entry] = trail("http.access")
    assert entry.user is None
    assert entry.status == 401


def test_log_lines_are_json_with_the_extra_fields():
    record = logging.makeLogRecord({"name": "kyst.audit", "msg": "http.access", "status": 200})
    line = json.loads(JsonFormatter().format(record))
    assert line["msg"] == "http.access"
    assert line["status"] == 200
    assert line["ts"].endswith("+00:00")
