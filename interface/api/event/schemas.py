from pydantic import BaseModel, Field, field_validator, model_validator
from datetime import date
from typing import List, Optional
from uuid import UUID

class Event(BaseModel):
    uuid: UUID = Field(..., description="Unique identifier for the event", examples=["123e4567-e89b-12d3-a456-426614174000"])
    owner: UUID = Field(..., description="Surgeon ID: each event is related to a surgeon", examples=["987e6543-e21b-12d3-a456-426614174000"])
    start_date: date = Field(..., description="Start date of the event", examples=["2026-10-01"])
    end_date: date = Field(..., description="End date of the event", examples=["2026-10-05"])
    duration: int = Field(..., description="Duration of the event in days", examples=[4])

    @field_validator('duration')
    @classmethod
    def validate_duration(cls, v):
        if v <= 0:
            raise ValueError("Duration must be greater than 0")
        return v
        
    @model_validator(mode='after')
    def check_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("End date cannot be before start date")
        return self

class MLPrediction(BaseModel):
    predicted_duration: int = Field(..., description="Predicted duration of the intervention in minutes", examples=[120])
    confidence_score: float = Field(..., description="Confidence score of the prediction (0.0 to 1.0)", examples=[0.85], ge=0.0, le=1.0)
    model_version: str = Field(..., description="Version of the ML model used", examples=["v1.2.0"])

class Intervention(Event):
    # Basic info
    diagnostic_principal: str = Field(..., description="Primary diagnosis for the intervention", examples=["Appendicitis"])
    emergency: bool = Field(..., description="Indicates if the intervention is an emergency", examples=[True])
    patient_id: UUID = Field(..., description="ID of the patient undergoing the intervention", examples=["321e4567-e89b-12d3-a456-426614174000"])
    operating_room_id: UUID = Field(..., description="ID of the operating room where the intervention takes place")
    ai_prediction: Optional[MLPrediction] = Field(None, description="AI-generated predictions for this intervention")

class HospitalStay(BaseModel):
    uuid: UUID = Field(..., description="Unique identifier for the hospital stay", examples=["123e4567-e89b-12d3-a456-426614174000"])
    patient_id: UUID = Field(..., description="ID of the patient", examples=["321e4567-e89b-12d3-a456-426614174000"])
    entry_date: date = Field(..., description="Date the patient entered the hospital", examples=["2026-10-01"])
    exit_date: Optional[date] = Field(None, description="Date the patient left the hospital, null if still admitted", examples=["2026-10-05"])
    is_ambulatory: bool = Field(False, description="Whether the stay is ambulatory (same-day discharge)")
    interventions: List[Intervention] = Field(default_factory=list, description="List of interventions during this stay")

    @model_validator(mode='after')
    def check_stay_dates(self):
        if self.exit_date and self.exit_date < self.entry_date:
            raise ValueError("Exit date cannot be before entry date")
        return self
