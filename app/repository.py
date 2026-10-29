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
from app.orm_models import IncidentORM, TriageResultORM, TriageReviewORM
from app.schemas import (
    IncidentResponse,
    TriageResult,
    TriageReviewRequest,
    TriageReviewResponse,
    TriageResultResponse,
)


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
        if record is None:
            return None
        return self._to_triage_response(record).model_copy(
            update={
                "review": (
                    self._to_review_response(review)
                    if (review := self._get_review_for_triage(record.id))
                    else None
                ),
            },
        )

    def get_review(self, incident_id: UUID) -> TriageReviewResponse | None:
        triage = self._session.scalar(
            select(TriageResultORM).where(
                TriageResultORM.incident_id == str(incident_id),
            ),
        )
        record = self._get_review_for_triage(triage.id) if triage else None
        return self._to_review_response(record) if record is not None else None

    def _get_review_for_triage(self, triage_id: str) -> TriageReviewORM | None:
        return self._session.scalar(
            select(TriageReviewORM).where(TriageReviewORM.triage_id == triage_id),
        )

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

    def create_review(
        self,
        incident_id: UUID,
        review: TriageReviewRequest,
    ) -> None:
        triage = self._session.scalar(
            select(TriageResultORM).where(
                TriageResultORM.incident_id == str(incident_id),
            ),
        )
        if triage is None:
            return

        values = {
            "category": triage.category,
            "severity": triage.severity,
            "priority": triage.priority,
            "summary": triage.summary,
            "affected_components": triage.affected_components,
            "missing_information": triage.missing_information,
            "justification": triage.justification,
            "confidence": triage.confidence,
        }
        values.update(
            {
                key: value.value if hasattr(value, "value") else value
                for key, value in review.model_dump(exclude_none=True).items()
                if key != "review_comment"
            },
        )
        record = TriageReviewORM(
            id=str(uuid4()),
            triage_id=triage.id,
            reviewed_at=datetime.now(timezone.utc),
            source="human",
            review_comment=review.review_comment,
            **values,
        )
        self._session.add(record)
        self._session.commit()

    @staticmethod
    def _to_review_response(record: TriageReviewORM) -> TriageReviewResponse:
        return TriageReviewResponse(
            reviewed=True,
            source=record.source,
            review_comment=record.review_comment,
            reviewed_at=record.reviewed_at,
            final=TriageResult(
                category=IncidentCategory(record.category),
                severity=IncidentSeverity(record.severity),
                priority=IncidentPriority(record.priority),
                summary=record.summary,
                affected_components=record.affected_components,
                missing_information=record.missing_information,
                justification=record.justification,
                confidence=AnalysisConfidence(record.confidence),
            ),
        )
