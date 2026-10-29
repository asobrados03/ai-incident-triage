from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import create_tables, engine, get_db_session
from app.analyzer import FakeAnalyzer
from app.repository import IncidentRepository
from app.schemas import IncidentCreate, IncidentResponse
from app.service import (
    IncidentAnalysisConflictError,
    IncidentNotFoundError,
    IncidentService,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
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
    return IncidentService(IncidentRepository(session), FakeAnalyzer())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
