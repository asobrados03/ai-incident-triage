from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.dependencies import get_incident_service
from app.api.routes import router
from app.infrastructure.config import (
    get_settings,
    validate_runtime_settings,
)
from app.infrastructure.database import create_tables, engine
from app.logging_config import configure_logging

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
app.include_router(router)

__all__ = ["app", "get_incident_service"]
