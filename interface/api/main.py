from fastapi import FastAPI

from event.routeurs import router as event_router
from people.routeurs import router as patient_router
from account.routeurs import router as account_router
from analytics.routeurs import router as analytics_router
from data.routeurs import router as data_router
from configuration.routeurs import router as configuration_router

app = FastAPI(
    title="IAS API",
    description="API de planification hospitalière avec IA",
    version="1.0.0",
)

# Route d'accueil simple pour vérifier que l'API tourne
@app.get("/")
async def root():
    return {"message": "Bienvenue sur l'API IAS"}

# Routeurs
app.include_router(account_router, prefix="/api")
app.include_router(configuration_router, prefix="/api")
app.include_router(event_router, prefix="/api")
app.include_router(patient_router, prefix="/api")
app.include_router(analytics_router, prefix="/api")
app.include_router(data_router, prefix="/api")
