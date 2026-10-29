from contextlib import asynccontextmanager
import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings, validate_runtime_settings
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
from app.repository import IncidentRepository
from app.schemas import IncidentCreate, IncidentResponse, TriageReviewRequest
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
) -> IncidentService:
    if settings.analyzer_backend == "fake":
        analyzer = FakeAnalyzer()
    elif settings.analyzer_backend == "ollama":
        analyzer = OllamaAnalyzer()
    else:
        raise AnalyzerConfigurationError(
            f"Unsupported analyzer backend: {settings.analyzer_backend}",
        )
    return IncidentService(IncidentRepository(session), analyzer)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "analyzer_backend": settings.analyzer_backend,
    }


@app.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_incident(
    incident: IncidentCreate,
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    return incident_service.create(incident)


@app.get("/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(
    incident_id: UUID,
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
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    try:
        return incident_service.analyze(incident_id)
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
    incident_service: IncidentService = Depends(get_incident_service),
) -> IncidentResponse:
    try:
        return incident_service.review(incident_id, review)
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
