from pydantic import BaseModel, Field, model_validator
from typing import List
from uuid import UUID, uuid4
from people.schemas import Surgeon

class OperatingRoom(BaseModel):
    id: UUID = Field(default_factory=uuid4, description="Unique identifier for the operating room")
    name: str = Field(..., description="Name or number of the operating room", examples=["Salle 1"])
    equipment_type: str = Field(..., description="Type of equipment available in the room", examples=["General Surgery"])

class Structure(BaseModel):
    nom: str = Field(..., description="Name of the hospital or structure", examples=["Hôpital Central"])
    bed: int = Field(..., description="Number of standard beds available", examples=[100], gt=0)
    ambulatory: int = Field(..., description="Number of ambulatory places available", examples=[250], ge=0)
    staff: List[Surgeon] = Field(default_factory=list, description="List of surgeons working in the structure")
    operating_rooms: List[OperatingRoom] = Field(default_factory=list, description="List of operating rooms available")

    @model_validator(mode='after')
    def validate_ambulatory(self):
        if self.ambulatory < 2 * self.bed:
            raise ValueError("La capacité ambulatoire doit être au moins deux fois celle du nombre de lit")
        return self