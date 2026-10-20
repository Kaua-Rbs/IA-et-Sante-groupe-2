"""Stand-in predictors for the API tests, which run without the trained artifacts.

Deterministic values by specialty; nothing here is fitted on hospital data.
"""

from api.ai.contracts import DurationPrediction, PredictionInput
from api.ai.providers import Predictors
from api.ai.trained import PredictedStayCareTypeClassifier

MODEL_VERSION = "test-stub"
DEFAULT = {"room_minutes": 75, "los_days": 3}
BY_SPECIALTY = {
    "Orthopédie": {"room_minutes": 95, "los_days": 4},
    "Digestif": {"room_minutes": 110, "los_days": 5},
    "Urologie": {"room_minutes": 70, "los_days": 2},
    "ORL": {"room_minutes": 55, "los_days": 1},
}
BY_INTERVENTION_TYPE = {"Varices": {"room_minutes": 45, "los_days": 1}}
ELDERLY_AGE = 75


def _values(inputs: PredictionInput) -> dict:
    if inputs.intervention_type in BY_INTERVENTION_TYPE:
        return BY_INTERVENTION_TYPE[inputs.intervention_type]
    return BY_SPECIALTY.get(inputs.specialty, DEFAULT)


class StubRoomDurationPredictor:
    model_version = MODEL_VERSION

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        minutes = _values(inputs)["room_minutes"]
        if inputs.age >= ELDERLY_AGE:
            minutes = round(minutes * 1.1)
        return DurationPrediction(minutes, "minutes", (round(minutes * 0.8), round(minutes * 1.25)))


class StubLOSPredictor:
    model_version = MODEL_VERSION

    def predict(self, inputs: PredictionInput) -> DurationPrediction:
        days = _values(inputs)["los_days"]
        if inputs.age >= ELDERLY_AGE and days > 1:
            days += 1
        return DurationPrediction(days, "inclusive_calendar_days", (max(1, days - 1), days + 2))


def stub_predictors() -> Predictors:
    los = StubLOSPredictor()
    return Predictors(los, StubRoomDurationPredictor(), PredictedStayCareTypeClassifier(los),
                      source="test-stub")
