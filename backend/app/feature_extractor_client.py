from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from app.config import get_feature_extractor_request_timeout_seconds, get_feature_extractor_url
from app.observability import outbound_request_headers


@dataclass(frozen=True)
class FeatureExtractorStepResult:
    step_name: str
    event_type: str
    status: str
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def trigger_feature_extractor(
    document_id: str,
    contract_id: Optional[str],
    doc_classification: str,
    processing_run_id: Optional[str] = None,
    service_url: Optional[str] = None,
) -> list[FeatureExtractorStepResult]:
    base_url = (service_url or get_feature_extractor_url() or "").strip().rstrip("/")
    if not base_url:
        return []

    headers = outbound_request_headers(
        {
            "X-Document-Upload-ID": document_id,
            **({"X-Contract-ID": contract_id} if contract_id else {}),
            **({"X-Processing-Run-ID": processing_run_id} if processing_run_id else {}),
        }
    )

    summary_metadata: Dict[str, Any] = {"endpoint": "/summarize", "service_url": base_url}
    try:
        summary = _post_json(
            base_url,
            "/summarize",
            {"doc_id": document_id, "contract_id": contract_id},
            headers=headers,
        )
    except Exception as error:
        return [
            FeatureExtractorStepResult(
                step_name="feature_extractor.summary",
                event_type="feature_extractor.summary",
                status="failed",
                message=str(error),
                metadata=summary_metadata,
            )
        ]

    summary_metadata.update(
        {
            "blob_path": summary.get("blob_path"),
            "model": summary.get("model"),
            "classification": summary.get("classification"),
        }
    )
    steps = [
        FeatureExtractorStepResult(
            step_name="feature_extractor.summary",
            event_type="feature_extractor.summary",
            status="success",
            metadata=summary_metadata,
        )
    ]

    primitives_payload = {
        "doc_id": document_id,
        "contract_id": contract_id,
        "doc_classification": doc_classification or "other",
    }
    primitives_metadata: Dict[str, Any] = {
        "endpoint": "/extract-primitives",
        "service_url": base_url,
        "doc_classification": primitives_payload["doc_classification"],
    }
    try:
        primitives = _post_json(
            base_url,
            "/extract-primitives",
            primitives_payload,
            headers=headers,
        )
    except Exception as error:
        steps.append(
            FeatureExtractorStepResult(
                step_name="feature_extractor.primitives",
                event_type="feature_extractor.primitives",
                status="failed",
                message=str(error),
                metadata=primitives_metadata,
            )
        )
        return steps

    primitives_metadata.update(
        {
            "extraction_run_id": primitives.get("extraction_run_id"),
            "primitives_extracted": primitives.get("primitives_extracted", {}),
        }
    )
    steps.append(
        FeatureExtractorStepResult(
            step_name="feature_extractor.primitives",
            event_type="feature_extractor.primitives",
            status="success",
            metadata=primitives_metadata,
        )
    )
    return steps


def _post_json(
    base_url: str,
    path: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    timeout = get_feature_extractor_request_timeout_seconds()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{base_url}{path}", json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            detail = _response_detail(error.response)
            raise RuntimeError(f"{path} returned HTTP {error.response.status_code}: {detail}") from error
        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(f"{path} returned a non-JSON response") from error
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} returned an unexpected response shape")
    return data


def _response_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    if isinstance(data, dict):
        detail = data.get("detail")
        return str(detail)[:500] if detail is not None else str(data)[:500]
    return str(data)[:500]
