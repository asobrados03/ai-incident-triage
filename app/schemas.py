from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
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


class TriageResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: IncidentCategory
    severity: IncidentSeverity
    priority: IncidentPriority
    summary: str = Field(min_length=1, max_length=1000)
    affected_components: list[str]
    missing_information: list[str]
    justification: str = Field(min_length=1, max_length=2000)
    confidence: AnalysisConfidence


class TriageResultResponse(TriageResult):
    id: UUID
    created_at: datetime


class IncidentResponse(IncidentCreate):
    id: UUID
    status: IncidentStatus
    created_at: datetime
    triage: TriageResultResponse | None = None
