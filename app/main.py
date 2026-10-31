from contextlib import asynccontextmanager
import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import Principal, Role, require_role
from app.config import Settings, get_settings, validate_runtime_settings
from app.database import create_tables, engine, get_db_session
from app.logging_config import configure_logging
from app.analyzer import (
    AnalyzerConfigurationError,
    AnalyzerProviderUnavailableError,
    AnalyzerResponseError,
    AnalyzerTimeoutError,
    FakeAnalyzer,
    OllamaAnalyzer,
)
from app.repository import AuditRepository, IncidentRepository, RetentionRepository
from app.retention import RetentionService
from app.schemas import (
    AuditLogPage,
    IncidentCreate,
    IncidentResponse,
    RetentionRunRequest,
    RetentionRunResponse,
    TriageReviewRequest,
)
from app.service import (
    IncidentAnalysisConflictError,
    IncidentNotFoundError,
    IncidentReviewConflictError,
    IncidentService,
)

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


@app.get("/health")
def health(
    runtime_settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    return {
        "status": "ok",
        "analyzer_backend": runtime_settings.analyzer_backend,
    }


@app.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    incident: IncidentCreate,
    principal: Principal = Depends(require_role(Role.WRITER)),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    return incident_service.create(incident, actor=principal)


@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: UUID,
    _principal: Principal = Depends(require_role(Role.READER)),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    incident = incident_service.get(incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        )
    return incident


@app.post(
    "/incidents/{incident_id}/analysis",
    response_model=IncidentResponse,
)
def analyze_incident(
    incident_id: UUID,
    principal: Principal = Depends(require_role(Role.WRITER)),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    try:
        return incident_service.analyze(incident_id, actor=principal)
    except IncidentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        ) from error
    except IncidentAnalysisConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except AnalyzerTimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Analyzer provider timed out",
        ) from error
    except (
        AnalyzerProviderUnavailableError,
        AnalyzerResponseError,
        AnalyzerConfigurationError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "Analyzer provider unavailable"
                if isinstance(error, AnalyzerProviderUnavailableError)
                else "Analyzer provider returned an invalid response"
                if isinstance(error, AnalyzerResponseError)
                else "Invalid analyzer configuration"
            ),
        ) from error


@app.patch(
    "/incidents/{incident_id}/triage",
    response_model=IncidentResponse,
)
def review_incident_triage(
    incident_id: UUID,
    review: TriageReviewRequest,
    principal: Principal = Depends(require_role(Role.WRITER)),
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    try:
        return incident_service.review(incident_id, review, actor=principal)
    except IncidentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Incident not found",
        ) from error
    except IncidentReviewConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error


@app.get("/audit", response_model=AuditLogPage)
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=100),
    actor: str | None = Query(default=None, max_length=100),
    resource_type: str | None = Query(default=None, max_length=50),
    resource_id: str | None = Query(default=None, max_length=100),
    _principal: Principal = Depends(require_role(Role.ADMIN)),
    audit_repository: AuditRepository = Depends(get_audit_repository),
) -> AuditLogPage:
    items, total = audit_repository.list(
        limit=limit,
        offset=offset,
        action=action,
        actor=actor,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    return AuditLogPage(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@app.post("/admin/retention", response_model=RetentionRunResponse)
def run_retention(
    request: RetentionRunRequest,
    principal: Principal = Depends(require_role(Role.ADMIN)),
    retention_service: RetentionService = Depends(get_retention_service),
) -> RetentionRunResponse:
    return retention_service.run(
        actor=principal,
        dry_run=request.dry_run,
        incidents_days=request.incidents_days,
        audit_days=request.audit_days,
    )
