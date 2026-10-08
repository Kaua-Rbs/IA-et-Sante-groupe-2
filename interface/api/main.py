from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api import __version__
from api.accounts.router import router as accounts_router
from api.analytics.router import router as analytics_router
from api.bootstrap import init_db
from api.clinical.router import router as clinical_router
from api.config import limiter, settings
from api.planning.router import router as planning_router
from api.resources.router import router as resources_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="KYST API",
    summary="Keep Your Surgeries Timelies",
    description="Orchestration du bloc opératoire et des lits : demandes d'intervention, "
    "prédictions, propositions de dates et validation humaine.",
    version=__version__,
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

app.include_router(accounts_router)
app.include_router(resources_router)
app.include_router(clinical_router)
app.include_router(planning_router)
app.include_router(analytics_router)


@app.get("/health", tags=["meta"])
def health():
    return {
        "status": "ok",
        "name": "KYST",
        "version": __version__,
        "ai_backend": settings.AI_BACKEND,
        "emergency_margin": settings.EMERGENCY_MARGIN,
        "proposal_count": settings.PROPOSAL_COUNT,
    }
