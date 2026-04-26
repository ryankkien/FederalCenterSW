from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config import get_cpars_import_dir, get_regulations_api_key, get_sam_api_key


OPEN_SOURCE_GROUP = ("usaspending", "federal_register", "acquisition")
OPTIONAL_SOURCE_GROUP = ("sam", "regulations", "cpars")


@dataclass(frozen=True)
class KnowledgeSourceDocument:
    source_name: str
    source_key: str
    title: str
    source_type: str = "official"
    status: str = "available"
    unavailable_reason: Optional[str] = None
    url: Optional[str] = None
    text: Optional[str] = None
    raw_json: Dict[str, Any] = field(default_factory=dict)
    source_timestamp: Optional[datetime] = None
    contract_id: Optional[str] = None
    vendor_uei: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def normalize_sources(sources: Optional[Sequence[str]]) -> List[str]:
    requested = [source.strip().lower() for source in (sources or ("open",)) if source.strip()]
    if not requested:
        requested = ["open"]
    normalized: List[str] = []
    for source in requested:
        if source == "open":
            normalized.extend(OPEN_SOURCE_GROUP)
        elif source == "optional":
            normalized.extend(OPTIONAL_SOURCE_GROUP)
        else:
            normalized.append(source)
    return sorted(set(normalized))


def collect_contract_source_documents(
    contract: object,
    sources: Sequence[str],
    limit: int,
) -> List[KnowledgeSourceDocument]:
    documents: List[KnowledgeSourceDocument] = []
    for source in normalize_sources(sources):
        try:
            if source == "usaspending":
                documents.extend(_usaspending_contract_awards(contract, limit))
            elif source == "federal_register":
                documents.extend(_federal_register_documents(contract, max(1, min(limit, 10))))
            elif source == "acquisition":
                documents.extend(_acquisition_context(contract))
            elif source == "sam":
                documents.extend(_sam_documents(contract, limit))
            elif source == "regulations":
                documents.extend(_regulations_documents(contract, limit))
            elif source == "cpars":
                documents.extend(_cpars_import_documents(contract, limit))
            else:
                documents.append(_unavailable(source, "unknown_source", f"Source '{source}' is not configured."))
        except Exception as error:
            documents.append(_unavailable(source, "fetch_error", str(error)[:500]))
    return documents[: max(1, limit)]


def _usaspending_contract_awards(contract: object, limit: int) -> List[KnowledgeSourceDocument]:
    contract_number = _attr(contract, "contract_number", "id") or ""
    vendor_uei = _attr(contract, "vendor_uei")
    vendor_name = _attr(contract, "vendor_name")
    keywords = [item for item in (contract_number, vendor_uei, vendor_name) if item]
    if not keywords:
        return [_unavailable("usaspending", "missing_query", "Contract has no number, UEI, or vendor name.")]

    payload = {
        "filters": {
            "award_type_codes": ["A", "B", "C", "D"],
            "keywords": keywords[:3],
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Recipient UEI",
            "Award Amount",
            "Awarding Agency",
            "Awarding Sub Agency",
            "Start Date",
            "End Date",
            "Award Type",
            "Award Description",
            "PSC",
            "NAICS",
        ],
        "limit": max(1, min(limit, 100)),
        "page": 1,
        "sort": "Award Amount",
        "order": "desc",
        "spending_level": "awards",
    }
    data = _fetch_json(
        "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        method="POST",
        body=payload,
    )
    results = data.get("results", [])
    if not isinstance(results, list) or not results:
        return [
            KnowledgeSourceDocument(
                source_name="usaspending",
                source_key=f"usaspending:no-results:{contract_number or vendor_uei or vendor_name}",
                title="USAspending award search returned no records",
                status="available",
                text="No USAspending award records matched the contract identifiers used for this ingestion run.",
                raw_json={"request": payload, "response": data},
                contract_id=_attr(contract, "id"),
                vendor_uei=vendor_uei,
                metadata={"record_type": "no_results"},
            )
        ]

    documents = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        award_id = str(item.get("Award ID") or item.get("generated_internal_id") or item)
        recipient = str(item.get("Recipient Name") or "Unknown recipient")
        amount = item.get("Award Amount")
        description = str(item.get("Award Description") or "")
        documents.append(
            KnowledgeSourceDocument(
                source_name="usaspending",
                source_key=f"award:{award_id}",
                title=f"USAspending award {award_id}",
                url=f"https://www.usaspending.gov/search/?hash={award_id}",
                text=(
                    f"Award {award_id} to {recipient}. Award amount: {amount}. "
                    f"Agency: {item.get('Awarding Agency')}. Description: {description}"
                ),
                raw_json=item,
                contract_id=_attr(contract, "id"),
                vendor_uei=str(item.get("Recipient UEI") or vendor_uei or "") or None,
                metadata={"record_type": "award", "recipient_name": recipient},
            )
        )
    return documents


