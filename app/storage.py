from uuid import UUID

from app.schemas import IncidentResponse


class IncidentStore:
    def __init__(self) -> None:
        self._incidents: dict[UUID, IncidentResponse] = {}

    def save(self, incident: IncidentResponse) -> IncidentResponse:
        self._incidents[incident.id] = incident
        return incident

    def get(self, incident_id: UUID) -> IncidentResponse | None:
        return self._incidents.get(incident_id)
