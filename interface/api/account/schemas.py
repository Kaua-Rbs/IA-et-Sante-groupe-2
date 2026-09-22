from typing import Literal
from uuid import UUID, uuid4
from enum import Enum
from pydantic import BaseModel, EmailStr, Field

# Différents roles : user (peut lire), medecin (peut saisir son planning), admin (peut gérer les utilisateurs)
class Roles(str, Enum):
    user = "user"
    doctor = "doctor"
    admin = "admin"

# Propriétés de base d'un utilisateur partagées avec la base de données
class UserBase(BaseModel):
    id: UUID = Field(default_factory=uuid4, description="Unique identifier of the user", examples=["123e4567-e89b-12d3-a456-426614174000"])
    name: str = Field(..., description="First name of the user", examples=["Thomas"])
    surname: str = Field(..., description="Last name of the user", examples=["Dupont"])
    email: EmailStr = Field(..., description="Email address used for authentication", examples=["thomas.dupont@example.com"])
    role: Roles = Field(Roles.user, description="Role of the user, defaults to user.")
    validated: bool = Field(False, description="Whether the user account has been validated by an admin.")

# Schéma pour la requête de connexion (/login)
class UserLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="Email address used for authentication", examples=["thomas.dupont@example.com"])
    password: str = Field(..., description="User's plain text password", examples=["strongpassword123"])

# Schéma pour la requête d'inscription (/register)
class UserRegisterRequest(UserBase):
    password: str = Field(..., description="Chosen plain text password", examples=["strongpassword123"])