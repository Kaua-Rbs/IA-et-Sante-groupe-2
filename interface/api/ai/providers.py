"""Select the prediction / scheduling implementations (FastAPI dependencies)."""

from dataclasses import dataclass
from functools import cache
from typing import Annotated

from fastapi import Depends

from api.ai.contracts import CareTypeClassifier, LOSPredictor, RoomDurationPredictor, Scheduler
from api.ai.fixtures import (
    FixtureCareTypeClassifier, FixtureLOSPredictor, FixtureRoomDurationPredictor,
    GreedyCapacityScheduler, GreedyFixtureScheduler,
)
from api.config import settings


@dataclass(frozen=True)
class Predictors:
    los: LOSPredictor
    room_duration: RoomDurationPredictor
    care_type: CareTypeClassifier


@cache
def get_predictors() -> Predictors:
    if settings.AI_BACKEND == "fixtures":
        return Predictors(
            FixtureLOSPredictor(), FixtureRoomDurationPredictor(), FixtureCareTypeClassifier(),
        )
    if settings.AI_BACKEND == "trained":
        from api.ai.trained import (
            PredictedStayCareTypeClassifier, TrainedLOSPredictor, TrainedRoomDurationPredictor,
        )
        los = TrainedLOSPredictor(settings.LOS_MODEL_PATH)
        return Predictors(los, TrainedRoomDurationPredictor(settings.ROOM_MODEL_PATH),
                          PredictedStayCareTypeClassifier(los))
    raise RuntimeError(f"Unknown AI_BACKEND {settings.AI_BACKEND!r}")


def get_scheduler() -> Scheduler:
    if settings.AI_BACKEND == "fixtures":
        return GreedyFixtureScheduler()
    if settings.AI_BACKEND == "trained":
        # Date A/B remains an individual, validated capacity search. The cohort
        # optimizer is exposed separately because its objective is collective.
        return GreedyCapacityScheduler()
    raise RuntimeError(f"Unknown AI_BACKEND {settings.AI_BACKEND!r}")


PredictorsDep = Annotated[Predictors, Depends(get_predictors)]
SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]
