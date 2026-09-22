from datetime import date, datetime, timezone
from typing import Optional, List
from sqlmodel import Field, Relationship, SQLModel
from uuid import UUID, uuid4
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB

class UserDB(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    surname: str
    email: str
    role: str
    validated: bool = Field(default=False)

class PatientDB(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    date_naissance: date
    sexe: int
    hospital_stays: List["HospitalStayDB"] = Relationship(back_populates="patient")

class OperatingRoomDB(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    equipment_type: str
    is_active: bool = Field(default=True)

class SurgeonDB(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: Optional[UUID] = Field(default=None, foreign_key="userdb.id")
    interventions: List["InterventionDB"] = Relationship(back_populates="surgeon")

class HospitalStayDB(SQLModel, table=True):
    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    patient_id: UUID = Field(foreign_key="patientdb.id")
    entry_date: date
    exit_date: Optional[date] = Field(default=None)
    is_ambulatory: bool = Field(default=False)
    
    patient: Optional[PatientDB] = Relationship(back_populates="hospital_stays")
    interventions: List["InterventionDB"] = Relationship(back_populates="stay")

class InterventionDB(SQLModel, table=True):
    uuid: UUID = Field(default_factory=uuid4, primary_key=True)
    owner: UUID = Field(foreign_key="surgeondb.id")
    patient_id: UUID = Field(foreign_key="patientdb.id")
    operating_room_id: Optional[UUID] = Field(default=None, foreign_key="operatingroomdb.id")
    stay_id: Optional[UUID] = Field(default=None, foreign_key="hospitalstaydb.uuid")
    
    start_date: date
    end_date: date
    duration: int
    diagnostic_principal: str
    emergency: bool
    
    ai_prediction: Optional[dict] = Field(default=None, sa_column=Column(JSONB))

    surgeon: Optional[SurgeonDB] = Relationship(back_populates="interventions")
    stay: Optional[HospitalStayDB] = Relationship(back_populates="interventions")
