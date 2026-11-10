import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.analyzers.core import AnalyzerProviderUnavailableError, FakeAnalyzer
from backend.auth import Principal, Role
from backend.infrastructure.database import Base
from backend.domain.models import IncidentSeverity
from backend.infrastructure.repositories import AuditRepository, IncidentRepository
from backend.schemas import IncidentCreate, TriageReviewRequest
from backend.services.incident import IncidentService


@pytest.fixture
def session(tmp_path):
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'audit.db'}",
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


def writer() -> Principal:
    return Principal(name="soporte", role=Role.WRITER)


def incident() -> IncidentCreate:
    return IncidentCreate(
        title="Título confidencial",
        description="Descripción con datos sensibles.",
        components=["frontend"],
    )


def test_failed_analysis_is_audited_without_provider_details(session: Session) -> None:
    class UnavailableAnalyzer:
        def analyze(self, incident):
            raise AnalyzerProviderUnavailableError(
                "detalle-secreto-del-proveedor",
            )

    audit_repository = AuditRepository(session)
    service = IncidentService(
        IncidentRepository(session),
        UnavailableAnalyzer(),
        audit_repository,
    )
    created = service.create(incident(), actor=writer())

    with pytest.raises(AnalyzerProviderUnavailableError):
        service.analyze(created.id, actor=writer())

    logs, total = audit_repository.list(limit=10, offset=0)
    assert total == 2
    assert [log.action for log in logs] == [
        "incident.analysis_failed",
        "incident.create",
    ]
    failed = logs[0]
    assert failed.actor == "soporte"
    assert failed.role == Role.WRITER
    assert failed.resource_type == "incident"
    assert failed.resource_id == str(created.id)
    assert failed.details["error_type"] == "AnalyzerProviderUnavailableError"
    assert "detalle-secreto-del-proveedor" not in json.dumps(failed.details)


def test_review_audit_records_fields_but_not_comment_content(
    session: Session,
) -> None:
    audit_repository = AuditRepository(session)
    service = IncidentService(
        IncidentRepository(session),
        FakeAnalyzer(),
        audit_repository,
    )
    created = service.create(incident(), actor=writer())
    service.analyze(created.id, actor=writer())

    service.review(
        created.id,
        TriageReviewRequest(
            severity=IncidentSeverity.HIGH,
            review_comment="comentario sensible que no debe auditarse",
        ),
        actor=writer(),
    )

    logs, _ = audit_repository.list(
        limit=10,
        offset=0,
        action="incident.review",
    )
    assert len(logs) == 1
    review_log = logs[0]
    assert review_log.details["changed_fields"] == ["severity"]
    assert review_log.details["has_comment"] is True
    assert "comentario sensible" not in json.dumps(review_log.details)
