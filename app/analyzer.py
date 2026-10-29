from typing import Protocol

import httpx

from app.config import get_settings
from app.models import AnalysisConfidence
from app.schemas import IncidentCreate, TriageResult


class IncidentAnalyzer(Protocol):
    def analyze(self, incident: IncidentCreate) -> TriageResult:
        """Return a deterministic domain result without handling persistence."""


class AnalyzerProviderUnavailableError(Exception):
    """The configured analyzer provider cannot be reached."""


class AnalyzerTimeoutError(Exception):
    """The configured analyzer provider exceeded its timeout."""


class AnalyzerResponseError(Exception):
    """The analyzer provider returned an unusable result."""


class AnalyzerConfigurationError(Exception):
    """The configured analyzer backend is not supported."""


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


class OllamaAnalyzer:
    """Analyzer adapter for a local Ollama server."""

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._model = model or settings.ollama_model
        self._timeout = timeout_seconds or settings.ollama_timeout_seconds
        self._client = client

    def analyze(self, incident: IncidentCreate) -> TriageResult:
        payload = {
            "model": self._model,
            "stream": False,
            "think": False,
            "format": TriageResult.model_json_schema(),
            "options": {"temperature": 0, "num_predict": 512},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Clasifica incidencias. Responde únicamente con un objeto JSON "
                        "válido que cumpla exactamente el esquema solicitado."
                    ),
                },
                {
                    "role": "user",
                    "content": self._incident_prompt(incident),
                },
            ],
        }

        try:
            response = self._post(payload)
        except httpx.TimeoutException as error:
            raise AnalyzerTimeoutError(
                f"Ollama timed out after {self._timeout} seconds",
            ) from error
        except (httpx.ConnectError, httpx.NetworkError) as error:
            raise AnalyzerProviderUnavailableError(
                f"Ollama is unavailable at {self._base_url}",
            ) from error
        except httpx.HTTPStatusError as error:
            raise AnalyzerProviderUnavailableError(
                f"Ollama returned HTTP {error.response.status_code}",
            ) from error

        try:
            content = response.json()["message"]["content"]
            result = TriageResult.model_validate_json(content)
            if (
                result.missing_information
                and result.confidence is AnalysisConfidence.HIGH
            ):
                result = result.model_copy(
                    update={"confidence": AnalysisConfidence.MEDIUM},
                )
            return result
        except (KeyError, TypeError, ValueError) as error:
            raise AnalyzerResponseError(
                "Ollama returned a response that does not match TriageResult",
            ) from error

    def _post(self, payload: dict) -> httpx.Response:
        if self._client is not None:
            response = self._client.post(
                f"{self._base_url}/api/chat",
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            return response

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                f"{self._base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response

    @staticmethod
    def _incident_prompt(incident: IncidentCreate) -> str:
        return (
            "Analiza esta incidencia y devuelve category, severity, priority, summary, "
            "affected_components, missing_information, justification y confidence.\n\n"
            f"{incident.model_dump_json()}"
        )
