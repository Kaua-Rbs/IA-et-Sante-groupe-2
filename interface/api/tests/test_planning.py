import asyncio
import datetime as dt
from threading import Event

import pytest
from sqlmodel import Session, select

from api.accounts.models import Role
from api.db import engine
from api.config import settings
from api.planning import replanning, service
from api.planning.models import ReplanRun

DAY = dt.timedelta(days=1)


def iso(days_from_today: int) -> str:
    return (dt.date.today() + days_from_today * DAY).isoformat()


@pytest.fixture
def setup(client, make_user):
    """Orthopaedics with one room, three vacations and a single conventional bed."""
    planner = make_user("planner", Role.planner)
    doctor = make_user("doctor", Role.doctor)

    def post(path, body, headers=planner):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    specialty = post("/specialties", {"name": "Orthopédie"})
    room = post("/rooms", {"name": "Salle 1", "default_specialty_id": specialty["id"]})
    beds = post("/bed-units", {"name": "Chirurgie", "care_type": "conventional", "capacity": 1})
    post("/bed-units", {"name": "Ambulatoire", "care_type": "ambulatory", "capacity": 21})
    surgeon = post("/surgeons", {"name": "Dr A", "specialty_id": specialty["id"]})
    for offset in (1, 2, 3):
        post("/vacations", {
            "room_id": room["id"], "specialty_id": specialty["id"],
            "date": iso(offset), "start_time": "08:00:00",
        })

    def new_request():
        patient = post("/patients", {"birth_year": 1960, "sex": 2}, headers=doctor)
        return post("/requests", {
            "patient_id": patient["id"], "surgeon_id": surgeon["id"],
            "principal_diagnosis": "M17.1", "ccam_codes": ["NFKA008"],
            "earliest_date": iso(0), "latest_date": iso(10),
        }, headers=doctor)

    return {"client": client, "doctor": doctor, "planner": planner, "beds": beds,
            "new_request": new_request, "room": room, "specialty": specialty}


def propose(s, request):
    response = s["client"].post(f"/requests/{request['id']}/proposals", headers=s["doctor"])
    assert response.status_code == 201, response.text
    return response.json()


def test_proposals_offer_distinct_dates_with_reasons(setup):
    proposals = propose(setup, setup["new_request"]())
    assert [p["rank"] for p in proposals] == [1, 2]
    assert proposals[0]["admission_date"] != proposals[1]["admission_date"]
    assert all(p["reasons"] for p in proposals)
    assert proposals[0]["scheduler"] == "greedy-capacity"


def test_accepting_books_the_slot_and_closes_the_alternatives(setup):
    s = setup
    request = s["new_request"]()
    first, second = propose(s, request)

    case = s["client"].post(f"/proposals/{first['id']}/accept", headers=s["doctor"])
    assert case.status_code == 201
    assert s["client"].get(f"/requests/{request['id']}", headers=s["doctor"]).json()["status"] == "scheduled"
    statuses = {p["id"]: p["status"] for p in s["client"].get(
        f"/requests/{request['id']}/proposals", headers=s["doctor"]).json()}
    assert statuses == {first["id"]: "accepted", second["id"]: "superseded"}

    cases = s["client"].get("/cases", params={"request_id": request["id"]}, headers=s["doctor"]).json()
    assert [c["id"] for c in cases] == [case.json()["id"]]

    occupancy = s["client"].get(
        "/analytics/occupancy", params={"start": first["admission_date"], "end": first["admission_date"]},
        headers=s["planner"],
    ).json()
    chirurgie = next(u for u in occupancy if u["name"] == "Chirurgie")
    assert chirurgie["days"][0]["occupied"] == 1


def test_full_beds_leave_no_proposal(setup):
    s = setup
    first = propose(s, s["new_request"]())[0]
    s["client"].post(f"/proposals/{first['id']}/accept", headers=s["doctor"])
    # The single bed is taken for the whole window covered by the three vacations
    assert propose(s, s["new_request"]()) == []


def test_stale_proposal_cannot_be_accepted(setup):
    s = setup
    a = propose(s, s["new_request"]())[0]
    b = propose(s, s["new_request"]())[0]
    assert s["client"].post(f"/proposals/{a['id']}/accept", headers=s["doctor"]).status_code == 201
    response = s["client"].post(f"/proposals/{b['id']}/accept", headers=s["doctor"])
    assert response.status_code == 409
    assert response.json()["detail"]["reasons"]


