from uuid import UUID
from typing import List
from fastapi import APIRouter
from account.schemas import UserBase
from .schemas import Structure, OperatingRoom

router = APIRouter(
    prefix="/configuration",
    tags=["Configuration & Administration"],
)

@router.get("/users", response_model=List[UserBase])
async def get_all_users():
    """Liste tous les utilisateurs (pour validation)."""
    pass

@router.put("/user/update/{id}", response_model=UserBase)
async def update_user(id: UUID, user_data: UserBase):
    """Modification d'un utilisateur par l'admin."""
    pass

@router.patch("/user/approve/{id}", response_model=UserBase)
async def approve_user(id: UUID):
    """Approuve un utilisateur en attente."""
    pass

@router.delete("/user/delete/{id}")
async def delete_user(id: UUID):
    """Supprime un utilisateur."""
    pass

@router.get("/structure", response_model=Structure)
async def get_structure():
    """Récupère la configuration globale de l'établissement."""
    pass

@router.put("/structure/update", response_model=Structure)
async def update_structure(structure: Structure):
    """Met à jour la configuration de la structure."""
    pass

@router.get("/operating_rooms", response_model=List[OperatingRoom])
async def list_operating_rooms():
    """Liste les salles d'opération."""
    pass

@router.post("/operating_room/add", response_model=OperatingRoom)
async def add_operating_room(room: OperatingRoom):
    """Ajoute une nouvelle salle d'opération."""
    pass

@router.put("/operating_room/update/{id}", response_model=OperatingRoom)
async def update_operating_room(id: UUID, room: OperatingRoom):
    """Modifie une salle d'opération."""
    pass

@router.delete("/operating_room/delete/{id}")
async def delete_operating_room(id: UUID):
    """Supprime ou désactive une salle."""
    pass
