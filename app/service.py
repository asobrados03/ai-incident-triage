from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.analyzer import IncidentAnalyzer
from app.models import IncidentStatus
from app.repository import IncidentRepository
from app.schemas import IncidentCreate, IncidentResponse, TriageReviewRequest


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
    ) -> None:
        self._repository = repository
        self._analyzer = analyzer

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

    def analyze(self, incident_id: UUID) -> IncidentResponse:
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
        except Exception:
            self._repository.set_status(incident_id, IncidentStatus.ANALYSIS_FAILED)
            raise

        analyzed = self._repository.get(incident_id)
        if analyzed is None:
            raise IncidentNotFoundError
        return analyzed

    def review(
        self,
        incident_id: UUID,
        review: TriageReviewRequest,
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
        return reviewed
