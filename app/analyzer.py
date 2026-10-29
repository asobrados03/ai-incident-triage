from typing import Protocol

from app.schemas import IncidentCreate, TriageResult


class IncidentAnalyzer(Protocol):
    def analyze(self, incident: IncidentCreate) -> TriageResult:
        """Return a deterministic domain result without handling persistence."""


class FakeAnalyzer:
    """Local analyzer used until a real provider adapter is introduced."""

    def analyze(self, incident: IncidentCreate) -> TriageResult:
        text = " ".join(
            (
                incident.title,
                incident.description,
                incident.actual_behavior or "",
            ),
        ).lower()

        if any(word in text for word in ("lento", "slow", "rendimiento", "performance")):
            category, severity, priority = "performance", "high", "high"
            justification = "Se detectaron indicios relacionados con rendimiento."
        elif any(word in text for word in ("configuración", "configuration", "config")):
            category, severity, priority = "configuration", "medium", "medium"
            justification = "Se detectaron indicios relacionados con configuración."
        elif any(word in text for word in ("documentación", "documentation", "docs")):
            category, severity, priority = "documentation", "low", "low"
            justification = "Se detectaron indicios relacionados con documentación."
        elif any(word in text for word in ("feature", "funcionalidad", "mejora", "solicitud")):
            category, severity, priority = "feature", "low", "medium"
            justification = "La incidencia parece solicitar una funcionalidad."
        else:
            category, severity, priority = "bug", "medium", "medium"
            justification = "Se clasifica como bug al no detectar otra señal."

        missing_information = []
        if not incident.steps_to_reproduce:
            missing_information.append("steps_to_reproduce")
        if not incident.environment:
            missing_information.append("environment")

        return TriageResult(
            category=category,
            severity=severity,
            priority=priority,
            summary=f"Análisis determinista de: {incident.title}",
            affected_components=incident.components or [],
            missing_information=missing_information,
            justification=justification,
            confidence="high" if not missing_information else "medium",
        )