def _federal_register_documents(contract: object, limit: int) -> List[KnowledgeSourceDocument]:
    terms = _query_terms(contract)
    if not terms:
        return [_unavailable("federal_register", "missing_query", "No contract terms available.")]
    query = {
        "conditions[term]": " ".join(terms[:4]),
        "per_page": str(max(1, min(limit, 20))),
        "order": "newest",
    }
    data = _fetch_json(f"https://www.federalregister.gov/api/v1/documents.json?{urlencode(query)}")
    results = data.get("results", [])
    if not isinstance(results, list):
        results = []
    documents: List[KnowledgeSourceDocument] = []
    for item in results[:limit]:
        if not isinstance(item, dict):
            continue
        number = str(item.get("document_number") or item.get("html_url") or item.get("title"))
        text = " ".join(
            str(item.get(key) or "")
            for key in ("title", "abstract", "type", "publication_date")
            if item.get(key)
        )
        documents.append(
            KnowledgeSourceDocument(
                source_name="federal_register",
                source_key=f"document:{number}",
                title=str(item.get("title") or "Federal Register document")[:500],
                url=item.get("html_url") or item.get("pdf_url"),
                text=text,
                raw_json=item,
                source_timestamp=_parse_date(item.get("publication_date")),
                contract_id=_attr(contract, "id"),
                vendor_uei=_attr(contract, "vendor_uei"),
                metadata={"record_type": "federal_register_document"},
            )
        )
    return documents or [
        KnowledgeSourceDocument(
            source_name="federal_register",
            source_key=f"federal-register:no-results:{_attr(contract, 'id', 'contract_number')}",
            title="Federal Register search returned no records",
            text="No Federal Register records matched the contract terms used for this ingestion run.",
            raw_json={"request": query, "response": data},
            contract_id=_attr(contract, "id"),
            vendor_uei=_attr(contract, "vendor_uei"),
            metadata={"record_type": "no_results"},
        )
    ]


def _acquisition_context(contract: object) -> List[KnowledgeSourceDocument]:
    candidates = [
        ("far-1.602-2", "FAR 1.602-2 Responsibilities", "https://www.acquisition.gov/far/1.602-2"),
        ("far-42.15", "FAR Subpart 42.15 Contractor Performance Information", "https://www.acquisition.gov/far/subpart-42.15"),
        ("far-43.201", "FAR 43.201 General", "https://www.acquisition.gov/far/43.201"),
        ("far-46.401", "FAR 46.401 General", "https://www.acquisition.gov/far/46.401"),
    ]
    documents = []
    for key, title, url in candidates:
        text = ""
        try:
            text = _fetch_text(url)
        except Exception:
            text = title
        documents.append(
            KnowledgeSourceDocument(
                source_name="acquisition",
                source_key=key,
                title=title,
                url=url,
                text=_clean_text(text)[:4000] or title,
                raw_json={"url": url},
                contract_id=_attr(contract, "id"),
                vendor_uei=_attr(contract, "vendor_uei"),
                metadata={"record_type": "far_reference"},
            )
        )
    return documents


def _sam_documents(contract: object, limit: int) -> List[KnowledgeSourceDocument]:
    api_key = get_sam_api_key()
    if not api_key:
        return [_unavailable("sam", "missing_api_key", "SAM_API_KEY is not configured.")]
    contract_number = _attr(contract, "contract_number")
    if not contract_number:
        return [_unavailable("sam", "missing_contract_number", "Contract has no contract number.")]
    query = urlencode({"api_key": api_key, "noticeid": contract_number, "limit": str(max(1, min(limit, 100)))})
    data = _fetch_json(f"https://api.sam.gov/prod/opportunities/v2/search?{query}")
    return [
        KnowledgeSourceDocument(
            source_name="sam",
            source_key=f"sam:{contract_number}",
            title=f"SAM.gov opportunity search for {contract_number}",
            url="https://sam.gov/contracting",
            text=json.dumps(data, sort_keys=True)[:8000],
            raw_json=data,
            contract_id=_attr(contract, "id"),
            vendor_uei=_attr(contract, "vendor_uei"),
            metadata={"record_type": "sam_search"},
        )
    ]


