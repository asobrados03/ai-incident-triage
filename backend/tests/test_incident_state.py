from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.api.schemas import IncidentResponse, TriageResult, TriageReviewRequest
from backend.domain.models import IncidentSeverity, IncidentStatus
from backend.infrastructure.database import Base
from backend.infrastructure.orm_models import IncidentORM, TriageResultORM, TriageReviewORM
from backend.infrastructure.repositories import IncidentRepository
from backend.services.incident import IncidentReviewConflictError, IncidentService


@pytest.fixture
def session(tmp_path):
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'state.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(database_engine)
    factory = sessionmaker(
        bind=database_engine,
        autocommit=False,
        autoflush=False,
    )
    with factory() as db_session:
        yield db_session
    database_engine.dispose()


def make_triage(*, severity: IncidentSeverity = IncidentSeverity.MEDIUM) -> TriageResult:
    return TriageResult(
        category="bug",
        severity=severity,
        priority="medium",
        summary="Resumen",
        affected_components={"frontend"},
        missing_information={"logs"},
        justification="Justificación",
        confidence="high",
    )


def create_incident(repository: IncidentRepository) -> IncidentResponse:
    return repository.create(
        IncidentResponse(
            id=uuid4(),
            status=IncidentStatus.CREATED,
            created_at=datetime.now(UTC),
            title="Fallo",
            description="No funciona.",
        ),
    )


class FixedAnalyzer:
    def __init__(self, result: TriageResult) -> None:
        self._result = result

    def analyze(self, incident) -> TriageResult:
        return self._result


def set_status(session: Session, incident_id: UUID, status: str) -> None:
    record = session.get(IncidentORM, str(incident_id))
    assert record is not None
    record.status = status
    session.commit()


def test_claim_for_analysis_is_exclusive(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)

    assert repository.claim_for_analysis(incident.id) is True
    assert repository.get(incident.id).status is IncidentStatus.ANALYZING
    assert repository.claim_for_analysis(incident.id) is False
    assert repository.claim_for_analysis(uuid4()) is False


def test_claim_for_analysis_allows_retry_after_failure(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)

    assert repository.claim_for_analysis(incident.id) is True
    repository.mark_analysis_failed(incident.id)
    assert repository.get(incident.id).status is IncidentStatus.ANALYSIS_FAILED
    assert repository.claim_for_analysis(incident.id) is True


def test_complete_analysis_requires_an_active_claim(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)

    assert repository.complete_analysis(incident.id, make_triage()) is False
    assert repository.get(incident.id).status is IncidentStatus.CREATED
    assert session.scalar(select(func.count()).select_from(TriageResultORM)) == 0


def test_retry_with_existing_triage_heals_the_incident(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)
    assert repository.claim_for_analysis(incident.id) is True
    assert repository.complete_analysis(incident.id, make_triage()) is True

    # Estado inconsistente que provocaba el fallo anterior: triaje persistido
    # pero incidencia marcada como fallida.
    set_status(session, incident.id, "analysis_failed")

    service = IncidentService(
        repository, FixedAnalyzer(make_triage(severity=IncidentSeverity.HIGH))
    )
    analyzed = service.analyze(incident.id)

    assert analyzed.status is IncidentStatus.ANALYZED
    assert analyzed.triage is not None
    assert analyzed.triage.severity is IncidentSeverity.HIGH
    assert session.scalar(select(func.count()).select_from(TriageResultORM)) == 1


def test_mark_analysis_failed_does_not_override_analyzed(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)
    assert repository.claim_for_analysis(incident.id) is True
    assert repository.complete_analysis(incident.id, make_triage()) is True

    repository.mark_analysis_failed(incident.id)

    assert repository.get(incident.id).status is IncidentStatus.ANALYZED


def test_save_review_requires_analyzed_and_is_atomic(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)

    assert (
        repository.save_review(incident.id, TriageReviewRequest(review_comment="Sin triaje"))
        is False
    )

    assert repository.claim_for_analysis(incident.id) is True
    assert repository.complete_analysis(incident.id, make_triage()) is True
    assert (
        repository.save_review(incident.id, TriageReviewRequest(review_comment="Aceptado")) is True
    )
    assert repository.get(incident.id).status is IncidentStatus.REVIEWED
    assert repository.save_review(incident.id, TriageReviewRequest(severity="critical")) is False
    assert session.scalar(select(func.count()).select_from(TriageReviewORM)) == 1


def test_save_review_rejects_incident_not_in_analyzed(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)
    assert repository.claim_for_analysis(incident.id) is True
    assert repository.complete_analysis(incident.id, make_triage()) is True
    set_status(session, incident.id, "analysis_failed")

    assert repository.save_review(incident.id, TriageReviewRequest(severity="critical")) is False
    assert session.scalar(select(func.count()).select_from(TriageReviewORM)) == 0


def test_review_from_failed_analysis_is_rejected(session: Session) -> None:
    repository = IncidentRepository(session)
    incident = create_incident(repository)
    assert repository.claim_for_analysis(incident.id) is True
    assert repository.complete_analysis(incident.id, make_triage()) is True
    set_status(session, incident.id, "analysis_failed")

    service = IncidentService(repository, FixedAnalyzer(make_triage()))

    with pytest.raises(IncidentReviewConflictError):
        service.review(incident.id, TriageReviewRequest(severity="critical"))
