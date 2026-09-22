from uuid import UUID
from fastapi import APIRouter
from .schemas import UserBase, UserLoginRequest, UserRegisterRequest

router = APIRouter(
    prefix="/account",
    tags=["Compte Utilisateur"],
)

@router.post("/login")
async def login(credentials: UserLoginRequest):
    """Connexion."""
    pass

@router.post("/register", response_model=UserBase)
async def register(user: UserRegisterRequest):
    """Inscription d'un nouvel utilisateur."""
    pass

@router.get("/me", response_model=UserBase)
async def get_connected_profile():
    """Récupérer son propre profil."""
    pass

@router.put("/me/update", response_model=UserBase)
async def update_my_profile(user_update: UserBase):
    """Mettre à jour son propre profil."""
    pass