def _regulations_documents(contract: object, limit: int) -> List[KnowledgeSourceDocument]:
    api_key = get_regulations_api_key()
    if not api_key:
        return [_unavailable("regulations", "missing_api_key", "REGULATIONS_API_KEY is not configured.")]
    term = " ".join(_query_terms(contract)[:4])
    if not term:
        return [_unavailable("regulations", "missing_query", "No contract terms available.")]
    query = urlencode({"filter[searchTerm]": term, "page[size]": str(max(1, min(limit, 250)))})
    data = _fetch_json(
        f"https://api.regulations.gov/v4/documents?{query}",
        headers={"X-Api-Key": api_key},
    )
    records = data.get("data", [])
    if not isinstance(records, list):
        records = []
    return [
        KnowledgeSourceDocument(
            source_name="regulations",
            source_key=f"regulations:{item.get('id')}",
            title=str((item.get("attributes") or {}).get("title") or item.get("id") or "Regulations.gov document"),
            url=f"https://www.regulations.gov/document/{item.get('id')}",
            text=json.dumps(item, sort_keys=True)[:8000],
            raw_json=item,
            contract_id=_attr(contract, "id"),
            vendor_uei=_attr(contract, "vendor_uei"),
            metadata={"record_type": "regulations_document"},
        )
        for item in records[:limit]
        if isinstance(item, dict)
    ]


def _cpars_import_documents(contract: object, limit: int) -> List[KnowledgeSourceDocument]:
    import_dir = get_cpars_import_dir()
    if not import_dir:
        return [_unavailable("cpars", "missing_import_dir", "CPARS_IMPORT_DIR is not configured.")]
    if not import_dir.exists():
        return [_unavailable("cpars", "missing_import_dir", f"CPARS_IMPORT_DIR does not exist: {import_dir}")]
    terms = {str(value).lower() for value in (_attr(contract, "contract_number"), _attr(contract, "vendor_uei"), _attr(contract, "vendor_name")) if value}
    documents: List[KnowledgeSourceDocument] = []
    for path in sorted(import_dir.glob("*.json"))[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = json.dumps(data, sort_keys=True)
        if terms and not any(term in text.lower() for term in terms):
            continue
        documents.append(
            KnowledgeSourceDocument(
                source_name="cpars",
                source_key=f"cpars:{path.name}",
                title=str(data.get("title") or data.get("contract_number") or path.name),
                source_type="authorized_import",
                text=text[:20_000],
                raw_json=data,
                contract_id=_attr(contract, "id"),
                vendor_uei=str(data.get("vendor_uei") or _attr(contract, "vendor_uei") or "") or None,
                metadata={"record_type": "cpars_authorized_import", "path": str(path)},
            )
        )
    return documents or [
        KnowledgeSourceDocument(
            source_name="cpars",
            source_key=f"cpars:no-import:{_attr(contract, 'id', 'contract_number')}",
            title="No matching CPARS import records",
            source_type="authorized_import",
            status="unavailable",
            unavailable_reason="No authorized CPARS import files matched this contract.",
            contract_id=_attr(contract, "id"),
            vendor_uei=_attr(contract, "vendor_uei"),
        )
    ]


def _fetch_json(
    url: str,
    method: str = "GET",
    body: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout_seconds: float = 12.0,
) -> Dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request_headers = {"User-Agent": "FederalCenterSW/0.1", "Accept": "application/json"}
    if data is not None:
        request_headers["Content-Type"] = "application/json"
    if headers:
        request_headers.update(headers)
    request = Request(url, data=data, method=method, headers=request_headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        raw = response.read(1_000_000)
    parsed = json.loads(raw.decode("utf-8", errors="replace"))
    return parsed if isinstance(parsed, dict) else {"results": parsed}


def _fetch_text(url: str, timeout_seconds: float = 8.0) -> str:
    request = Request(url, headers={"User-Agent": "FederalCenterSW/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read(300_000).decode("utf-8", errors="replace")


def _unavailable(source_name: str, source_key: str, reason: str) -> KnowledgeSourceDocument:
    return KnowledgeSourceDocument(
        source_name=source_name,
        source_key=f"{source_name}:{source_key}",
        title=f"{source_name} source unavailable",
        status="unavailable",
        unavailable_reason=reason,
        text=reason,
        raw_json={"reason": reason},
        metadata={"record_type": "source_unavailable"},
    )


def _query_terms(contract: object) -> List[str]:
    values = [
        _attr(contract, "contract_number"),
        _attr(contract, "title"),
        _attr(contract, "vendor_name"),
        _attr(contract, "agency_name"),
        _attr(contract, "psc_code"),
        _attr(contract, "naics_code"),
    ]
    return [str(value) for value in values if value]


def _parse_date(value: object) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _attr(row: object, *names: str) -> Optional[str]:
    for name in names:
        value = getattr(row, name, None)
        if value:
            return str(value)
    return None
