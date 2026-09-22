from uuid import UUID
from typing import List
from fastapi import APIRouter
from .schemas import Event, Intervention, HospitalStay, MLPrediction

router = APIRouter(
    prefix="/event",
    tags=["Planning & Interventions"],
)

@router.get("/list", response_model=List[Event])
async def list_events():
    """Liste des événements (avec filtres par date, chirurgien, salle)."""
    pass

@router.get("/conflicts")
async def get_conflicts():
    """Détecte les conflits ou chevauchements dans les plannings."""
    pass

@router.post("/add", response_model=Event)
async def add_event(event: Event):
    """Ajoute un événement générique."""
    pass

@router.put("/update/{id}", response_model=Event)
async def update_event(id: UUID, event: Event):
    """Modifie un événement."""
    pass

@router.delete("/delete/{id}")
async def delete_event(id: UUID):
    """Supprime un événement."""
    pass

@router.post("/intervention/predict", response_model=MLPrediction)
async def predict_intervention(intervention: Intervention):
    """Appelle le modèle d'IA pour obtenir une prédiction de durée."""
    pass

@router.post("/intervention/feedback/{id}")
async def intervention_feedback(id: UUID, actual_duration: int):
    """Soumet la durée réelle post-opération pour l'IA."""
    pass

@router.post("/intervention/add", response_model=Intervention)
async def add_intervention(intervention: Intervention):
    """Planifie une intervention chirurgicale spécifique."""
    pass

@router.get("/hospital_stay/list", response_model=List[HospitalStay])
async def list_hospital_stays():
    """Liste les séjours hospitaliers en cours."""
    pass

@router.get("/hospital_stay/active", response_model=List[HospitalStay])
async def active_hospital_stays():
    """Liste uniquement les patients actuellement admis (occupant un lit)."""
    pass

@router.post("/hospital_stay/add", response_model=HospitalStay)
async def add_hospital_stay(stay: HospitalStay):
    """Crée un nouveau séjour (admission)."""
    pass

@router.put("/hospital_stay/update/{id}", response_model=HospitalStay)
async def update_hospital_stay(id: UUID, stay: HospitalStay):
    """Met à jour un séjour (ex: date de sortie)."""
    pass
