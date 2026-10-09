"""Select the prediction / scheduling implementations (FastAPI dependencies)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from api.ai.contracts import CareTypeClassifier, LOSPredictor, RoomDurationPredictor, Scheduler
from api.ai.fixtures import (
    FixtureCareTypeClassifier, FixtureLOSPredictor, FixtureRoomDurationPredictor,
    GreedyFixtureScheduler,
)
from api.config import settings


@dataclass(frozen=True)
class Predictors:
    los: LOSPredictor
    room_duration: RoomDurationPredictor
    care_type: CareTypeClassifier


def get_predictors() -> Predictors:
    if settings.AI_BACKEND == "fixtures":
        return Predictors(
            FixtureLOSPredictor(), FixtureRoomDurationPredictor(), FixtureCareTypeClassifier(),
        )
    raise RuntimeError(f"Unknown AI_BACKEND {settings.AI_BACKEND!r}")


def get_scheduler() -> Scheduler:
    if settings.AI_BACKEND == "fixtures":
        return GreedyFixtureScheduler()
    raise RuntimeError(f"Unknown AI_BACKEND {settings.AI_BACKEND!r}")


PredictorsDep = Annotated[Predictors, Depends(get_predictors)]
SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]
