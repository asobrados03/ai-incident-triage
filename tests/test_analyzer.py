import json

import httpx
import pytest

from app.analyzer import (
    AnalyzerProviderUnavailableError,
    AnalyzerResponseError,
    AnalyzerTimeoutError,
    OllamaAnalyzer,
)
from app.schemas import IncidentCreate


def incident() -> IncidentCreate:
    return IncidentCreate(
        title="No carga el panel",
        description="El panel devuelve un error.",
        components=["frontend"],
    )


def valid_ollama_response() -> dict:
    return {
        "message": {
            "content": (
                '{"category":"bug","severity":"medium","priority":"medium",'
                '"summary":"El panel falla","affected_components":["frontend"],'
                '"missing_information":[],"justification":"Es un defecto funcional",'
                '"confidence":"high"}'
            ),
        },
    }


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ollama_analyzer_parses_structured_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat"
        payload = json.loads(request.read())
        assert payload["model"] == "qwen3.5:4b"
        assert payload["think"] is False
        assert payload["options"]["temperature"] == 0
        assert payload["options"]["num_predict"] == 512
        return httpx.Response(200, json=valid_ollama_response())

    analyzer = OllamaAnalyzer(
        base_url="http://ollama.test",
        model="qwen3.5:4b",
        client=make_client(handler),
    )

    result = analyzer.analyze(incident())

    assert result.category == "bug"
    assert result.affected_components == ["frontend"]
    assert result.confidence == "high"


def ollama_response_with(confidence: str, missing_information: list[str]) -> dict:
    content = {
        "category": "bug",
        "severity": "medium",
        "priority": "medium",
        "summary": "El panel falla",
        "affected_components": ["frontend"],
        "missing_information": missing_information,
        "justification": "Es un defecto funcional",
        "confidence": confidence,
    }
    return {"message": {"content": json.dumps(content)}}


def analyze_response(confidence: str, missing_information: list[str]):
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ollama_response_with(confidence, missing_information),
        )

    analyzer = OllamaAnalyzer(
        base_url="http://ollama.test",
        client=make_client(handler),
    )
    return analyzer.analyze(incident())


def test_ollama_analyzer_downgrades_high_confidence_with_missing_information() -> None:
    result = analyze_response("high", ["environment"])

    assert result.confidence == "medium"


def test_ollama_analyzer_keeps_low_confidence_with_missing_information() -> None:
    result = analyze_response("low", ["environment"])

    assert result.confidence == "low"


def test_ollama_analyzer_rejects_invalid_structured_result() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": '{"category":"unknown"}'}},
        )

    analyzer = OllamaAnalyzer(
        base_url="http://ollama.test",
        client=make_client(handler),
    )

    with pytest.raises(AnalyzerResponseError):
        analyzer.analyze(incident())


def test_ollama_analyzer_maps_unavailable_provider() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    analyzer = OllamaAnalyzer(
        base_url="http://ollama.test",
        client=make_client(handler),
    )

    with pytest.raises(AnalyzerProviderUnavailableError):
        analyzer.analyze(incident())


def test_ollama_analyzer_maps_timeout() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    analyzer = OllamaAnalyzer(
        base_url="http://ollama.test",
        client=make_client(handler),
    )

    with pytest.raises(AnalyzerTimeoutError):
        analyzer.analyze(incident())
