from fastapi import Depends
from sqlalchemy.orm import Session

from app.analyzers.core import (
    AnalyzerConfigurationError,
    FakeAnalyzer,
    OllamaAnalyzer,
)
from app.infrastructure.config import Settings, get_settings
from app.infrastructure.database import get_db_session
from app.infrastructure.repositories import (
    AuditRepository,
    IncidentRepository,
    RetentionRepository,
)
from app.services.incident import IncidentService
from app.services.retention import RetentionService


def get_incident_service(
    session: Session = Depends(get_db_session),
    runtime_settings: Settings = Depends(get_settings),
) -> IncidentService:
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
