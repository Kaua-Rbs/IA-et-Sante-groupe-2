import logging
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter
from slowapi.util import get_remote_address

# interface/kyst.env is the reference for every variable (API, frontend, deployment);
# interface/kyst.local.env, not versioned, overrides it with real secrets.
# Process environment variables take precedence over both files.
INTERFACE_DIR = Path(__file__).resolve().parent.parent
ENV_FILES = (INTERFACE_DIR / "kyst.env", INTERFACE_DIR / "kyst.local.env")

PLACEHOLDER_SECRET = "change-me"

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings, documented in interface/kyst.env."""

    model_config = SettingsConfigDict(env_file=ENV_FILES, env_file_encoding="utf-8", extra="ignore")

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite:///kyst.db"
    # Origins allowed to call the API from a browser (the SvelteKit server calls it directly)
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    RATE_LIMIT_ENABLED: bool = True
    # Accounts: when True, a new account must be validated by an admin before it can log in
    ACCOUNT_VALIDATION: bool = True
    # Optional first administrator, created at startup if no user has this email yet
    FIRST_ADMIN_EMAIL: str | None = None
    FIRST_ADMIN_PASSWORD: str | None = None
    # Prediction and scheduling backend: only "fixtures" exists until the models are delivered
    AI_BACKEND: str = "fixtures"
    # Scheduling: share of each vacation kept free for emergencies, proposals per request,
    # and how far after the earliest date to look when the request has no deadline
    EMERGENCY_MARGIN: float = 0.1
    PROPOSAL_COUNT: int = 2
    SCHEDULING_HORIZON_DAYS: int = 60


settings = Settings()

if settings.SECRET_KEY == PLACEHOLDER_SECRET:
    logger.warning(
        "SECRET_KEY still has its placeholder value: set a real key in kyst.local.env "
        "or in the environment before any shared deployment"
    )

# Rate limiter (shared across routers)
limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)
