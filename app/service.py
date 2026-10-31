from datetime import datetime, timezone
import logging
from time import perf_counter
from uuid import UUID, uuid4

from app.analyzer import IncidentAnalyzer
from app.auth import Principal
from app.models import IncidentStatus
from app.repository import AuditRepository, IncidentRepository
from app.schemas import IncidentCreate, IncidentResponse, TriageReviewRequest

logger = logging.getLogger(__name__)


class IncidentNotFoundError(Exception):
    pass


class IncidentAnalysisConflictError(Exception):
    pass


class IncidentReviewConflictError(Exception):
    pass


class IncidentService:
    def __init__(
        self,
        repository: IncidentRepository,
        analyzer: IncidentAnalyzer,
        audit_repository: AuditRepository | None = None,
    ) -> None:
        self._repository = repository
        self._analyzer = analyzer
        self._audit_repository = audit_repository

    def create(
        self,
        data: IncidentCreate,
        actor: Principal | None = None,
    ) -> IncidentResponse:
        incident = IncidentResponse(
            id=uuid4(),
            status=IncidentStatus.CREATED,
            created_at=datetime.now(timezone.utc),
            **data.model_dump(),
        )
        created = self._repository.create(incident)
        self._record_audit(
            actor,
            "incident.create",
            created.id,
            {"status": created.status.value},
        )
        return created

    def get(self, incident_id: UUID) -> IncidentResponse | None:
        return self._repository.get(incident_id)

    def analyze(
        self,
        incident_id: UUID,
        actor: Principal | None = None,
    ) -> IncidentResponse:
        started = perf_counter()
        logger.info("incident_analysis_started", extra={"incident_id": str(incident_id)})
        incident = self._repository.get(incident_id)
        if incident is None:
            raise IncidentNotFoundError
        if incident.status is not IncidentStatus.CREATED:
            raise IncidentAnalysisConflictError(
                f"Incident cannot be analyzed from status {incident.status.value}",
            )

        self._repository.set_status(incident_id, IncidentStatus.ANALYZING)
        try:
            result = self._analyzer.analyze(incident)
            self._repository.create_triage(incident_id, result)
            self._repository.set_status(incident_id, IncidentStatus.ANALYZED)
        except Exception as error:
            self._repository.set_status(incident_id, IncidentStatus.ANALYSIS_FAILED)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            logger.error(
                "incident_analysis_failed",
                extra={
                    "incident_id": str(incident_id),
                    "status": IncidentStatus.ANALYSIS_FAILED.value,
                    "duration_ms": duration_ms,
                    "error_type": "analyzer_error",
                },
            )
            self._record_audit_safely(
                actor,
                "incident.analysis_failed",
                incident_id,
                {
                    "status": IncidentStatus.ANALYSIS_FAILED.value,
                    "duration_ms": duration_ms,
                    "error_type": type(error).__name__,
                },
            )
            raise

        analyzed = self._repository.get(incident_id)
        if analyzed is None:
            raise IncidentNotFoundError
        duration_ms = round((perf_counter() - started) * 1000, 2)
        logger.info(
            "incident_analysis_completed",
            extra={
                "incident_id": str(incident_id),
                "status": analyzed.status.value,
                "duration_ms": duration_ms,
            },
        )
        self._record_audit(
            actor,
            "incident.analyze",
            incident_id,
            {
                "status": analyzed.status.value,
                "duration_ms": duration_ms,
            },
        )
        return analyzed

    def review(
        self,
        incident_id: UUID,
        review: TriageReviewRequest,
        actor: Principal | None = None,
    ) -> IncidentResponse:
        incident = self._repository.get(incident_id)
        if incident is None:
            raise IncidentNotFoundError
        if incident.status is IncidentStatus.REVIEWED:
            raise IncidentReviewConflictError("Incident has already been reviewed")
        if incident.triage is None:
            raise IncidentReviewConflictError("Incident has no triage result")

        self._repository.create_review(incident_id, review)
        self._repository.set_status(incident_id, IncidentStatus.REVIEWED)
        reviewed = self._repository.get(incident_id)
        if reviewed is None:
            raise IncidentNotFoundError
        logger.info(
            "incident_review_completed",
            extra={
                "incident_id": str(incident_id),
                "status": reviewed.status.value,
            },
        )
        changed_fields = sorted(
            key
            for key, value in review.model_dump(exclude_none=True).items()
            if key != "review_comment" and value is not None
        )
        self._record_audit(
            actor,
            "incident.review",
            incident_id,
            {
                "status": reviewed.status.value,
                "changed_fields": changed_fields,
                "has_comment": review.review_comment is not None,
            },
        )
        return reviewed

    def _record_audit(
        self,
        actor: Principal | None,
        action: str,
        incident_id: UUID,
        details: dict,
    ) -> None:
        if self._audit_repository is None:
            return
        self._audit_repository.record(
            actor=actor or Principal.system(),
            action=action,
            resource_type="incident",
            resource_id=str(incident_id),
            details=details,
        )

    def _record_audit_safely(
        self,
        actor: Principal | None,
        action: str,
        incident_id: UUID,
        details: dict,
    ) -> None:
        try:
            self._record_audit(actor, action, incident_id, details)
        except Exception:
            logger.exception(
                "audit_write_failed",
                extra={"incident_id": str(incident_id)},
            )