@pytest.mark.parametrize("edit", ["request", "patient"])
def test_clinical_edits_invalidate_old_dates(setup, edit):
    s = setup
    request = s["new_request"]()
    old = propose(s, request)[0]
    if edit == "request":
        path, body = f"/requests/{request['id']}", {"principal_diagnosis": "M16.1"}
    else:
        path, body = f"/patients/{request['patient_id']}", {"sex": 1}
    changed = s["client"].patch(path, headers=s["doctor"], json=body)
    assert changed.status_code == 200, changed.text
    assert s["client"].post(
        f"/proposals/{old['id']}/accept", headers=s["doctor"],
    ).status_code == 409
    assert all(row["status"] == "superseded" for row in s["client"].get(
        f"/requests/{request['id']}/proposals", headers=s["doctor"],
    ).json())
    assert len(propose(s, changed.json() if edit == "request" else request)) == 2


def test_replanning_publishes_pending_cases_and_preserves_confirmed_cases(setup):
    s = setup
    request = s["new_request"]()
    assert s["client"].get("/planning/replanning", headers=s["planner"]).json()["pending_changes"] > 0
    assert s["client"].post("/planning/replanning/run", headers=s["doctor"]).status_code == 403
    run = s["client"].post("/planning/replanning/run", headers=s["planner"])
    assert run.status_code == 200, run.text
    assert run.json()["run"]["status"] == "succeeded"
    proposals = s["client"].get(
        f"/requests/{request['id']}/proposals", headers=s["doctor"],
    ).json()
    assert len(proposals) == 1
    assert proposals[0]["scheduler"].startswith("cohort:")
    case = s["client"].post(
        f"/proposals/{proposals[0]['id']}/accept", headers=s["doctor"],
    ).json()
    refreshed = s["client"].post("/planning/replanning/run", headers=s["planner"])
    assert refreshed.json()["run"]["status"] == "succeeded"
    assert s["client"].get("/cases", headers=s["doctor"]).json() == [case]
    assert s["client"].get("/planning/replanning", headers=s["planner"]).json()["pending_changes"] == 0


def test_failed_refresh_preserves_previous_proposals_without_error_details(setup, monkeypatch):
    s = setup
    request = s["new_request"]()
    original = propose(s, request)

    def failing(*args, **kwargs):
        raise RuntimeError("private clinical payload")

    monkeypatch.setattr(service, "publish_cohort_proposals", failing)
    response = s["client"].post("/planning/replanning/run", headers=s["planner"])
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "failed"
    assert response.json()["run"]["failure_type"] == "RuntimeError"
    assert "private clinical payload" not in response.text
    current = s["client"].get(
        f"/requests/{request['id']}/proposals", headers=s["doctor"],
    ).json()
    assert {row["id"]: row for row in current} == {row["id"]: row for row in original}


def test_automatic_worker_processes_committed_changes(setup, monkeypatch):
    s = setup
    request = s["new_request"]()
    done = Event()
    original = replanning.process_pending_changes
    results = []

    def process():
        try:
            results.append(original())
        finally:
            done.set()

    monkeypatch.setattr(replanning, "process_pending_changes", process)
    monkeypatch.setattr(settings, "AUTO_REPLAN_ENABLED", True)

    async def execute():
        async with replanning.change_worker():
            assert await asyncio.to_thread(done.wait, 10)

    asyncio.run(execute())
    assert results[0]["status"] == "succeeded"
    assert s["client"].get(
        f"/requests/{request['id']}/proposals", params={"status": "proposed"}, headers=s["doctor"],
    ).json()


def test_interrupted_refresh_is_retried_after_restart(client):
    with Session(engine) as session:
        run = ReplanRun(method="SMA", start=dt.date.today(), end=dt.date.today())
        session.add(run)
        session.commit()
    replanning.recover_interrupted_runs()
    with Session(engine) as session:
        assert session.exec(select(ReplanRun)).one().status == "interrupted"
        assert replanning.queue_status(session)["pending_changes"] == 1
    replanning.recover_interrupted_runs()
    with Session(engine) as session:
        assert replanning.queue_status(session)["pending_changes"] == 1


