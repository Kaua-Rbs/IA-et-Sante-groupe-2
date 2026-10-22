"""Room closures, surgeon absences, urgent requests and moving a patient."""

import datetime as dt

import pytest
from sqlalchemy import inspect, text

from api.accounts.models import Role
from api.bootstrap import add_missing_columns
from api.db import engine
from api.planning import service
from api.planning.availability import open_minutes, surgeon_absences
from api.resources.models import Unavailability, Vacation

DAY = dt.timedelta(days=1)


def iso(days_from_today: int) -> str:
    return (dt.date.today() + days_from_today * DAY).isoformat()


@pytest.fixture
def s(client, make_user):
    """Orthopaedics (95 min, 4 days per case), one room, 4-hour vacations today and on days 1-3."""
    planner = make_user("planner", Role.planner)
    doctor = make_user("doctor", Role.doctor)

    def call(method, path, body=None, headers=doctor, status=None):
        response = client.request(method, path, json=body, headers=headers)
        if status is not None:
            assert response.status_code == status, response.text
        return response

    def post(path, body, headers=planner):
        return call("POST", path, body, headers, 201).json()

    specialty = post("/specialties", {"name": "Orthopédie"})
    room = post("/rooms", {"name": "Salle 1", "default_specialty_id": specialty["id"]})
    post("/bed-units", {"name": "Chirurgie", "care_type": "conventional", "capacity": 20})
    surgeon = post("/surgeons", {"name": "Dr A", "specialty_id": specialty["id"]})
    for offset in (0, 1, 2, 3):
        post("/vacations", {"room_id": room["id"], "specialty_id": specialty["id"],
                            "date": iso(offset), "start_time": "08:00:00"})

    def request(first: int, last: int, urgent: bool = False):
        patient = post("/patients", {"birth_year": 1960, "sex": 2}, headers=doctor)
        return post("/requests", {
            "patient_id": patient["id"], "surgeon_id": surgeon["id"],
            "principal_diagnosis": "M17.1", "ccam_codes": ["NFKA008"],
            "earliest_date": iso(first), "latest_date": iso(last), "urgent": urgent,
        }, headers=doctor)

    def propose(req):
        return call("POST", f"/requests/{req['id']}/proposals", status=201).json()

    def book(day: int):
        """Confirm a case on the given day; two fill a vacation (190 of 216 usable min)."""
        req = request(day, day)
        proposal = propose(req)[0]
        return call("POST", f"/proposals/{proposal['id']}/accept", status=201).json()

    def dates(proposals):
        return sorted(p["admission_date"] for p in proposals)

    return dict(call=call, post=post, request=request, propose=propose, book=book, dates=dates,
                planner=planner, doctor=doctor, room=room, surgeon=surgeon)


def conflicts(s):
    return s["call"]("GET", "/planning/commitment-conflicts", headers=s["planner"], status=200).json()


# --- Room closures and surgeon absences ---

def test_partial_room_closure_shortens_the_vacation(s):
    s["book"](1)
    assert iso(1) in s["dates"](s["propose"](s["request"](1, 1)))
    # Closed 8h-10h: 120 open minutes, 108 usable, and one case of 95 is already there
    s["post"]("/unavailabilities", {"room_id": s["room"]["id"], "start_date": iso(1),
                                    "end_date": iso(1), "start_time": "08:00:00",
                                    "end_time": "10:00:00", "reason": "Maintenance"})
    assert s["propose"](s["request"](1, 1)) == []
    assert conflicts(s) == []  # the confirmed case still fits in the open time


