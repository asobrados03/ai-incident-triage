from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.infrastructure.database import Base


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

    triage: Mapped["TriageResultORM | None"] = relationship(
        back_populates="incident",
        uselist=False,
    )


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

    incident: Mapped[IncidentORM] = relationship(back_populates="triage")
    review: Mapped["TriageReviewORM | None"] = relationship(
        back_populates="triage",
        uselist=False,
    )


class TriageReviewORM(Base):
    __tablename__ = "triage_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    triage_id: Mapped[str] = mapped_column(
        ForeignKey("triage_results.id"),
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
    review_comment: Mapped[str | None] = mapped_column(String(2000))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="human")

    triage: Mapped[TriageResultORM] = relationship(back_populates="review")


class AuditLogORM(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
