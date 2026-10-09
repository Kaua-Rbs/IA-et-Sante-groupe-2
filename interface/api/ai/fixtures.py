"""Stand-ins for the prediction models and the optimisation solver.

They return deterministic, plausible values so the API and the frontend can be built
before the other teams deliver. Nothing here is fitted on the hospital data.
"""

import datetime as dt
import json
from functools import cache
from pathlib import Path

from api.ai.contracts import (
    Candidate, DurationPrediction, PredictionInput, SchedulingInput,
)
from api.resources.models import CareType

FIXTURES_FILE = Path(__file__).with_name("fixtures.json")


@cache
def _table() -> dict:
    return json.loads(FIXTURES_FILE.read_text(encoding="utf-8"))


def _base_values(inputs: PredictionInput) -> dict:
    table = _table()
    if inputs.intervention_type in table["by_intervention_type"]:
        return table["by_intervention_type"][inputs.intervention_type]
    return table["by_specialty"].get(inputs.specialty, table["default"])


def _is_elderly(inputs: PredictionInput) -> bool:
    return inputs.age >= _table()["elderly_age"]


class FixtureRoomDurationPredictor:
    model_version = _table()["model_version"]

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        minutes = _base_values(inputs)["room_minutes"]
        if _is_elderly(inputs):
            minutes *= _table()["elderly_room_factor"]
        minutes = round(minutes)
        return DurationPrediction(minutes, "minutes", (round(minutes * 0.8), round(minutes * 1.25)))


class FixtureLOSPredictor:
    model_version = _table()["model_version"]

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        days = _base_values(inputs)["los_days"]
        if _is_elderly(inputs) and days > 1:
            days += _table()["elderly_extra_days"]
        return DurationPrediction(days, "inclusive_calendar_days", (max(1, days - 1), days + 2))


class FixtureCareTypeClassifier:
    """Ambulatory when the predicted stay is a single day, as in the source data."""

    model_version = _table()["model_version"]

    def predict(self, inputs: PredictionInput) -> CareType:
        days = FixtureLOSPredictor().predict(inputs).value
        return CareType.ambulatory if days <= 1 else CareType.conventional


class GreedyFixtureScheduler:
    """Greedy baseline: scores each compatible vacation independently.

    Placeholder for the optimisation team's solver (tabu search, simulated annealing,
    genetic algorithm). It neither reorders existing cases nor plans several patients
    together, and ignores weekends and holidays.
    """

    name = "greedy-fixture"

    def propose(self, request: SchedulingInput, count: int) -> list[Candidate]:
        window_days = max(1, (request.latest_date - request.earliest_date).days)
        candidates: list[Candidate] = []
        for vacation in request.vacations:
            candidate = self._evaluate(request, vacation, window_days)
            if candidate is not None:
                candidates.append(candidate)
        candidates.sort(key=lambda c: (-c.score, c.admission_date, c.vacation_id))
        return _prefer_distinct_dates(candidates, count)

    def _evaluate(self, request, vacation, window_days) -> Candidate | None:
        if vacation.specialty_id != request.specialty_id:
            return None
        if vacation.surgeon_id not in (None, request.surgeon_id):
            return None
        if not request.earliest_date <= vacation.date <= request.latest_date:
            return None
        usable = vacation.duration_min * (1 - request.emergency_margin)
        if vacation.used_min + request.room_minutes > usable:
            return None

        admission = vacation.date
        discharge = admission + dt.timedelta(days=request.los_days - 1)
        stay = [admission + dt.timedelta(days=i) for i in range(request.los_days)]
        # Bed unit of the right care type with the lowest relative peak over the stay
        options = []
        for unit in request.bed_units:
            if unit.care_type != request.care_type:
                continue
            peak = max(unit.occupancy.get(day, 0) for day in stay) + 1
            if peak <= unit.capacity:
                options.append((peak / unit.capacity, unit.id, unit, peak))
        if not options:
            return None
        _, _, best_unit, best_peak = min(options)

        fill = (vacation.used_min + request.room_minutes) / vacation.duration_min
        bed_load = best_peak / best_unit.capacity
        delay = (vacation.date - request.earliest_date).days / window_days
        score = 0.5 * fill + 0.3 * (1 - bed_load) + 0.2 * (1 - delay)
        reasons = (
            f"Vacation du {vacation.date:%d/%m/%Y} en {vacation.room_name} : remplissage "
            f"{fill:.0%} après ajout ({request.room_minutes:.0f} min prévues).",
            f"{best_unit.name} : au plus {best_peak}/{best_unit.capacity} lits occupés "
            f"pendant le séjour ({request.los_days} j).",
            f"Marge de {request.emergency_margin:.0%} de la vacation préservée pour les urgences.",
        )
        return Candidate(vacation.id, best_unit.id, admission, discharge, round(score, 4), reasons)


def _prefer_distinct_dates(candidates: list[Candidate], count: int) -> list[Candidate]:
    """Best candidates first, but offer different dates before a second slot on the same day."""
    chosen: list[Candidate] = []
    seen_dates: set[dt.date] = set()
    for candidate in candidates:
        if candidate.admission_date not in seen_dates:
            chosen.append(candidate)
            seen_dates.add(candidate.admission_date)
        if len(chosen) == count:
            return chosen
    for candidate in candidates:
        if candidate not in chosen:
            chosen.append(candidate)
        if len(chosen) == count:
            break
    return chosen
