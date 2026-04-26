from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator, Mapping
from uuid import uuid4

from fastapi import FastAPI, Request

REQUEST_ID_HEADER = "X-Request-ID"
CONTEXT_FIELDS = ("request_id", "contract_id", "document_upload_id", "processing_run_id")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_contract_id: ContextVar[str | None] = ContextVar("contract_id", default=None)
_document_upload_id: ContextVar[str | None] = ContextVar("document_upload_id", default=None)
_processing_run_id: ContextVar[str | None] = ContextVar("processing_run_id", default=None)
_context_vars = {
    "request_id": _request_id,
    "contract_id": _contract_id,
    "document_upload_id": _document_upload_id,
    "processing_run_id": _processing_run_id,
}
_configured_services: set[str] = set()
_azure_monitor_configured = False


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        service_name = getattr(record, "service_name", None)
        if service_name:
            payload["service"] = service_name
        for key in CONTEXT_FIELDS:
            payload[key] = getattr(record, key, None) or _context_vars[key].get()
        for key, value in record.__dict__.items():
            if key in _standard_log_record_fields() or key in payload:
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"))


class ContextLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        extra = dict(self.extra)
        extra.update(kwargs.pop("extra", {}) or {})
        kwargs["extra"] = extra
        return msg, kwargs


def configure_observability(service_name: str) -> None:
    global _azure_monitor_configured

    if service_name not in _configured_services:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler.addFilter(_ServiceNameFilter(service_name))
        logging.basicConfig(level=level, handlers=[handler], force=True)
        _configured_services.add(service_name)

    connection_string = os.getenv("APPINSIGHTS_CONNECTION_STRING") or os.getenv(
        "APPLICATIONINSIGHTS_CONNECTION_STRING"
    )
    if connection_string and not _azure_monitor_configured:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=connection_string)
            _azure_monitor_configured = True
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to configure Azure Monitor exporter",
                extra={"service_name": service_name},
            )


def instrument_fastapi(app: FastAPI) -> None:
    if not (
        os.getenv("APPINSIGHTS_CONNECTION_STRING")
        or os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    ):
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        get_logger(__name__).warning("FastAPI-specific OpenTelemetry instrumentation is unavailable")


def add_request_context_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid4())
        with log_context(
            request_id=request_id,
            contract_id=request.headers.get("X-Contract-ID"),
            document_upload_id=request.headers.get("X-Document-Upload-ID"),
            processing_run_id=request.headers.get("X-Processing-Run-ID"),
        ):
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id
            return response


def get_logger(name: str, **fields: Any) -> ContextLoggerAdapter:
    return ContextLoggerAdapter(logging.getLogger(name), _clean_context(fields))


def outbound_request_headers(headers: Mapping[str, str] | None = None) -> dict[str, str]:
    outbound = dict(headers or {})
    request_id = _request_id.get()
    if request_id:
        outbound.setdefault(REQUEST_ID_HEADER, request_id)
    return outbound


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    tokens = []
    try:
        for key, value in _clean_context(fields).items():
            tokens.append((_context_vars[key], _context_vars[key].set(value)))
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def _clean_context(fields: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: str(value)
        for key, value in fields.items()
        if key in _context_vars and value is not None and str(value)
    }


class _ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "service_name"):
            record.service_name = self.service_name
        return True


def _standard_log_record_fields() -> set[str]:
    return {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "module",
        "msecs",
        "message",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
        "taskName",
    }
