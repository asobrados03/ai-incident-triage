import threading

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.analyzers.core import (
    AnalyzerConfigurationError,
    FakeAnalyzer,
    IncidentAnalyzer,
    OllamaAnalyzer,
)
from backend.infrastructure.config import Settings, get_settings
from backend.infrastructure.database import get_db_session
from backend.infrastructure.repositories import (
    AuditRepository,
    IncidentRepository,
    RetentionRepository,
    UserRepository,
)
from backend.security.login_throttle import LoginThrottle
from backend.services.incident import IncidentService
from backend.services.retention import RetentionService
from backend.services.users import UserService

_login_throttles: dict[tuple[int, float], LoginThrottle] = {}
_login_throttles_lock = threading.Lock()


def get_login_throttle(
    runtime_settings: Settings = Depends(get_settings),
) -> LoginThrottle:
    key = (
        runtime_settings.login_max_attempts,
        runtime_settings.login_window_seconds,
    )
    with _login_throttles_lock:
        throttle = _login_throttles.get(key)
        if throttle is None:
            throttle = LoginThrottle(
                max_attempts=key[0],
                window_seconds=key[1],
            )
            _login_throttles[key] = throttle
        return throttle


def reset_login_throttle() -> None:
    """Descarta los limitadores en memoria; solo para tests y reinicios."""
    with _login_throttles_lock:
        _login_throttles.clear()


def get_incident_service(
    session: Session = Depends(get_db_session),
    runtime_settings: Settings = Depends(get_settings),
) -> IncidentService:
    analyzer: IncidentAnalyzer
    if runtime_settings.analyzer_backend == "fake":
        analyzer = FakeAnalyzer()
    elif runtime_settings.analyzer_backend == "ollama":
        analyzer = OllamaAnalyzer()
    else:
        raise AnalyzerConfigurationError(
            f"Unsupported analyzer backend: {runtime_settings.analyzer_backend}",
        )
    return IncidentService(
        IncidentRepository(session),
        analyzer,
        AuditRepository(session),
    )


def get_audit_repository(
    session: Session = Depends(get_db_session),
) -> AuditRepository:
    return AuditRepository(session)


def get_incident_repository(
    session: Session = Depends(get_db_session),
) -> IncidentRepository:
    return IncidentRepository(session)


def get_retention_service(
    session: Session = Depends(get_db_session),
    runtime_settings: Settings = Depends(get_settings),
) -> RetentionService:
    return RetentionService(
        RetentionRepository(session),
        AuditRepository(session),
        runtime_settings.retention_days,
        runtime_settings.audit_retention_days,
    )


def get_user_repository(
    session: Session = Depends(get_db_session),
) -> UserRepository:
    return UserRepository(session)


def get_user_service(
    session: Session = Depends(get_db_session),
) -> UserService:
    return UserService(
        UserRepository(session),
        AuditRepository(session),
    )
