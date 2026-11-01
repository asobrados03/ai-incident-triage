from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Protocol
import unicodedata

import httpx

from backend.infrastructure.config import get_settings
from backend.domain.models import AnalysisConfidence
from backend.schemas import IncidentCreate, TriageResult


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


def _normalize(text: str) -> str:
    """Lowercase text and remove accents so rules are language-stable."""
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_accents.lower().split())


def _matches(text: str, pattern: str) -> bool:
    return re.search(pattern, text) is not None


@dataclass(frozen=True)
class _Signal:
    name: str
    pattern: str
    weight: int = 1


_CATEGORY_SIGNALS: dict[str, tuple[_Signal, ...]] = {
    "performance": (
        _Signal("latencia", r"\blatenc", 2),
        _Signal("lentitud", r"\blent(?:itud|amente|o|a|os|as)\b", 2),
        _Signal("tardanza", r"\btard(?:a|an|anza|o|aron|aba|aban)\b", 2),
        _Signal("rendimiento", r"\brendimiento", 2),
        _Signal("performance", r"\bperformance\b|\bslow\b", 2),
        _Signal("lentitud comparativa", r"\bdespacio\b|\bmas lento\b|\bva lento\b", 2),
        _Signal("timeout", r"\btimeout\b|\btiempo de espera", 2),
        _Signal(
            "duración",
            r"\b\d+(?:[.,]\d+)?\s*(?:ms|milisegundos|s|segundos|minutos)\b",
            1,
        ),
        _Signal("consumo", r"\bmemoria|\bcpu\b", 1),
    ),
    "configuration": (
        _Signal("configuración", r"\bconfig", 2),
        _Signal(
            "configuración incorrecta",
            r"\bconfig\w*\s+(?:incorrect|invalid|errone)\w*",
            2,
        ),
        _Signal("variables de entorno", r"\bvariable|\bentorno\b|\b\.env\b", 2),
        _Signal("database_url", r"database_url", 3),
        _Signal("conexión", r"\bconexion|\bconect", 2),
        _Signal("postgres", r"\bpostgres", 2),
        _Signal("despliegue", r"\bdespliegue|\bdeploy", 1),
        _Signal("credenciales", r"\bcredencial|\bcontrasen", 2),
    ),
    "documentation": (
        _Signal("documentación", r"\bdocument(?:acion|al)\b", 2),
        _Signal("readme", r"\breadme\b", 2),
        _Signal("docs", r"\bdocs?\b", 2),
        _Signal("guía", r"\bguia|\bmanual\b|\btutorial\b", 3),
        _Signal("instrucciones", r"\binstruccion", 2),
    ),
    "feature": (
        _Signal("solicitud", r"\bsolicit", 3),
        _Signal("exportación", r"\bexport", 2),
        _Signal("añadir", r"\banad|\bagreg|\bincluir\b", 2),
        _Signal("permitir", r"\bpermit", 2),
        _Signal("mejora", r"\bmejora|\bfuncionalidad\b|\bfeature\b", 2),
        _Signal("sería útil", r"\bseria util|\bpodria", 2),
    ),
    "bug": (
        _Signal("error", r"\berror", 2),
        _Signal("fallo", r"\bfall", 2),
        _Signal(
            "no funciona",
            r"\bno funciona|\bno carga\b|\bno responde|\bno se puede",
            2,
        ),
        _Signal("no recibe", r"\bno recib", 2),
        _Signal("no conecta", r"\bno conect", 2),
        _Signal(
            "elemento ausente",
            r"\bno aparece|\bno se muestra|\bno visible|\bdesaparec",
            3,
        ),
        _Signal("no se guarda", r"\bno se guard", 2),
        _Signal(
            "exposición de datos",
            r"\b(?:datos|facturas|pedidos|informacion|documentos|archivos) de otr[ao]"
            r"|\bcuenta ajena|\bacceso indebido|\bfuga de datos",
            2,
        ),
        _Signal("excepción", r"\bexcepcion|\bexception\b", 2),
        _Signal("cierre", r"\bcrash\b|\bcierr", 3),
        _Signal(
            "http 5xx",
            r"\berror(?:es)?(?:\s+http)?\s+5\d{2}\b|\bhttp\s+5\d{2}\b"
            r"|\bcodigo\s+5\d{2}\b",
            1,
        ),
        _Signal("incorrecto", r"\bincorrect|\broto\b|\bdefecto", 1),
        _Signal("corrupto", r"\bcorrupt", 2),
    ),
}

