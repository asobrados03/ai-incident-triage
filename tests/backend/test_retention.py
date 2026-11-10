from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.auth import Principal, Role
from backend.infrastructure.config import Settings, validate_runtime_settings
from backend.infrastructure.database import Base
from backend.infrastructure.orm_models import (
    AuditLogORM,
    IncidentORM,
    TriageResultORM,
    TriageReviewORM,
)
from backend.infrastructure.repositories import AuditRepository, RetentionRepository
from backend.services.retention import RetentionService


@pytest.fixture
def session(tmp_path):
    database_engine = create_engine(
        f"sqlite:///{tmp_path / 'retention.db'}",
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


def add_incident(
    session: Session,
    *,
    created_at: datetime,
    with_triage: bool = False,
    with_review: bool = False,
) -> tuple[str, str | None]:
    incident_id = str(uuid4())
    session.add(
        IncidentORM(
            id=incident_id,
            title="Título sensible",
            description="Descripción sensible",
            steps_to_reproduce=None,
            expected_behavior=None,
            actual_behavior=None,
            environment=None,
            components=None,
            status="reviewed" if with_review else "created",
            created_at=created_at,
        ),
    )
    triage_id = None
    if with_triage:
        triage_id = str(uuid4())
        session.add(
            TriageResultORM(
                id=triage_id,
                incident_id=incident_id,
                category="bug",
                severity="medium",
                priority="medium",
                summary="Resumen",
                affected_components=[],
                missing_information=[],
                justification="Justificación",
                confidence="high",
                created_at=created_at,
            ),
        )
        if with_review:
            session.add(
                TriageReviewORM(
                    id=str(uuid4()),
                    triage_id=triage_id,
                    category="bug",
                    severity="high",
                    priority="high",
                    summary="Resumen",
                    affected_components=[],
                    missing_information=[],
                    justification="Justificación",
                    confidence="high",
                    review_comment=None,
                    reviewed_at=created_at,
                    source="human",
                ),
            )
    session.commit()
    return incident_id, triage_id


def add_audit_log(
    session: Session,
    *,
    created_at: datetime,
    action: str,
) -> None:
    session.add(
        AuditLogORM(
            id=str(uuid4()),
            created_at=created_at,
            actor="old-user",
            role="writer",
            action=action,
            resource_type="incident",
            resource_id=None,
            details={},
        ),
    )
    session.commit()


def count_audit(session: Session, action: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(AuditLogORM)
        .where(AuditLogORM.action == action),
    ) or 0


def make_service(session: Session) -> RetentionService:
    return RetentionService(
        RetentionRepository(session),
        AuditRepository(session),
        incidents_days=90,
        audit_days=365,
    )


def seed(session: Session) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    old_incident, old_triage = add_incident(
        session,
        created_at=now - timedelta(days=100),
        with_triage=True,
        with_review=True,
    )
    recent_incident, recent_triage = add_incident(
        session,
        created_at=now - timedelta(days=10),
        with_triage=True,
        with_review=False,
    )
    add_audit_log(
        session,
        created_at=now - timedelta(days=400),
        action="old.event",
    )
    add_audit_log(
        session,
        created_at=now - timedelta(days=10),
        action="recent.event",
    )
    return {
        "old_incident": old_incident,
        "old_triage": old_triage,
        "recent_incident": recent_incident,
        "recent_triage": recent_triage,
    }


def test_retention_dry_run_reports_without_deleting(session: Session) -> None:
    ids = seed(session)

    result = make_service(session).run(
        actor=Principal(name="admin", role=Role.ADMIN),
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.incidents_matched == 1
    assert result.triage_results_matched == 1
    assert result.triage_reviews_matched == 1
    assert result.audit_logs_matched == 1

    session.expire_all()
    assert session.get(IncidentORM, ids["old_incident"]) is not None
    assert session.get(TriageResultORM, ids["old_triage"]) is not None
    assert session.get(IncidentORM, ids["recent_incident"]) is not None
    assert count_audit(session, "old.event") == 1
    assert count_audit(session, "recent.event") == 1
    assert count_audit(session, "retention.run") == 1


def test_retention_apply_deletes_only_expired_data_and_audits(session: Session) -> None:
    ids = seed(session)

    result = make_service(session).run(
        actor=Principal(name="admin", role=Role.ADMIN),
        dry_run=False,
    )

    assert result.dry_run is False
    assert result.incidents_matched == 1
    assert result.triage_results_matched == 1
    assert result.triage_reviews_matched == 1
    assert result.audit_logs_matched == 1

    session.expire_all()
    assert session.get(IncidentORM, ids["old_incident"]) is None
    assert session.get(TriageResultORM, ids["old_triage"]) is None
    assert session.get(IncidentORM, ids["recent_incident"]) is not None
    assert session.get(TriageResultORM, ids["recent_triage"]) is not None
    assert count_audit(session, "old.event") == 0
    assert count_audit(session, "recent.event") == 1

    retention_audit = session.scalar(
        select(AuditLogORM).where(AuditLogORM.action == "retention.run"),
    )
    assert retention_audit is not None
    assert retention_audit.actor == "admin"
    assert retention_audit.role == "admin"
    assert retention_audit.details["dry_run"] is False
    assert retention_audit.details["incidents_matched"] == 1
    assert retention_audit.details["audit_logs_matched"] == 1


def test_retention_respects_per_run_day_overrides(session: Session) -> None:
    seed(session)

    result = make_service(session).run(
        actor=Principal(name="admin", role=Role.ADMIN),
        dry_run=True,
        incidents_days=200,
        audit_days=500,
    )

    assert result.incidents_matched == 0
    assert result.audit_logs_matched == 0


def test_retention_rejects_non_positive_day_overrides(session: Session) -> None:
    with pytest.raises(ValueError):
        make_service(session).run(
            actor=Principal(name="admin", role=Role.ADMIN),
            dry_run=True,
            incidents_days=0,
        )


@pytest.mark.parametrize(
    "settings",
    [
        Settings(retention_days=0),
        Settings(audit_retention_days=0),
        Settings(auth_users="invalid-configuration"),
    ],
)
def test_invalid_security_settings_are_rejected(settings: Settings) -> None:
    with pytest.raises(ValueError):
        validate_runtime_settings(settings)