def test_closure_deprograms_only_the_cases_that_no_longer_fit(s):
    first = s["book"](2)
    second = s["book"](2)
    s["post"]("/unavailabilities", {"room_id": s["room"]["id"], "start_date": iso(2),
                                    "end_date": iso(2), "start_time": "10:00:00",
                                    "end_time": "12:00:00", "reason": "Panne"})
    # 120 open minutes: the first booked stays, the second is deprogrammed
    assert s["call"]("GET", f"/cases/{first['id']}", status=200).json()["status"] == "planned"
    moved = s["call"]("GET", f"/cases/{second['id']}", status=200).json()
    assert moved["status"] == "cancelled"
    assert moved["cancel_reason"].startswith("Déprogrammée : Salle 1 fermée le")
    assert conflicts(s) == []
    (row,) = s["call"]("GET", "/planning/deprogrammed", status=200).json()
    assert row["case_id"] == second["id"] and row["former_date"] == iso(2)
    assert "de 10h00 à 12h00" in row["reason"]
    assert row["proposals"] == []  # its window is day 2 only, now full


def test_whole_day_closure_removes_the_date(s):
    s["post"]("/unavailabilities", {"room_id": s["room"]["id"],
                                    "start_date": iso(1), "end_date": iso(2)})
    assert s["dates"](s["propose"](s["request"](1, 3))) == [iso(3)]


def test_surgeon_absence_deprograms_future_cases_with_dates_a_b(s):
    proposal = s["propose"](s["request"](1, 3))[0]
    assert proposal["admission_date"] == iso(1)
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    s["post"]("/unavailabilities", {"surgeon_id": s["surgeon"]["id"], "start_date": iso(1),
                                    "end_date": iso(2), "reason": "Arrêt de travail"})
    assert s["dates"](s["propose"](s["request"](1, 3))) == [iso(3)]
    (row,) = s["call"]("GET", "/planning/deprogrammed", status=200).json()
    assert row["case_id"] == case["id"]
    assert "Dr A absent du" in row["reason"] and "Arrêt de travail" in row["reason"]
    assert [p["admission_date"] for p in row["proposals"]] == [iso(3)]


def test_absence_today_leaves_the_case_as_a_conflict(s):
    case = s["book"](0)
    s["post"]("/unavailabilities", {"surgeon_id": s["surgeon"]["id"],
                                    "start_date": iso(0), "end_date": iso(0)})
    assert s["call"]("GET", f"/cases/{case['id']}", status=200).json()["status"] == "planned"
    (found,) = conflicts(s)
    assert found["case_id"] == case["id"]


def test_deleting_a_vacation_with_future_cases_deprograms_them(s):
    case = s["book"](1)
    vacation = case["vacation_id"]
    deleted = s["call"]("DELETE", f"/vacations/{vacation}", headers=s["planner"], status=200).json()
    assert deleted == {"ok": True, "deprogrammed": 1}
    assert all(v["id"] != vacation for v in s["call"](
        "GET", "/vacations", headers=s["planner"], status=200).json())
    moved = s["call"]("GET", f"/cases/{case['id']}", status=200).json()
    assert moved["status"] == "cancelled" and "Vacation supprimée" in moved["cancel_reason"]
    # The slot can be opened again
    s["post"]("/vacations", {"room_id": s["room"]["id"], "specialty_id": s["room"]["default_specialty_id"],
                             "date": iso(1), "start_time": "08:00:00"})


def test_vacations_of_today_or_the_past_with_cases_are_kept(s):
    case = s["book"](0)
    response = s["call"]("DELETE", f"/vacations/{case['vacation_id']}", headers=s["planner"])
    assert response.status_code == 409
    assert s["call"]("GET", f"/cases/{case['id']}", status=200).json()["status"] == "planned"


def test_empty_vacation_is_really_deleted(s):
    vacation = s["call"]("GET", "/vacations", headers=s["planner"], status=200).json()[-1]
    assert s["call"]("DELETE", f"/vacations/{vacation['id']}", headers=s["planner"],
                     status=200).json() == {"ok": True, "deprogrammed": 0}
    assert s["call"]("GET", f"/vacations/{vacation['id']}", headers=s["planner"]).status_code == 404


