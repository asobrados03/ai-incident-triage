import json
import logging

from app.logging_config import JsonFormatter


def test_json_formatter_emits_only_operational_fields() -> None:
    record = logging.LogRecord(
        name="app.services.incident",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="incident_analysis_completed",
        args=(),
        exc_info=None,
    )
    record.incident_id = "incident-id"
    record.status = "analyzed"
    record.duration_ms = 12.5

    payload = json.loads(JsonFormatter().format(record))

    assert payload["event"] == "incident_analysis_completed"
    assert payload["incident_id"] == "incident-id"
    assert payload["status"] == "analyzed"
    assert payload["duration_ms"] == 12.5
    assert "description" not in payload
    assert "prompt" not in payload
    assert "secret" not in payload
