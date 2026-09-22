from pydantic import BaseModel, Field
from typing import List
from uuid import UUID

class OccupancyStats(BaseModel):
    total_beds: int = Field(..., description="Total standard beds available", examples=[100])
    occupied_beds: int = Field(..., description="Currently occupied beds", examples=[85])
    bed_occupancy_rate: float = Field(..., description="Percentage of standard beds occupied (0.0 to 1.0)", examples=[0.85])
    total_ambulatory: int = Field(..., description="Total ambulatory places available", examples=[250])
    occupied_ambulatory: int = Field(..., description="Currently occupied ambulatory places", examples=[150])
    ambulatory_occupancy_rate: float = Field(..., description="Percentage of ambulatory places occupied (0.0 to 1.0)", examples=[0.60])

class OperatingRoomStat(BaseModel):
    room_id: UUID = Field(..., description="Operating room identifier")
    room_name: str = Field(..., description="Name of the room", examples=["Salle 1"])
    total_interventions: int = Field(..., description="Number of interventions in the period", examples=[12])
    utilization_rate: float = Field(..., description="Percentage of time the room was in use during open hours", examples=[0.75])

class OperatingRoomStatsResponse(BaseModel):
    period_days: int = Field(..., description="Number of days in the analysis period", examples=[7])
    rooms: List[OperatingRoomStat] = Field(default_factory=list, description="Statistics per operating room")

class AIAccuracyStats(BaseModel):
    total_predictions: int = Field(..., description="Total number of evaluated ML predictions", examples=[500])
    average_error_minutes: float = Field(..., description="Average absolute error between predicted and actual duration in minutes", examples=[12.5])
    accuracy_percentage: float = Field(..., description="Overall accuracy percentage", examples=[0.92])
    overestimated_count: int = Field(..., description="Number of times the AI predicted a longer duration than reality", examples=[200])
    underestimated_count: int = Field(..., description="Number of times the AI predicted a shorter duration than reality", examples=[300])
