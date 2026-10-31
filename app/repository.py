from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import Principal
from app.models import (
    AnalysisConfidence,
    IncidentCategory,
    IncidentPriority,
    IncidentSeverity,
    IncidentStatus,
)
from app.orm_models import (
    AuditLogORM,
    IncidentORM,
    TriageResultORM,
    TriageReviewORM,
)
from app.schemas import (
    AuditLogResponse,
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


class AuditRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        actor: Principal,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        self._session.add(
            AuditLogORM(
                id=str(uuid4()),
                created_at=datetime.now(timezone.utc),
                actor=actor.name,
                role=actor.role.value,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
            ),
        )
        self._session.commit()

    def list(
        self,
        *,
        limit: int,
        offset: int,
        action: str | None = None,
        actor: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> tuple[list[AuditLogResponse], int]:
        filters = []
        if action is not None:
            filters.append(AuditLogORM.action == action)
        if actor is not None:
            filters.append(AuditLogORM.actor == actor)
        if resource_type is not None:
            filters.append(AuditLogORM.resource_type == resource_type)
        if resource_id is not None:
            filters.append(AuditLogORM.resource_id == resource_id)

        query = select(AuditLogORM)
        count_query = select(func.count()).select_from(AuditLogORM)
        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

        total = self._session.scalar(count_query) or 0
        records = self._session.scalars(
            query.order_by(
                AuditLogORM.created_at.desc(),
                AuditLogORM.id.desc(),
            )
            .limit(limit)
            .offset(offset),
        ).all()
        return [self._to_response(record) for record in records], total

    @staticmethod
    def _to_response(record: AuditLogORM) -> AuditLogResponse:
        return AuditLogResponse(
            id=UUID(record.id),
            created_at=record.created_at,
            actor=record.actor,
            role=record.role,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            details=record.details or {},
        )


@dataclass(frozen=True)
class RetentionCounts:
    incidents: int
    triage_results: int
    triage_reviews: int


class RetentionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def preview_incidents(self, cutoff: datetime) -> RetentionCounts:
        incident_ids = select(IncidentORM.id).where(IncidentORM.created_at < cutoff)
        triage_ids = select(TriageResultORM.id).where(
            TriageResultORM.incident_id.in_(incident_ids),
        )
        return RetentionCounts(
            incidents=self._count(IncidentORM, IncidentORM.created_at < cutoff),
            triage_results=self._count(
                TriageResultORM,
                TriageResultORM.incident_id.in_(incident_ids),
            ),
            triage_reviews=self._count(
                TriageReviewORM,
                TriageReviewORM.triage_id.in_(triage_ids),
            ),
        )

    def delete_incidents(self, cutoff: datetime) -> RetentionCounts:
        incident_ids = select(IncidentORM.id).where(IncidentORM.created_at < cutoff)
        triage_ids = select(TriageResultORM.id).where(
            TriageResultORM.incident_id.in_(incident_ids),
        )
        triage_reviews = self._delete(
            delete(TriageReviewORM).where(
                TriageReviewORM.triage_id.in_(triage_ids),
            ),
        )
        triage_results = self._delete(
            delete(TriageResultORM).where(
                TriageResultORM.incident_id.in_(incident_ids),
            ),
        )
        incidents = self._delete(
            delete(IncidentORM).where(IncidentORM.created_at < cutoff),
        )
        self._session.commit()
        return RetentionCounts(
            incidents=incidents,
            triage_results=triage_results,
            triage_reviews=triage_reviews,
        )

    def preview_audit_logs(self, cutoff: datetime) -> int:
        return self._count(AuditLogORM, AuditLogORM.created_at < cutoff)

    def delete_audit_logs(self, cutoff: datetime) -> int:
        deleted = self._delete(
            delete(AuditLogORM).where(AuditLogORM.created_at < cutoff),
        )
        self._session.commit()
        return deleted

    def _count(self, model, *conditions) -> int:
        query = select(func.count()).select_from(model)
        if conditions:
            query = query.where(*conditions)
        return self._session.scalar(query) or 0

    def _delete(self, statement) -> int:
        result = self._session.execute(
            statement.execution_options(synchronize_session=False),
        )
        return result.rowcount or 0