# Deterministic tie-break: bug reports win ties, feature requests lose them.
_CATEGORY_TIE_BREAK = ("bug", "configuration", "performance", "documentation", "feature")

_CRITICAL_IMPACT = (
    r"\bperdida de datos|\bdatos perdidos|\bcorrupcion|\bseguridad\b"
    r"|\bvulnerabilidad|\bcaida\b|\bno disponible|\bse cierra"
    r"|\bcierre de la aplicacion|\bcrash\b|\bcritico\b"
    r"|\b(?:datos|facturas|pedidos|informacion|documentos|archivos) de otr[ao]"
    r"|\bcuenta ajena|\bacceso indebido|\bfuga de datos"
)
_HIGH_IMPACT = (
    r"\btodos los usuarios|\btodo el mundo|\btoda la organizacion"
    r"|\berror(?:es)?(?:\s+http)?\s+5\d{2}\b|\bhttp\s+5\d{2}\b"
    r"|\bbloquea|\bno recib|\btardan|\btarda\b|\bdemora"
    r"|\binterrupcion|\bafecta a todos|\bmuy lento|\bgravemente"
    r"|\bpierden\b|\bse pierde|\bno se guard|\bcambios sin guardar"
)
_MEDIUM_IMPACT = (
    r"\berror|\bincorrect|\bfall|\bno conect|\bproblema|\bdegradad"
    r"|\blent(?:o|a|os|as|itud)\b|\bparcial|\bno funciona|\bno se puede"
    r"|\bdespacio\b|\bmas lento\b|\bno aparece|\bno se muestra"
    r"|\bno visible|\bdesaparec"
)
_URGENT_IMPACT = (
    r"\btodos los usuarios|\btodo el mundo|\btoda la organizacion"
    r"|\bcaida\b|\bno disponible|\bperdida de datos|\bdatos perdidos"
    r"|\bseguridad\b|\bvulnerabilidad|\burgente|\bcuanto antes"
    r"|\bbloqueante"
    r"|\b(?:datos|facturas|pedidos|informacion|documentos|archivos) de otr[ao]"
    r"|\bcuenta ajena|\bacceso indebido|\bfuga de datos"
)
_CONNECTIVITY_IMPACT = (
    r"\bconect|\bconexion|\bdatabase_url|\bdespliegue|\bcredencial"
)

_UNCERTAINTY = (
    r"\ba veces|\bocasional|\bintermitente|\besporadic"
    r"|\bno hay metricas|\bno hay trazas|\bsin metricas|\bsin trazas"
    r"|\bno se sabe|\bno esta claro|\bno tenemos logs"
)

_MISSING_LABELS = {
    "latency": "latencia observada",
    "percentage": "porcentaje de peticiones afectadas",
    "timing": "momento en que ocurre",
    "correlation": "identificador de correlación",
    "observability": "logs o métricas disponibles",
}

_STEPS_PLACEHOLDERS = {"n/a", "na", "none", "ninguno", "no aplica", "no procede"}