def test_deprogrammed_dates_a_b_survive_a_cohort_refresh(s):
    proposal = s["propose"](s["request"](1, 3))[0]
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    s["call"]("PATCH", f"/vacations/{case['vacation_id']}", {"date": iso(5)},
              headers=s["planner"], status=200)
    (row,) = s["call"]("GET", "/planning/deprogrammed", status=200).json()
    before = [p["id"] for p in row["proposals"]]
    assert before
    s["call"]("POST", "/planning/replanning/run", headers=s["planner"], status=200)
    (row,) = s["call"]("GET", "/planning/deprogrammed", status=200).json()
    assert [p["id"] for p in row["proposals"]] == before


def test_partial_absence_removes_the_whole_vacation_everywhere(s):
    """Review: a vacation offered despite a partial absence could never be confirmed."""
    s["post"]("/unavailabilities", {"surgeon_id": s["surgeon"]["id"], "start_date": iso(1),
                                    "end_date": iso(1), "start_time": "08:00:00",
                                    "end_time": "09:00:00"})
    proposals = s["propose"](s["request"](1, 2))
    assert s["dates"](proposals) == [iso(2)]
    s["call"]("POST", f"/proposals/{proposals[0]['id']}/accept", status=201)
    # The cohort refresh applies the same rule
    s["request"](1, 1)
    s["call"]("POST", "/planning/replanning/run", headers=s["planner"], status=200)
    pending = s["call"]("GET", "/requests", headers=s["doctor"], status=200).json()
    for req in pending:
        rows = s["call"]("GET", f"/requests/{req['id']}/proposals", status=200).json()
        assert all(p["admission_date"] != iso(1) for p in rows if p["status"] == "proposed")


def test_absence_declared_after_a_proposal_blocks_its_confirmation(s):
    proposal = s["propose"](s["request"](1, 1))[0]
    s["post"]("/unavailabilities", {"surgeon_id": s["surgeon"]["id"],
                                    "start_date": iso(1), "end_date": iso(1)})
    response = s["call"]("POST", f"/proposals/{proposal['id']}/accept")
    assert response.status_code == 409
    assert "Le chirurgien est absent pendant cette vacation." in response.json()["detail"]["reasons"]


@pytest.mark.parametrize("body", [
    {"start_date": iso(1), "end_date": iso(1)},  # no target
    {"room_id": 1, "surgeon_id": 1, "start_date": iso(1), "end_date": iso(1)},
    {"room_id": 1, "start_date": iso(2), "end_date": iso(1)},
    {"room_id": 1, "start_date": iso(1), "end_date": iso(1), "start_time": "10:00:00"},
    {"room_id": 1, "start_date": iso(1), "end_date": iso(1),
     "start_time": "12:00:00", "end_time": "10:00:00"},
])
def test_invalid_unavailabilities_are_rejected(s, body):
    assert s["call"]("POST", "/unavailabilities", body, headers=s["planner"]).status_code == 422


def test_only_planners_manage_unavailabilities(s):
    body = {"room_id": s["room"]["id"], "start_date": iso(1), "end_date": iso(1)}
    assert s["call"]("POST", "/unavailabilities", body).status_code == 403
    created = s["post"]("/unavailabilities", body)
    listed = s["call"]("GET", "/unavailabilities", headers=s["doctor"], status=200).json()
    assert [u["id"] for u in listed] == [created["id"]]
    s["call"]("DELETE", f"/unavailabilities/{created['id']}", headers=s["planner"], status=200)
    assert iso(1) in s["dates"](s["propose"](s["request"](1, 1)))


def test_overlapping_closures_are_counted_once():
    vacation = Vacation(room_id=1, specialty_id=1, date=dt.date(2026, 1, 5),
                        start_time=dt.time(8), duration_min=240)
    day = dict(start_date=vacation.date, end_date=vacation.date)
    closures = [
        Unavailability(room_id=1, start_time=dt.time(9), end_time=dt.time(11), **day),
        Unavailability(room_id=1, start_time=dt.time(10), end_time=dt.time(13), **day),
        Unavailability(room_id=2, **day),  # another room
        Unavailability(surgeon_id=7, **day),  # absent surgeon not operating there
    ]
    assert open_minutes(vacation, closures) == 60
    # A surgeon absent for part of the vacation cannot operate in it; others can
    assert surgeon_absences(vacation, closures, 7) == [closures[3]]
    assert surgeon_absences(vacation, closures, 8) == []


