import datetime as dt

from api.ai.contracts import BedUnitLoad, PredictionInput, SchedulingInput, VacationSlot
from api.ai.fixtures import (
    FixtureCareTypeClassifier, FixtureLOSPredictor, GreedyFixtureScheduler,
)
from api.resources.models import CareType

MONDAY = dt.date(2030, 1, 7)


def request(vacations, beds_capacity=10, margin=0.1):
    return SchedulingInput(
        specialty_id=1, surgeon_id=1, room_minutes=95, los_days=3,
        care_type=CareType.conventional, earliest_date=MONDAY,
        latest_date=MONDAY + dt.timedelta(days=14), vacations=tuple(vacations),
        bed_units=(BedUnitLoad(1, "Chirurgie", CareType.conventional, beds_capacity),),
        emergency_margin=margin,
    )


def slot(vacation_id, days, used=0, specialty_id=1, surgeon_id=None):
    return VacationSlot(vacation_id, MONDAY + dt.timedelta(days=days), "Salle 1",
                        specialty_id, surgeon_id, 240, used)


def test_emergency_margin_is_kept():
    # 130 + 95 = 225 min fits in 240, but not in the 216 left by a 10 % margin
    assert GreedyFixtureScheduler().propose(request([slot(1, 0, used=130)]), 2) == []
    assert len(GreedyFixtureScheduler().propose(request([slot(1, 0, used=130)], margin=0), 2)) == 1


def test_other_specialties_and_surgeons_are_ignored():
    vacations = [slot(1, 0, specialty_id=2), slot(2, 1, surgeon_id=99), slot(3, 2)]
    assert [c.vacation_id for c in GreedyFixtureScheduler().propose(request(vacations), 2)] == [3]


def test_fuller_vacation_is_preferred():
    candidates = GreedyFixtureScheduler().propose(request([slot(1, 0), slot(2, 0, used=100)]), 1)
    assert candidates[0].vacation_id == 2


def test_single_day_stays_are_ambulatory():
    inputs = PredictionInput(age=40, sex=1, principal_diagnosis="I83.9", ccam_codes=("EJFA002",),
                             specialty="Chirurgie vasculaire", intervention_type="Varices")
    assert FixtureLOSPredictor().predict(inputs).value == 1
    assert FixtureCareTypeClassifier().predict(inputs) == CareType.ambulatory
