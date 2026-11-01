from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.auth import Role
from backend.domain.models import (
    AnalysisConfidence,
    IncidentCategory,
    IncidentPriority,
    IncidentSeverity,
    IncidentStatus,
)


class IncidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=5000)
    steps_to_reproduce: str | None = Field(default=None, max_length=5000)
    expected_behavior: str | None = Field(default=None, max_length=2000)
    actual_behavior: str | None = Field(default=None, max_length=2000)
    environment: str | None = Field(default=None, max_length=1000)
    components: list[str] | None = Field(default=None, max_length=20)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: IncidentCategory
    severity: IncidentSeverity
    priority: IncidentPriority
    summary: str = Field(min_length=1, max_length=1000)
    affected_components: set[str] = Field(default_factory=set, max_length=20)
    missing_information: set[str] = Field(default_factory=set, max_length=20)
    justification: str = Field(min_length=1, max_length=2000)
    confidence: AnalysisConfidence


class TriageReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: IncidentCategory | None = None
    severity: IncidentSeverity | None = None
    priority: IncidentPriority | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=1000)
    affected_components: set[str] | None = None
    missing_information: set[str] | None = None
    justification: str | None = Field(default=None, min_length=1, max_length=2000)
    confidence: AnalysisConfidence | None = None
    review_comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_review_content(self) -> "TriageReviewRequest":
        if not any(value is not None for value in self.model_dump().values()):
            raise ValueError("Review must change at least one field or add a comment")
        return self


class TriageReviewResponse(BaseModel):
    reviewed: bool
    source: str
    review_comment: str | None
    reviewed_at: datetime
    final: TriageResult


class TriageResultResponse(TriageResult):
    id: UUID
    created_at: datetime
    review: TriageReviewResponse | None = None


class IncidentResponse(IncidentCreate):
    id: UUID
    status: IncidentStatus
    created_at: datetime
    triage: TriageResultResponse | None = None


class TriageSummary(BaseModel):
    category: IncidentCategory
    severity: IncidentSeverity
    priority: IncidentPriority
    summary: str


class IncidentListItem(BaseModel):
    id: UUID
    title: str
    status: IncidentStatus
    created_at: datetime
    confidence: AnalysisConfidence | None = None
    proposal: TriageSummary | None = None
    final: TriageSummary | None = None


class IncidentListPage(BaseModel):
    items: list[IncidentListItem]
    total: int
    limit: int
    offset: int


class FieldAccuracy(BaseModel):
    total: int
    correct: int
    accuracy: float


class CorrectionByConfidence(BaseModel):
    total_reviews: int
    corrected_reviews: int
    accepted_without_changes: int
    correction_rate: float


class ReviewMetricsResponse(BaseModel):
    total_reviewed: int
    accepted_without_changes: int
    acceptance_rate: float
    field_accuracy: dict[str, FieldAccuracy]
    confusion_matrices: dict[str, dict[str, dict[str, int]]]
    corrections_by_confidence: dict[str, CorrectionByConfidence]


class AuditLogResponse(BaseModel):
    id: UUID
    created_at: datetime
    actor: str
    role: Role
    action: str
    resource_type: str
    resource_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class RetentionRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    incidents_days: int | None = Field(default=None, ge=1, le=36500)
    audit_days: int | None = Field(default=None, ge=1, le=36500)


class RetentionRunResponse(BaseModel):
    dry_run: bool
    incident_cutoff: datetime
    audit_cutoff: datetime
    incidents_matched: int
    triage_results_matched: int
    triage_reviews_matched: int
    audit_logs_matched: int
