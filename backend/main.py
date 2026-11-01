from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.dependencies import get_incident_service
from backend.api.routes import router
from backend.infrastructure.config import (
    get_cors_origins,
    get_settings,
    validate_runtime_settings,
)
from backend.infrastructure.database import create_tables, engine
from backend.logging_config import configure_logging

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    validate_runtime_settings(settings)
    create_tables(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

__all__ = ["app", "get_incident_service"]
