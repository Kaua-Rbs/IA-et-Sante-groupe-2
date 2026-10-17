import datetime as dt
from uuid import UUID

import pytest

from api.accounts.models import Role
from api.ai.cohort import CohortCase, optimize_cohort
from api.ai.contracts import BedUnitLoad, PredictionInput, VacationSlot
from api.ai.trained import _raw_features
from api.resources.models import CareType
from duration_features import engineer_features
from surgery_duration import FIXED_FEATURES


DAY = dt.date(2030, 1, 7)


def _case(number: int, *, first=0, last=2, stay=1):
    return CohortCase(UUID(int=number), 1, 1, 95, stay, CareType.conventional,
                      DAY + dt.timedelta(days=first), DAY + dt.timedelta(days=last))


def _slot(number: int, day: int):
    return VacationSlot(number, DAY + dt.timedelta(days=day), "Salle 1", 1, None, 240, 0)


def test_cohort_optimization_respects_patient_windows_and_capacity():
    cases = (_case(1, first=0, last=0), _case(2, first=1, last=1))
    result = optimize_cohort(cases, (_slot(1, 0), _slot(2, 1)),
                             (BedUnitLoad(1, "Chirurgie", CareType.conventional, 1),),
                             method="Tabou x Recuit", emergency_margin=0.1,
                             budget_seconds=0.05)
    assert len(result.assignments) == 2
    assert not result.unassigned
    assert {row.request_id: row.admission_date for row in result.assignments} == {
        UUID(int=1): DAY, UUID(int=2): DAY + dt.timedelta(days=1)}


def test_cohort_preview_never_overbooks_beds():
    cases = (_case(1, first=0, last=0, stay=2),
             _case(2, first=0, last=0, stay=2))
    result = optimize_cohort(cases, (_slot(1, 0),),
                             (BedUnitLoad(1, "Chirurgie", CareType.conventional, 1),),
                             method="Fourmis (ACO)", emergency_margin=0.1,
                             budget_seconds=0.05)
    assert len(result.assignments) == 1
    assert len(result.unassigned) == 1
    assert {row.request_id for row in result.assignments} | set(result.unassigned) == {
        UUID(int=1), UUID(int=2)}


def test_web_consultation_fields_map_to_model_features():
    features = PredictionInput(66, 2, "M17.1", ("NFKA008", "ABC123"),
                               "Orthopédie", "Prothèse de genou")
    raw = _raw_features(features)
    engineered = engineer_features(raw, FIXED_FEATURES)
    assert engineered.iloc[0]["age_years"] == 66
    assert engineered.iloc[0]["ccam_1"] == "NFKA008"
    assert engineered.iloc[0]["num_ccam_codes"] == 2
    assert engineered.iloc[0]["anesth_type_missing"] == 1
    assert "target_surgery_duration_min" not in engineered
    assert "target_los_days" not in engineered


def test_cohort_api_preview_is_read_only(client, make_user):
    planner = make_user("cohort-planner", Role.planner)
    doctor = make_user("cohort-doctor", Role.doctor)

    def create(path, body, headers=planner):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, response.text
        return response.json()

    specialty = create("/specialties", {"name": "Orthopédie"})
    room = create("/rooms", {"name": "Salle 1", "default_specialty_id": specialty["id"]})
    create("/bed-units", {"name": "Chirurgie", "care_type": "conventional", "capacity": 2})
    surgeon = create("/surgeons", {"name": "Dr A", "specialty_id": specialty["id"]})
    day = dt.date.today() + dt.timedelta(days=1)
    create("/vacations", {"room_id": room["id"], "specialty_id": specialty["id"],
                           "date": day.isoformat(), "start_time": "08:00:00"})
    for _ in range(2):
        patient = create("/patients", {"birth_year": 1960, "sex": 2}, doctor)
        create("/requests", {"patient_id": patient["id"], "surgeon_id": surgeon["id"],
                             "principal_diagnosis": "M17.1", "ccam_codes": ["NFKA008"],
                             "earliest_date": day.isoformat(), "latest_date": day.isoformat()},
               doctor)

    body = {"start": day.isoformat(), "end": day.isoformat(),
            "method": "Tabou x Recuit", "budget_seconds": 0.1}
    assert client.post("/planning/cohort-preview", json=body, headers=doctor).status_code == 403
    response = client.post("/planning/cohort-preview", json=body, headers=planner)
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["evaluated_cases"] == 2
    assert len(preview["assignments"]) == 2
    assert preview["unassigned"] == []
    assert client.get("/cases", headers=planner).json() == []
    assert all(not client.get(f"/requests/{row['request_id']}/proposals",
                              headers=planner).json() for row in preview["assignments"])

    simulation = client.post("/planning/room-simulation-preview", headers=planner, json={
        "date": day.isoformat(), "method": "baseline", "policy": "reactive",
        "realized_factor": 1.2, "outage": True,
    })
    assert simulation.status_code == 200, simulation.text
    replay = simulation.json()
    assert replay["cases"] == replay["completed"] + replay["unstarted"] == 2
    assert replay["assumptions"]["room_1_closure"] == "10:00-12:00"
    assert "case_id" not in simulation.text and "patient_id" not in simulation.text
    assert client.get("/cases", headers=planner).json() == []

    search = client.post("/planning/room-simulation-preview", headers=planner, json={
        "date": day.isoformat(), "method": "aco", "policy": "reactive",
        "realized_factor": 1.2, "outage": True,
    })
    assert search.status_code == 200, search.text
    assert search.json()["cases"] == search.json()["completed"] + search.json()["unstarted"]
