from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import IncidentStatus
from app.orm_models import IncidentORM
from app.schemas import IncidentResponse


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, incident: IncidentResponse) -> IncidentResponse:
        record = IncidentORM(
            id=str(incident.id),
            status=incident.status.value,
            created_at=incident.created_at,
            **incident.model_dump(
                exclude={"id", "status", "created_at"},
            ),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_response(record)

    def get(self, incident_id: UUID) -> IncidentResponse | None:
        record = self._session.scalar(
            select(IncidentORM).where(IncidentORM.id == str(incident_id)),
        )
        return self._to_response(record) if record is not None else None

    @staticmethod
    def _to_response(record: IncidentORM) -> IncidentResponse:
        return IncidentResponse(
            id=UUID(record.id),
            title=record.title,
            description=record.description,
            steps_to_reproduce=record.steps_to_reproduce,
            expected_behavior=record.expected_behavior,
            actual_behavior=record.actual_behavior,
            environment=record.environment,
            components=record.components,
            status=IncidentStatus(record.status),
            created_at=record.created_at,
        )
