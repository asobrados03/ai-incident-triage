from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models import IncidentStatus
from app.repository import IncidentRepository
from app.schemas import IncidentCreate, IncidentResponse


class IncidentService:
    def __init__(self, repository: IncidentRepository) -> None:
        self._repository = repository

    def create(self, data: IncidentCreate) -> IncidentResponse:
        incident = IncidentResponse(
            id=uuid4(),
            status=IncidentStatus.CREATED,
            created_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        return self._repository.create(incident)

    def get(self, incident_id: UUID) -> IncidentResponse | None:
        return self._repository.get(incident_id)