# --- Urgent requests ---

def test_urgent_request_may_use_the_emergency_margin(s):
    # Shorten day 1 so one case leaves 105 min: enough only without the 10 % margin
    vacation = s["call"]("GET", "/vacations", headers=s["planner"],
                         status=200).json()[1]
    s["call"]("PATCH", f"/vacations/{vacation['id']}", {"duration_min": 200},
              headers=s["planner"], status=200)
    s["book"](1)
    assert s["propose"](s["request"](1, 1)) == []
    (proposal,) = s["propose"](s["request"](1, 1, urgent=True))
    assert proposal["displaced_case_ids"] == []
    assert any("marge réservée aux urgences" in reason for reason in proposal["reasons"])


def test_urgent_request_postpones_the_fewest_future_cases(s):
    first = s["book"](1)
    second = s["book"](1)
    assert s["propose"](s["request"](1, 1)) == []  # an ordinary request never displaces anyone
    urgent = s["request"](1, 1, urgent=True)
    (proposal,) = s["propose"](urgent)
    assert len(proposal["displaced_case_ids"]) == 1
    displaced_id = proposal["displaced_case_ids"][0]
    assert displaced_id in (first["id"], second["id"])
    assert any("reporte 1 intervention programmée" in reason for reason in proposal["reasons"])

    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    assert case["admission_date"] == iso(1)
    displaced = s["call"]("GET", f"/cases/{displaced_id}", status=200).json()
    assert displaced["status"] == "cancelled"
    postponed = s["call"]("GET", f"/requests/{displaced['request_id']}", status=200).json()
    assert postponed["status"] == "pending"
    # The postponed patient's window is day 1 only, now full: no date, but it is visible as pending
    reproposed = s["call"]("GET", f"/requests/{displaced['request_id']}/proposals",
                           status=200).json()
    assert all(p["admission_date"] != iso(1) for p in reproposed if p["status"] == "proposed")


def test_postponed_patients_get_new_dates_at_once(s):
    # Two patients free on days 1-3, both booked on day 1 while days 2-3 are closed
    closure = s["post"]("/unavailabilities", {"room_id": s["room"]["id"],
                                              "start_date": iso(2), "end_date": iso(3)})
    for _ in range(2):
        proposal = s["propose"](s["request"](1, 3))[0]
        assert proposal["admission_date"] == iso(1)
        s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201)
    s["call"]("DELETE", f"/unavailabilities/{closure['id']}", headers=s["planner"], status=200)

    (urgent,) = s["propose"](s["request"](1, 1, urgent=True))
    s["call"]("POST", f"/proposals/{urgent['id']}/accept", status=201)
    displaced = s["call"]("GET", f"/cases/{urgent['displaced_case_ids'][0]}", status=200).json()
    fresh = [p for p in s["call"]("GET", f"/requests/{displaced['request_id']}/proposals",
                                  status=200).json() if p["status"] == "proposed"]
    assert fresh and iso(1) not in s["dates"](fresh)


def test_urgent_case_in_the_margin_is_not_a_conflict(s):
    """Review: a vacation filled into its margin by an emergency was flagged as overbooked."""
    vacation = s["call"]("GET", "/vacations", headers=s["planner"], status=200).json()[1]
    s["call"]("PATCH", f"/vacations/{vacation['id']}", {"duration_min": 200},
              headers=s["planner"], status=200)
    s["book"](1)
    (proposal,) = s["propose"](s["request"](1, 1, urgent=True))
    s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201)
    assert conflicts(s) == []