def test_rejected_dates_are_not_reoffered_by_a_refresh(setup):
    s = setup
    request = s["new_request"]()
    old = propose(s, request)[0]
    rejected = s["client"].post(f"/proposals/{old['id']}/reject", headers=s["doctor"])
    assert rejected.status_code == 200
    refreshed = s["client"].post("/planning/replanning/run", headers=s["planner"])
    assert refreshed.json()["run"]["status"] == "succeeded"
    opened = s["client"].get(
        f"/requests/{request['id']}/proposals", params={"status": "proposed"}, headers=s["doctor"],
    ).json()
    assert opened
    assert all(row["admission_date"] != old["admission_date"] for row in opened)


def test_refresh_removes_open_dates_for_newly_unassignable_requests(setup):
    s = setup
    request = s["new_request"]()
    propose(s, request)
    closed = s["client"].patch(
        f"/bed-units/{s['beds']['id']}", json={"active": False}, headers=s["planner"],
    )
    assert closed.status_code == 200
    refreshed = s["client"].post("/planning/replanning/run", headers=s["planner"])
    assert refreshed.json()["run"]["status"] == "succeeded"
    assert refreshed.json()["run"]["proposals_count"] == 0
    assert s["client"].get(
        f"/requests/{request['id']}/proposals", params={"status": "proposed"}, headers=s["doctor"],
    ).json() == []


def test_care_type_change_flags_confirmed_stay_without_moving_it(setup):
    s = setup
    first = propose(s, s["new_request"]())[0]
    case = s["client"].post(f"/proposals/{first['id']}/accept", headers=s["doctor"]).json()
    assert s["client"].get("/planning/commitment-conflicts", headers=s["planner"]).json() == []
    changed = s["client"].patch(f"/bed-units/{s['beds']['id']}", headers=s["planner"],
                                json={"care_type": "ambulatory"})
    assert changed.status_code == 200, changed.text
    conflicts = s["client"].get("/planning/commitment-conflicts", headers=s["planner"]).json()
    assert [row["case_id"] for row in conflicts] == [case["id"]]
    assert any("hébergement" in reason for reason in conflicts[0]["reasons"])
    assert s["client"].get("/cases", headers=s["doctor"]).json() == [case]


def test_cancelling_a_case_frees_capacity(setup):
    s = setup
    request = s["new_request"]()
    case = s["client"].post(
        f"/proposals/{propose(s, request)[0]['id']}/accept", headers=s["doctor"]).json()
    s["client"].post(f"/cases/{case['id']}/cancel", headers=s["doctor"])

    assert s["client"].get(f"/requests/{request['id']}", headers=s["doctor"]).json()["status"] == "pending"
    assert len(propose(s, s["new_request"]())) == 2


def test_outcome_feeds_prediction_accuracy(setup):
    s = setup
    request = s["new_request"]()
    proposal = propose(s, request)[0]
    case = s["client"].post(f"/proposals/{proposal['id']}/accept", headers=s["doctor"]).json()
    actual = proposal["planned_minutes"] + 10
    s["client"].post(f"/cases/{case['id']}/outcome", headers=s["doctor"],
                     json={"actual_room_minutes": actual, "actual_los_days": 4})

    accuracy = s["client"].get("/analytics/predictions", headers=s["planner"]).json()
    assert accuracy["evaluated_cases"] == 1
    assert accuracy["room_minutes_underestimated"] == 1
    assert accuracy["room_minutes_mae"] == pytest.approx(10, abs=1)


def test_overlapping_vacations_are_refused(setup):
    s = setup
    response = s["client"].post("/vacations", headers=s["planner"], json={
        "room_id": s["room"]["id"], "specialty_id": s["specialty"]["id"],
        "date": iso(1), "start_time": "10:00:00",
    })
    assert response.status_code == 409


def test_doctor_cannot_configure_resources(setup):
    response = setup["client"].post("/specialties", json={"name": "ORL"}, headers=setup["doctor"])
    assert response.status_code == 403


def test_health_exposes_scheduling_settings(client):
    health = client.get("/health").json()
    assert health["emergency_margin"] == 0.1
    assert health["proposal_count"] == 2
