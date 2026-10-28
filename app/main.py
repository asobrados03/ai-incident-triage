from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status

from app.config import get_settings
from app.schemas import IncidentCreate, IncidentResponse
from app.service import IncidentService
from app.storage import IncidentStore

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
store = IncidentStore()
service = IncidentService(store)


def get_incident_service() -> IncidentService:
    return service


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