def test_urgent_request_postpones_a_bed_holder_when_beds_are_full(s):
    """Review: with operating time free but no bed, no postponement was offered."""
    unit = s["call"]("GET", "/bed-units", headers=s["planner"], status=200).json()[0]
    s["call"]("PATCH", f"/bed-units/{unit['id']}", {"capacity": 1}, headers=s["planner"], status=200)
    holder = s["book"](2)  # 4-day stay from day 2: the only bed is taken on days 2-4
    assert s["propose"](s["request"](1, 1)) == []
    (proposal,) = s["propose"](s["request"](1, 1, urgent=True))
    assert proposal["admission_date"] == iso(1)
    assert proposal["displaced_case_ids"] == [holder["id"]]
    assert any("pour libérer un lit" in reason for reason in proposal["reasons"])
    s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201)


def test_failed_new_dates_do_not_undo_an_urgent_confirmation(s, monkeypatch):
    """Review: the booking was committed, then a failing re-proposal returned a 500."""
    s["book"](1)
    s["book"](1)
    (proposal,) = s["propose"](s["request"](1, 1, urgent=True))

    def broken(*args, **kwargs):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(service, "propose", broken)
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    assert case["status"] == "planned"
    displaced = s["call"]("GET", f"/cases/{proposal['displaced_case_ids'][0]}", status=200).json()
    assert displaced["status"] == "cancelled"
    assert s["call"]("GET", f"/requests/{displaced['request_id']}", status=200).json()["status"] == "pending"


def test_cases_of_today_are_never_postponed(s):
    s["book"](0)
    s["book"](0)
    assert s["propose"](s["request"](0, 0, urgent=True)) == []


def test_urgent_proposals_survive_a_cohort_refresh(s):
    s["book"](1)
    s["book"](1)
    (proposal,) = s["propose"](s["request"](1, 1, urgent=True))
    s["call"]("POST", "/planning/replanning/run", headers=s["planner"], status=200)
    rows = s["call"]("GET", f"/requests/{proposal['request_id']}/proposals", status=200).json()
    assert {row["id"]: row["status"] for row in rows} == {proposal["id"]: "proposed"}


# --- Moving a patient ---

def test_reschedule_frees_the_slot_and_offers_other_dates(s):
    proposal = s["propose"](s["request"](1, 3))[0]
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    proposals = s["call"]("POST", f"/cases/{case['id']}/reschedule", status=201).json()
    assert proposals and case["admission_date"] not in s["dates"](proposals)
    assert s["call"]("GET", f"/cases/{case['id']}", status=200).json()["status"] == "cancelled"
    assert s["call"]("GET", f"/requests/{case['request_id']}", status=200).json()["status"] == "pending"
    assert s["call"]("POST", f"/cases/{case['id']}/reschedule").status_code == 409


def test_the_date_left_stays_excluded_after_a_refresh(s):
    """Review: a cohort refresh re-offered the date the patient had just left."""
    proposal = s["propose"](s["request"](1, 3))[0]
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    s["call"]("POST", f"/cases/{case['id']}/reschedule", status=201)
    s["call"]("POST", "/planning/replanning/run", headers=s["planner"], status=200)
    rows = s["call"]("GET", f"/requests/{case['request_id']}/proposals", status=200).json()
    open_dates = [p["admission_date"] for p in rows if p["status"] == "proposed"]
    assert open_dates and case["admission_date"] not in open_dates
    assert any(p["status"] == "rejected" and p["admission_date"] == case["admission_date"] for p in rows)


def test_reschedule_keeps_the_booking_without_another_date(s):
    """Review: the booking was cancelled even when no other date existed."""
    case = s["book"](1)  # window: day 1 only
    response = s["call"]("POST", f"/cases/{case['id']}/reschedule")
    assert response.status_code == 409 and "conservée" in response.json()["detail"]
    assert s["call"]("GET", f"/cases/{case['id']}", status=200).json()["status"] == "planned"


