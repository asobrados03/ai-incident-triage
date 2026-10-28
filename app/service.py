from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models import IncidentStatus
from app.schemas import IncidentCreate, IncidentResponse
from app.storage import IncidentStore


class IncidentService:
    def __init__(self, store: IncidentStore) -> None:
        self._store = store

    def create(self, data: IncidentCreate) -> IncidentResponse:
        incident = IncidentResponse(
            id=uuid4(),
            status=IncidentStatus.CREATED,
            created_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        return self._store.save(incident)

    def get(self, incident_id: UUID) -> IncidentResponse | None:
        return self._store.get(incident_id)
