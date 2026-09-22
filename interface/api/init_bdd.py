from sqlmodel import SQLModel
from services.database import engine

# Importation des tables pour qu'elles soient enregistrées dans le registre SQLModel
from services.db import (
    UserDB, 
    PatientDB, 
    OperatingRoomDB, 
    SurgeonDB, 
    HospitalStayDB, 
    InterventionDB
)

def init_db():
    print("Initialisation de la base de données...")
    SQLModel.metadata.create_all(engine)
    print("Création des tables terminée avec succès !")

if __name__ == "__main__":
    init_db()