def test_a_case_of_today_can_be_moved_by_a_human(s):
    """Its room may be closed today: the team reprograms it, with the disruption as reason."""
    later = s["post"]("/unavailabilities", {"room_id": s["room"]["id"],
                                            "start_date": iso(1), "end_date": iso(3)})
    proposal = s["propose"](s["request"](0, 3))[0]
    assert proposal["admission_date"] == iso(0)
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    s["call"]("DELETE", f"/unavailabilities/{later['id']}", headers=s["planner"], status=200)
    s["post"]("/unavailabilities", {"room_id": s["room"]["id"], "start_date": iso(0), "end_date": iso(0)})
    # Today is frozen: listed for the team, not deprogrammed automatically
    assert [c["case_id"] for c in conflicts(s)] == [case["id"]]
    moved = s["call"]("POST", f"/cases/{case['id']}/reschedule",
                      {"reason": "Salle 1 fermée le jour même"}, status=201).json()
    assert moved and case["admission_date"] not in s["dates"](moved)
    row = next(r for r in s["call"]("GET", "/planning/deprogrammed", status=200).json()
               if r["case_id"] == case["id"])
    assert row["reason"] == "Déprogrammée : Salle 1 fermée le jour même"
    assert conflicts(s) == []


# --- Schema upgrade ---

def test_missing_optional_columns_are_added_on_startup(s):
    """A database created by the previous version keeps working after the upgrade."""
    proposal = s["propose"](s["request"](1, 1))[0]
    with engine.begin() as connection:
        connection.execute(text('ALTER TABLE "surgicalrequest" DROP COLUMN urgent'))
        connection.execute(text('ALTER TABLE "proposal" DROP COLUMN displaced_case_ids'))
    add_missing_columns()
    assert "urgent" in {c["name"] for c in inspect(engine).get_columns("surgicalrequest")}
    with engine.begin() as connection:
        assert connection.execute(text('SELECT urgent FROM "surgicalrequest"')).scalars().all() == [0]
    listed = s["call"]("GET", f"/requests/{proposal['request_id']}/proposals", status=200).json()
    assert listed[0]["displaced_case_ids"] == []
    s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201)


def test_widening_the_window_keeps_the_date_left_excluded(s):
    """Widening the deadline (no date found) must not bring back the date the patient left."""
    proposal = s["propose"](s["request"](1, 2))[0]
    case = s["call"]("POST", f"/proposals/{proposal['id']}/accept", status=201).json()
    s["call"]("POST", f"/cases/{case['id']}/reschedule", status=201)
    s["call"]("PATCH", f"/requests/{case['request_id']}", {"latest_date": iso(3)}, status=200)
    dates = s["dates"](s["call"]("POST", f"/requests/{case['request_id']}/proposals", status=201).json())
    assert dates and case["admission_date"] not in dates


def test_a_closed_slot_is_deprogrammed_even_without_another_date(s):
    case = s["book"](0)  # window: today only
    s["post"]("/unavailabilities", {"room_id": s["room"]["id"],
                                    "start_date": iso(0), "end_date": iso(0)})
    moved = s["call"]("POST", f"/cases/{case['id']}/reschedule",
                      {"reason": "Salle 1 fermée", "keep_if_no_date": False}, status=201).json()
    assert moved == []
    assert s["call"]("GET", f"/cases/{case['id']}", status=200).json()["status"] == "cancelled"
    (row,) = s["call"]("GET", "/planning/deprogrammed", status=200).json()
    assert row["case_id"] == case["id"] and row["proposals"] == []


def test_a_disruption_does_not_exclude_the_date(s):
    # What remains open that day may still suit the patient, unlike a voluntary move
    case = s["book"](1)
    moved = s["call"]("POST", f"/cases/{case['id']}/reschedule",
                      {"reason": "Lit indisponible", "keep_if_no_date": False}, status=201).json()
    assert s["dates"](moved) == [iso(1)]
