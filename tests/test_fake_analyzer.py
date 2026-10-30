from app.analyzer import FakeAnalyzer
from app.schemas import IncidentCreate, TriageResult


def analyze(**overrides) -> TriageResult:
    payload = {
        "title": "Fallo",
        "description": "Se produce un fallo.",
        "steps_to_reproduce": "Reproducir el fallo.",
        "environment": "Producción",
    }
    payload.update(overrides)
    return FakeAnalyzer().analyze(IncidentCreate(**payload))


def test_normalizes_accents_case_and_plural_forms() -> None:
    result = analyze(
        title="Búsquedas LENTAS en el panel",
        description="Las búsquedas tardan demasiado.",
    )

    assert result.category == "performance"
    assert result.severity == "high"
    assert result.priority == "high"


def test_classifies_configuration_and_raises_connectivity_priority() -> None:
    result = analyze(
        title="Error de conexión a PostgreSQL",
        description="La aplicación no conecta tras modificar DATABASE_URL.",
        environment="Staging",
    )

    assert result.category == "configuration"
    assert result.severity == "medium"
    assert result.priority == "high"


def test_crash_is_critical_but_not_automatically_urgent() -> None:
    result = analyze(
        title="La aplicación se cierra al arrancar",
        description="Se cierra al arrancar en producción.",
    )

    assert result.category == "bug"
    assert result.severity == "critical"
    assert result.priority == "high"


def test_http_500_for_all_users_is_urgent() -> None:
    result = analyze(
        title="Error 500 al iniciar sesión",
        description="El inicio de sesión devuelve un error 500 para todos los usuarios.",
    )

    assert result.category == "bug"
    assert result.severity == "high"
    assert result.priority == "urgent"


def test_feature_request_is_low_severity_and_low_priority() -> None:
    result = analyze(
        title="Solicitud de exportación CSV",
        description="Se solicita poder exportar los resultados en formato CSV.",
        steps_to_reproduce="N/A",
    )

    assert result.category == "feature"
    assert result.severity == "low"
    assert result.priority == "low"
    assert result.missing_information == []


def test_documentation_issue_is_low_severity_but_medium_priority() -> None:
    result = analyze(
        title="README desactualizado",
        description="El README describe una versión anterior del proyecto.",
        environment="Desarrollo",
    )

    assert result.category == "documentation"
    assert result.severity == "low"
    assert result.priority == "medium"


def test_uncertain_performance_issue_requests_observability_data() -> None:
    result = analyze(
        title="Lentitud ocasional al crear una incidencia",
        description=(
            "Crear una incidencia a veces es lento, pero no hay métricas ni "
            "trazas para distinguir si el problema está en la API o en la base "
            "de datos."
        ),
    )

    assert result.category == "performance"
    assert result.severity == "medium"
    assert result.priority == "medium"
    assert result.missing_information == [
        "latencia observada",
        "porcentaje de peticiones afectadas",
        "momento en que ocurre",
        "identificador de correlación",
        "logs o métricas disponibles",
    ]
    assert result.confidence == "medium"


def test_missing_steps_and_environment_are_reported_for_bugs() -> None:
    result = analyze(
        title="Error al guardar",
        description="La pantalla falla.",
        steps_to_reproduce=None,
        environment=None,
    )

    assert "steps_to_reproduce" in result.missing_information
    assert "environment" in result.missing_information
    assert result.confidence == "medium"


def test_ambiguous_signals_reduce_confidence() -> None:
    result = analyze(
        title="Archivos corruptos al exportar",
        description="La exportación genera archivos corruptos con datos incompletos.",
    )

    assert result.category == "bug"
    assert result.confidence == "medium"
    assert "corrupto" in result.justification


def test_justification_explains_the_detected_signals() -> None:
    result = analyze(
        title="Solicitud de paginación",
        description="Se solicita añadir paginación a los listados.",
        steps_to_reproduce="N/A",
    )

    assert "señales de categoría" in result.justification
    assert "prioridad low" in result.justification
