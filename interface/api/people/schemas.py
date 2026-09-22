from pydantic import BaseModel, Field, field_validator
from datetime import date
from typing import Optional, List
from uuid import UUID
from event.schemas import Event, Intervention, HospitalStay

class Patient(BaseModel):
    id: UUID = Field(..., description="Anonymized patient identifier", examples=["123e4567-e89b-12d3-a456-426614174000"])
    date_naissance: date = Field(..., description="Patient's date of birth", examples=["1990-05-15"])
    sexe: int = Field(..., description="1 for male, 2 for female", examples=[1])
    
    hospital_stays: List[HospitalStay] = Field(default_factory=list, description="List of hospital stays for this patient")

    @field_validator('sexe')
    @classmethod
    def validate_sexe(cls, v):
        if v not in (1, 2):
            raise ValueError("Sexe must be 1 (male) or 2 (female)")
        return v
        
    @field_validator('date_naissance')
    @classmethod
    def validate_dob(cls, v):
        if v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v

class Surgeon(BaseModel):
    id: UUID = Field(..., description="Unique identifier of the surgeon", examples=["987e6543-e21b-12d3-a456-426614174000"])
    user_id: Optional[UUID] = Field(None, description="Linked user account ID for authentication", examples=["111e4567-e89b-12d3-a456-426614174000"])
    timetable: List[Event] = Field(default_factory=list, description="List of scheduled events for the surgeon")
    interventions: List[Intervention] = Field(default_factory=list, description="List of interventions/cases associated with the surgeon")
