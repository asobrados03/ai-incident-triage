from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.dependencies import get_incident_service
from backend.api.frontend import mount_frontend
from backend.api.routes import router
from backend.security.auth import parse_auth_users
from backend.infrastructure.config import (
    get_cors_origins,
    get_settings,
    validate_runtime_settings,
)
from backend.infrastructure.database import SessionLocal, create_tables, engine
from backend.infrastructure.repositories import AuditRepository, UserRepository
from backend.logging_config import configure_logging
from backend.services.users import UserService

settings = get_settings()
logger = logging.getLogger(__name__)


def bootstrap_users() -> int:
    """Siembra la tabla users desde AUTH_USERS si hay usuarios nuevos."""
    seed = parse_auth_users(settings.auth_users)
    if not seed:
        return 0
    session = SessionLocal()
    try:
        service = UserService(UserRepository(session), AuditRepository(session))
        return service.bootstrap(seed)
    finally:
        session.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    validate_runtime_settings(settings)
    if settings.allow_anonymous_bootstrap:
        logger.warning(
            "anonymous_bootstrap_enabled",
            extra={
                "auth_users_configured": bool(
                    settings.auth_users.get_secret_value().strip(),
                ),
            },
        )
    create_tables(engine)
    created = bootstrap_users()
    if created:
        logger.info("auth_users_bootstrapped", extra={"created": created})
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
mount_frontend(app)

__all__ = ["app", "get_incident_service"]
