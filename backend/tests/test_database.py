from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.infrastructure.database import Base, create_database_engine
from backend.infrastructure.orm_models import TriageResultORM


def test_sqlite_engine_enables_foreign_keys(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'foreign-keys.db'}")
    Base.metadata.create_all(engine)

    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1

    engine.dispose()


def test_sqlite_rejects_orphan_triage_result(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'orphan.db'}")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(
            TriageResultORM(
                id=str(uuid4()),
                incident_id=str(uuid4()),
                category="bug",
                severity="medium",
                priority="medium",
                summary="Resumen",
                affected_components=[],
                missing_information=[],
                justification="Justificación",
                confidence="high",
                created_at=datetime.now(UTC),
            ),
        )
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()