class FakeAnalyzer:
    """Deterministic, explainable baseline based on normalized signal matching."""

    def analyze(self, incident: IncidentCreate) -> TriageResult:
        text = _normalize(
            " ".join(
                (
                    incident.title,
                    incident.description,
                    incident.actual_behavior or "",
                ),
            ),
        )

        category, category_signals, category_scores = self._classify_category(text)
        severity, impact_signals = self._classify_severity(text, category)
        priority = self._classify_priority(
            text,
            category,
            severity,
        )
        missing_information = self._missing_information(incident, text, category)
        confidence = self._confidence(
            missing_information,
            category_scores,
            severity,
        )

        return TriageResult(
            category=category,
            severity=severity,
            priority=priority,
            summary=f"Análisis determinista de: {incident.title}",
            affected_components=incident.components or [],
            missing_information=missing_information,
            justification=self._justification(
                category,
                category_signals,
                severity,
                impact_signals,
                priority,
                missing_information,
            ),
            confidence=confidence,
        )

    @staticmethod
    def _classify_category(
        text: str,
    ) -> tuple[str, list[str], dict[str, int]]:
        scores: dict[str, int] = {}
        matched: dict[str, list[str]] = {}
        for category, signals in _CATEGORY_SIGNALS.items():
            hits = [signal for signal in signals if _matches(text, signal.pattern)]
            scores[category] = sum(signal.weight for signal in hits)
            matched[category] = [signal.name for signal in hits]

        best_score = max(scores.values(), default=0)
        if best_score == 0:
            return "bug", [], scores

        candidates = [name for name, score in scores.items() if score == best_score]
        category = min(
            candidates,
            key=lambda name: _CATEGORY_TIE_BREAK.index(name),
        )
        return category, matched[category], scores

    @staticmethod
    def _classify_severity(text: str, category: str) -> tuple[str, list[str]]:
        if _matches(text, _CRITICAL_IMPACT):
            return "critical", ["impacto crítico"]
        if _matches(text, _HIGH_IMPACT):
            return "high", ["impacto alto"]
        if category in {"feature", "documentation"}:
            return "low", ["sin señales de impacto alto"]
        if _matches(text, _MEDIUM_IMPACT):
            return "medium", ["impacto medio"]
        return "medium", ["sin señales de impacto"]

    @staticmethod
    def _classify_priority(
        text: str,
        category: str,
        severity: str,
    ) -> str:
        if _matches(text, _URGENT_IMPACT):
            return "urgent"
        if severity in {"critical", "high"}:
            return "high"
        if severity == "medium":
            if category == "configuration" and _matches(
                text,
                _CONNECTIVITY_IMPACT,
            ):
                return "high"
            return "medium"
        if category == "documentation":
            return "medium"
        return "low"

    @staticmethod
    def _missing_information(
        incident: IncidentCreate,
        text: str,
        category: str,
    ) -> list[str]:
        missing: list[str] = []

        steps = (incident.steps_to_reproduce or "").strip().lower()
        if category in {"bug", "performance", "configuration"} and (
            not steps or steps in _STEPS_PLACEHOLDERS
        ):
            missing.append("steps_to_reproduce")

        if not (incident.environment or "").strip():
            missing.append("environment")

        if not _matches(text, _UNCERTAINTY):
            return missing

        concepts = {
            "latency": r"\b\d+(?:[.,]\d+)?\s*(?:ms|milisegundos|s|segundos|minutos)\b",
            "percentage": r"\b\d+(?:[.,]\d+)?\s*%|\bporcentaje",
            "timing": (
                r"\ba las\b|\bdesde las\b|\bfecha\b|\bhora exacta"
                r"|\bventana temporal|\bfranja|\bpico de"
            ),
            "correlation": (
                r"\bcorrelacion|\btrace.?id|\brequest.?id"
                r"|\bid de peticion|\bidentificador de"
            ),
        }
        for name, pattern in concepts.items():
            if not _matches(text, pattern):
                missing.append(_MISSING_LABELS[name])

        explicitly_absent = r"\bno hay (?:logs|metricas|trazas)|\bsin (?:logs|metricas|trazas)"
        available = r"\blogs?\b|\bmetricas?\b|\btrazas?\b|\bmonitorizacion|\bobservabilidad"
        if _matches(text, explicitly_absent) or not _matches(text, available):
            missing.append(_MISSING_LABELS["observability"])

        return missing

    @staticmethod
    def _confidence(
        missing_information: list[str],
        category_scores: dict[str, int],
        severity: str,
    ) -> str:
        if missing_information:
            return "medium"
        ordered = sorted(category_scores.values(), reverse=True)
        top = ordered[0] if ordered else 0
        second = ordered[1] if len(ordered) > 1 else 0
        if top == 0:
            return "medium" if severity in {"high", "critical"} else "low"
        if top == second:
            return "medium"
        return "high"

    @staticmethod
    def _justification(
        category: str,
        category_signals: list[str],
        severity: str,
        impact_signals: list[str],
        priority: str,
        missing_information: list[str],
    ) -> str:
        category_reason = (
            f"señales de categoría: {', '.join(category_signals)}"
            if category_signals
            else "sin señales específicas, se aplica la categoría por defecto"
        )
        impact_reason = (
            f"impacto {', '.join(impact_signals)}"
            if impact_signals
            else "sin señales de impacto"
        )
        missing_reason = (
            f"faltan datos: {', '.join(missing_information)}"
            if missing_information
            else "no faltan datos obligatorios"
        )
        return (
            f"Categoría {category} ({category_reason}); "
            f"severidad {severity} ({impact_reason}); "
            f"prioridad {priority}; {missing_reason}."
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
