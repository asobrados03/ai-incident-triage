from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IncidentORM(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(5000), nullable=False)
    steps_to_reproduce: Mapped[str | None] = mapped_column(String(5000))
    expected_behavior: Mapped[str | None] = mapped_column(String(2000))
    actual_behavior: Mapped[str | None] = mapped_column(String(2000))
    environment: Mapped[str | None] = mapped_column(String(1000))
    components: Mapped[list[str] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TriageResultORM(Base):
    __tablename__ = "triage_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id"),
        unique=True,
        nullable=False,
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(String(1000), nullable=False)
    affected_components: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    missing_information: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    justification: Mapped[str] = mapped_column(String(2000), nullable=False)
    confidence: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
