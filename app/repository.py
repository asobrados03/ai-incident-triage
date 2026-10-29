from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AnalysisConfidence,
    IncidentCategory,
    IncidentPriority,
    IncidentSeverity,
    IncidentStatus,
)
from app.orm_models import IncidentORM, TriageResultORM
from app.schemas import IncidentResponse, TriageResult, TriageResultResponse


class IncidentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, incident: IncidentResponse) -> IncidentResponse:
        record = IncidentORM(
            id=str(incident.id),
            status=incident.status.value,
            created_at=incident.created_at,
            **incident.model_dump(
                exclude={"id", "status", "created_at", "triage"},
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
        if record is None:
            return None
        return self._to_response(record, self.get_triage(incident_id))

    @staticmethod
    def _to_response(
        record: IncidentORM,
        triage: TriageResultResponse | None = None,
    ) -> IncidentResponse:
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
            triage=triage,
        )

    def get_status(self, incident_id: UUID) -> IncidentStatus | None:
        value = self._session.scalar(
            select(IncidentORM.status).where(IncidentORM.id == str(incident_id)),
        )
        return IncidentStatus(value) if value is not None else None

    def set_status(self, incident_id: UUID, incident_status: IncidentStatus) -> None:
        record = self._session.get(IncidentORM, str(incident_id))
        if record is None:
            return
        record.status = incident_status.value
        self._session.commit()

    def get_triage(self, incident_id: UUID) -> TriageResultResponse | None:
        record = self._session.scalar(
            select(TriageResultORM).where(
                TriageResultORM.incident_id == str(incident_id),
            ),
        )
        return self._to_triage_response(record) if record is not None else None

    def create_triage(
        self,
        incident_id: UUID,
        result: TriageResult,
    ) -> TriageResultResponse:
        record = TriageResultORM(
            id=str(uuid4()),
            incident_id=str(incident_id),
            created_at=datetime.now(timezone.utc),
            **result.model_dump(mode="json"),
        )
        self._session.add(record)
        self._session.commit()
        self._session.refresh(record)
        return self._to_triage_response(record)

    @staticmethod
    def _to_triage_response(record: TriageResultORM) -> TriageResultResponse:
        return TriageResultResponse(
            id=UUID(record.id),
            category=IncidentCategory(record.category),
            severity=IncidentSeverity(record.severity),
            priority=IncidentPriority(record.priority),
            summary=record.summary,
            affected_components=record.affected_components,
            missing_information=record.missing_information,
            justification=record.justification,
            confidence=AnalysisConfidence(record.confidence),
            created_at=record.created_at,
        )
