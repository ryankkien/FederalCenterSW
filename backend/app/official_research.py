from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List
from urllib.request import Request, urlopen

from app.contract_analysis import is_official_external_source


@dataclass(frozen=True)
class OfficialSourceCandidate:
    url: str
    title: str
    citation_text: str


def official_source_candidates(question: str) -> List[OfficialSourceCandidate]:
    text = question.lower()
    candidates = []
    if any(term in text for term in ("cor", "contracting officer", "direction", "scope")):
        candidates.append(
            OfficialSourceCandidate(
                url="https://www.acquisition.gov/far/1.602-2",
                title="FAR 1.602-2 Responsibilities",
                citation_text="Contracting officers are responsible for ensuring performance of all necessary actions for effective contracting.",
            )
        )
    if any(term in text for term in ("performance", "quality", "surveillance", "inspection")):
        candidates.append(
            OfficialSourceCandidate(
                url="https://www.acquisition.gov/far/46.401",
                title="FAR 46.401 General",
                citation_text="Government contract quality assurance must be performed before acceptance except as otherwise provided.",
            )
        )
    if any(term in text for term in ("delay", "cost", "change", "modification", "equitable")):
        candidates.append(
            OfficialSourceCandidate(
                url="https://www.acquisition.gov/far/43.201",
                title="FAR 43.201 General",
                citation_text="Generally, government contracts contain a changes clause that permits contract modifications within scope.",
            )
        )
    if not candidates:
        candidates.append(
            OfficialSourceCandidate(
                url="https://www.acquisition.gov/far",
                title="Federal Acquisition Regulation",
                citation_text="Acquisition.gov publishes the Federal Acquisition Regulation.",
            )
        )
    return [candidate for candidate in candidates if is_official_external_source(candidate.url)]


def fetch_official_source_text(url: str, timeout_seconds: float = 8.0) -> str:
    if not is_official_external_source(url):
        raise ValueError("External research source is not in the official-source allowlist")
    request = Request(url, headers={"User-Agent": "FederalCenterSW/0.1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        data = response.read(256_000)
    return _clean_text(data.decode("utf-8", errors="replace"))


def summarize_official_source(question: str, title: str, text: str, fallback: str) -> str:
    if not text.strip():
        return fallback
    words = [word for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", question.lower())]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        lower = sentence.lower()
        if any(word in lower for word in words):
            return sentence[:900].strip()
    return f"{title}: {text[:700].strip()}"


def _clean_text(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.IGNORECASE | re.DOTALL)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()
