from enum import StrEnum


class IncidentStatus(StrEnum):
    CREATED = "created"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    ANALYSIS_FAILED = "analysis_failed"


class IncidentCategory(StrEnum):
    BUG = "bug"
    FEATURE = "feature"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    PERFORMANCE = "performance"


class IncidentSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class AnalysisConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
