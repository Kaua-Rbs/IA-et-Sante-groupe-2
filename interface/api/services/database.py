import os
from sqlmodel import create_engine, Session
from dotenv import load_dotenv

# Charge les variables d'environnement depuis le fichier .env
load_dotenv()

DB_USER = os.getenv("DB_USER", "ias")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secretpassword")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "ias_db")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Essaye de créer le moteur de base de données (PostgreSQL ou fallback SQLite)
try:
    engine = create_engine(DATABASE_URL, echo=False)
except Exception:
    engine = create_engine("sqlite:///ias.db", echo=False)

def get_session():
    """Générateur de session pour l'injection de dépendances FastAPI."""
    with Session(engine) as session:
        yield session
