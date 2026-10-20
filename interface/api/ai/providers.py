"""Select the prediction / scheduling implementations (FastAPI dependencies)."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from api.ai.contracts import CareTypeClassifier, LOSPredictor, RoomDurationPredictor, Scheduler
from api.ai.scheduler import GreedyCapacityScheduler
from api.config import settings


@dataclass(frozen=True)
class Predictors:
    los: LOSPredictor
    room_duration: RoomDurationPredictor
    care_type: CareTypeClassifier
    source: str = "trained"  # stored with each prediction


# Loaded once, on first use. The API tests replace it with stand-ins.
_predictors: Predictors | None = None


def get_predictors() -> Predictors:
    global _predictors
    if _predictors is None:
        from api.ai.trained import (
            PredictedStayCareTypeClassifier, TrainedLOSPredictor, TrainedRoomDurationPredictor,
        )
        los = TrainedLOSPredictor(settings.LOS_MODEL_PATH)
        _predictors = Predictors(los, TrainedRoomDurationPredictor(settings.ROOM_MODEL_PATH),
                                 PredictedStayCareTypeClassifier(los))
    return _predictors


def get_scheduler() -> Scheduler:
    # Date A/B remains an individual, validated capacity search. The cohort
    # optimizer is exposed separately because its objective is collective.
    return GreedyCapacityScheduler()


PredictorsDep = Annotated[Predictors, Depends(get_predictors)]
SchedulerDep = Annotated[Scheduler, Depends(get_scheduler)]
