import json
import logging

from fastapi.testclient import TestClient

from app.main import app
from app.observability import (
    JsonLogFormatter,
    log_context,
    outbound_request_headers,
)


def test_health_response_includes_request_id_header() -> None:
    client = TestClient(app)

    response = client.get("/api/health", headers={"X-Request-ID": "req-test-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test-123"


def test_json_log_formatter_includes_correlation_fields() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )

    with log_context(
        request_id="req-1",
        contract_id="contract-1",
        document_upload_id="upload-1",
        processing_run_id="run-1",
    ):
        payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-1"
    assert payload["contract_id"] == "contract-1"
    assert payload["document_upload_id"] == "upload-1"
    assert payload["processing_run_id"] == "run-1"


def test_outbound_headers_propagate_request_id() -> None:
    with log_context(request_id="req-forward"):
        headers = outbound_request_headers({"Accept": "application/json"})

    assert headers == {"Accept": "application/json", "X-Request-ID": "req-forward"}
