from uuid import UUID
from typing import List
from fastapi import APIRouter
from .schemas import Patient, Surgeon
from event.schemas import Event

router = APIRouter(
    prefix="/people",
    tags=["Gestion des acteurs"],
)

@router.get("/patient/list", response_model=List[Patient])
async def list_patients():
    """Recherche / Liste des patients."""
    pass

@router.get("/patient/{id}", response_model=Patient)
async def get_patient(id: UUID):
    """Détails d'un patient (historique et séjours)."""
    pass

@router.post("/patient/add", response_model=Patient)
async def add_patient(patient: Patient):
    """Ajout d'un patient."""
    pass

@router.put("/patient/update/{id}", response_model=Patient)
async def update_patient(id: UUID, patient: Patient):
    """Mise à jour du dossier patient."""
    pass

@router.delete("/patient/delete/{id}")
async def delete_patient(id: UUID):
    """Suppression d'un patient."""
    pass

@router.get("/surgeon/list", response_model=List[Surgeon])
async def list_surgeons():
    """Liste des chirurgiens."""
    pass

@router.get("/surgeon/{id}", response_model=Surgeon)
async def get_surgeon(id: UUID):
    """Détails d'un chirurgien et son emploi du temps."""
    pass

@router.get("/surgeon/{id}/availability", response_model=List[Event])
async def surgeon_availability(id: UUID):
    """Trouve les créneaux libres pour un chirurgien."""
    pass

@router.post("/surgeon/add", response_model=Surgeon)
async def add_surgeon(surgeon: Surgeon):
    """Ajout d'un chirurgien (et liaison avec un user_id)."""
    pass

@router.put("/surgeon/update/{id}", response_model=Surgeon)
async def update_surgeon(id: UUID, surgeon: Surgeon):
    """Mise à jour d'un chirurgien."""
    pass

@router.delete("/surgeon/delete/{id}")
async def delete_surgeon(id: UUID):
    """Suppression d'un chirurgien."""
    pass
