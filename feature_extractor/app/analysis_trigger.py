import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import get_backend_api_url, get_internal_service_token


def trigger_per_contract_analysis(
    doc_id: str,
    contract_id: str | None,
    extraction_run_id: str | None,
) -> dict:
    """Ask the backend to enqueue stale per-contract analysis after primitive extraction."""
    if not contract_id:
        return {"status": "skipped", "reason": "missing_contract_id"}

    backend_url = get_backend_api_url()
    token = get_internal_service_token()
    if not backend_url or not token:
        return {"status": "skipped", "reason": "analysis_trigger_not_configured"}

    payload = json.dumps(
        {
            "document_upload_id": doc_id,
            "extraction_run_id": extraction_run_id,
        }
    ).encode("utf-8")
    request = Request(
        f"{backend_url}/api/internal/contracts/{contract_id}/performance-analysis",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Internal-Service-Token": token,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {
            "status": "failed",
            "reason": "backend_rejected_trigger",
            "status_code": exc.code,
            "detail": detail,
        }
    except URLError as exc:
        return {"status": "failed", "reason": "backend_unreachable", "detail": str(exc)}
    except TimeoutError as exc:
        return {"status": "failed", "reason": "backend_timeout", "detail": str(exc)}

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "failed", "reason": "invalid_backend_response", "detail": raw}
