from fastapi import APIRouter
from typing import List
from .schemas import OccupancyStats, OperatingRoomStatsResponse, AIAccuracyStats

router = APIRouter(
    prefix="/analytics",
    tags=["Statistiques & Tableaux de bord"],
)

@router.get("/occupancy", response_model=OccupancyStats)
async def get_occupancy():
    """Taux d'occupation global des lits et des places ambulatoires."""
    pass

@router.get("/operating_rooms", response_model=OperatingRoomStatsResponse)
async def get_operating_rooms_stats():
    """Taux d'utilisation des salles d'opération par période."""
    pass

@router.get("/ai_accuracy", response_model=AIAccuracyStats)
async def get_ai_accuracy():
    """Compare les durées prédites par l'IA aux durées réelles."""
    pass
