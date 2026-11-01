from backend.main import app


def test_openapi_exposes_backend_frontend_contract() -> None:
    paths = app.openapi()["paths"]

    assert {
        "/auth/login",
        "/health",
        "/incidents",
        "/incidents/{incident_id}",
        "/incidents/{incident_id}/analysis",
        "/incidents/{incident_id}/triage",
        "/review-metrics",
    } <= set(paths)
    assert paths["/incidents"]["get"]["parameters"][0]["name"] == "limit"
    assert paths["/incidents"]["get"]["parameters"][2]["name"] == "status"
    assert paths["/auth/login"]["post"]["requestBody"]
    assert paths["/review-metrics"]["get"]["responses"]["200"]


def test_openapi_operations_have_validation_error_contracts() -> None:
    paths = app.openapi()["paths"]

    analysis_responses = paths["/incidents/{incident_id}/analysis"]["post"]["responses"]
    review_responses = paths["/incidents/{incident_id}/triage"]["patch"]["responses"]

    assert "200" in analysis_responses
    assert "422" in analysis_responses
    assert "200" in review_responses
    assert "422" in review_responses
