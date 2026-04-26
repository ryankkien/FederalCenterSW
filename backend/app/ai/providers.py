from __future__ import annotations

import json
from typing import Dict, List, Optional, Protocol, Sequence

from pydantic import BaseModel, Field

from app.config import (
    get_ai_max_retries,
    get_ai_processing_enabled,
    get_ai_provider_name,
    get_ai_request_timeout_seconds,
    get_openai_api_key,
    get_openai_embedding_dimensions,
    get_openai_embedding_model,
    get_openai_llm_model,
)


class AIProviderStatus(BaseModel):
    name: str
    enabled: bool
    available: bool
    reason: Optional[str] = None


class AIContractHint(BaseModel):
    contract_number: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: Optional[str] = None


class DocumentSignal(BaseModel):
    category: str
    label: str
    summary: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)


class ProcessingSignalRequest(BaseModel):
    document_id: str
    title: Optional[str] = None
    document_type: Optional[str] = None
    chunks: List[str] = Field(default_factory=list)


class AIProcessingResult(BaseModel):
    provider: str
    model: Optional[str] = None
    signals: List[DocumentSignal] = Field(default_factory=list)
    raw: Dict[str, object] = Field(default_factory=dict)


class StructuredAnalysisResult(BaseModel):
    provider: str
    model: Optional[str] = None
    prompt_version: str = "deterministic_fallback_v1"
    data: Dict[str, object] = Field(default_factory=dict)
    raw: Dict[str, object] = Field(default_factory=dict)


class AIProvider(Protocol):
    @property
    def status(self) -> AIProviderStatus:
        ...

    def suggest_contract_matches(
        self,
        context: str,
        candidate_contract_numbers: Sequence[str],
    ) -> List[AIContractHint]:
        ...

    def extract_document_signals(
        self,
        request: ProcessingSignalRequest,
    ) -> AIProcessingResult:
        ...

    def extract_baseline(self, text: str) -> StructuredAnalysisResult:
        ...

    def extract_report_facts(self, text: str) -> StructuredAnalysisResult:
        ...

    def compare_regressions(self, baseline: str, report: str) -> StructuredAnalysisResult:
        ...

    def update_hypothesis(self, hypothesis: str, evidence: Sequence[str]) -> StructuredAnalysisResult:
        ...

    def summarize_external_source(self, question: str, source_text: str) -> StructuredAnalysisResult:
        ...

    def build_contract_onboarding(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        ...

    def build_contractor_profile(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        ...

    def generate_wiki_links(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        ...

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        ...


class NullAIProvider:
    def __init__(self, reason: str = "AI processing is disabled") -> None:
        self._status = AIProviderStatus(
            name="null",
            enabled=False,
            available=False,
            reason=reason,
        )

    @property
    def status(self) -> AIProviderStatus:
        return self._status

    def suggest_contract_matches(
        self,
        context: str,
        candidate_contract_numbers: Sequence[str],
    ) -> List[AIContractHint]:
        return []

    def extract_document_signals(
        self,
        request: ProcessingSignalRequest,
    ) -> AIProcessingResult:
        return AIProcessingResult(provider=self.status.name, signals=[])

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        return []

    def extract_baseline(self, text: str) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def extract_report_facts(self, text: str) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def compare_regressions(self, baseline: str, report: str) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def update_hypothesis(self, hypothesis: str, evidence: Sequence[str]) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def summarize_external_source(self, question: str, source_text: str) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def build_contract_onboarding(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def build_contractor_profile(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})

    def generate_wiki_links(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return StructuredAnalysisResult(provider=self.status.name, data={})


class OpenAIProvider:
    def __init__(
        self,
        api_key: str,
        llm_model: str,
        embedding_model: str,
        embedding_dimensions: Optional[int],
        timeout_seconds: float,
        max_retries: int,
    ) -> None:
        try:
            from openai import OpenAI
        except ImportError as error:
            raise RuntimeError("openai package is not installed") from error

        self._client = OpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._llm_model = llm_model
        self._embedding_model = embedding_model
        self._embedding_dimensions = embedding_dimensions
        self._status = AIProviderStatus(name="openai", enabled=True, available=True)

    @property
    def status(self) -> AIProviderStatus:
        return self._status

    def suggest_contract_matches(
        self,
        context: str,
        candidate_contract_numbers: Sequence[str],
    ) -> List[AIContractHint]:
        candidates = [number for number in candidate_contract_numbers if number]
        if not context.strip() or not candidates:
            return []

        payload = {
            "context": context[:6000],
            "candidate_contract_numbers": candidates[:50],
        }
        response = self._client.chat.completions.create(
            model=self._llm_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return JSON with a 'matches' array. Each match must include "
                        "contract_number, confidence from 0 to 1, and a short rationale. "
                        "Only choose from the provided candidate_contract_numbers."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
        )
        data = _json_response(response)
        return _contract_hints_from_json(data, candidates)

    def extract_document_signals(
        self,
        request: ProcessingSignalRequest,
    ) -> AIProcessingResult:
        chunks = [chunk for chunk in request.chunks if chunk.strip()]
        if not chunks:
            return AIProcessingResult(provider=self.status.name, model=self._llm_model, signals=[])

        payload = {
            "document_id": request.document_id,
            "title": request.title,
            "document_type": request.document_type,
            "chunks": chunks[:20],
        }
        response = self._client.chat.completions.create(
            model=self._llm_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Extract contract performance signals as JSON with a 'signals' array. "
                        "Use categories such as timeliness, cost, risks, delays, staffing, "
                        "deliverables, inconsistencies, successes, lessons_learned, and "
                        "benchmarking. Include short evidence snippets only when present."
                    ),
                },
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
        )
        data = _json_response(response)
        return AIProcessingResult(
            provider=self.status.name,
            model=self._llm_model,
            signals=_signals_from_json(data),
            raw=data,
        )

    def embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        inputs = [text for text in texts if text.strip()]
        if not inputs:
            return []

        kwargs = {
            "model": self._embedding_model,
            "input": inputs,
        }
        if self._embedding_dimensions:
            kwargs["dimensions"] = self._embedding_dimensions
        response = self._client.embeddings.create(**kwargs)
        return [list(item.embedding) for item in response.data]

    def extract_baseline(self, text: str) -> StructuredAnalysisResult:
        return self._structured_json(
            "baseline_extraction_v1",
            "Extract contract baseline obligations as JSON.",
            {"text": text[:12000]},
        )

    def extract_report_facts(self, text: str) -> StructuredAnalysisResult:
        return self._structured_json(
            "report_fact_extraction_v1",
            "Extract report facts, entities, metrics, and citations as JSON.",
            {"text": text[:12000]},
        )

    def compare_regressions(self, baseline: str, report: str) -> StructuredAnalysisResult:
        return self._structured_json(
            "regression_compare_v1",
            "Compare report text against the baseline and return cited regressions as JSON.",
            {"baseline": baseline[:8000], "report": report[:12000]},
        )

    def update_hypothesis(self, hypothesis: str, evidence: Sequence[str]) -> StructuredAnalysisResult:
        return self._structured_json(
            "hypothesis_update_v1",
            "Update hypothesis status from evidence as JSON.",
            {"hypothesis": hypothesis, "evidence": list(evidence)[:20]},
        )

    def summarize_external_source(self, question: str, source_text: str) -> StructuredAnalysisResult:
        return self._structured_json(
            "external_source_summary_v1",
            "Summarize official source text relevant to the question as JSON.",
            {"question": question, "source_text": source_text[:12000]},
        )

    def build_contract_onboarding(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return self._structured_json(
            "contract_onboarding_wiki_v1",
            (
                "Create a cited contract onboarding wiki article as JSON. Use only supplied facts. "
                "Return concise sections, limitations, and no unsupported claims."
            ),
            payload,
        )

    def build_contractor_profile(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return self._structured_json(
            "contractor_profile_wiki_v1",
            (
                "Create a contractor evidence profile as JSON. Use cautious evidence labels, "
                "not moral judgments, and return limitations for missing performance data."
            ),
            payload,
        )

    def generate_wiki_links(self, payload: Dict[str, object]) -> StructuredAnalysisResult:
        return self._structured_json(
            "knowledge_link_generation_v1",
            "Generate semantic wiki links as JSON using only supplied node metadata.",
            payload,
        )

    def _structured_json(
        self,
        prompt_version: str,
        instruction: str,
        payload: Dict[str, object],
    ) -> StructuredAnalysisResult:
        response = self._client.chat.completions.create(
            model=self._llm_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": instruction},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
        )
        data = _json_response(response)
        return StructuredAnalysisResult(
            provider=self.status.name,
            model=self._llm_model,
            prompt_version=prompt_version,
            data=data,
            raw=data,
        )


def get_ai_provider() -> AIProvider:
    if not get_ai_processing_enabled():
        return NullAIProvider()

    provider_name = get_ai_provider_name()
    if provider_name != "openai":
        return NullAIProvider(reason=f"Unsupported AI_PROVIDER '{provider_name}'")

    api_key = get_openai_api_key()
    if not api_key:
        return NullAIProvider(reason="OPENAI_API_KEY is not configured")

    try:
        return OpenAIProvider(
            api_key=api_key,
            llm_model=get_openai_llm_model(),
            embedding_model=get_openai_embedding_model(),
            embedding_dimensions=get_openai_embedding_dimensions(),
            timeout_seconds=get_ai_request_timeout_seconds(),
            max_retries=get_ai_max_retries(),
        )
    except RuntimeError as error:
        return NullAIProvider(reason=str(error))


def _json_response(response: object) -> Dict[str, object]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return {}
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", None)
    if not content:
        return {}
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _contract_hints_from_json(
    data: Dict[str, object],
    candidates: Sequence[str],
) -> List[AIContractHint]:
    allowed = {candidate.upper(): candidate for candidate in candidates}
    raw_matches = data.get("matches", [])
    if not isinstance(raw_matches, list):
        return []

    hints = []
    for item in raw_matches:
        if not isinstance(item, dict):
            continue
        contract_number = str(item.get("contract_number") or "").upper()
        if contract_number not in allowed:
            continue
        hints.append(
            AIContractHint(
                contract_number=allowed[contract_number],
                confidence=_float_value(item.get("confidence")),
                rationale=str(item.get("rationale") or "")[:300] or None,
            )
        )
    return hints


def _signals_from_json(data: Dict[str, object]) -> List[DocumentSignal]:
    raw_signals = data.get("signals", [])
    if not isinstance(raw_signals, list):
        return []

    signals = []
    for item in raw_signals:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        label = str(item.get("label") or category or "signal").strip()
        summary = str(item.get("summary") or "").strip()
        if not category or not summary:
            continue
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        signals.append(
            DocumentSignal(
                category=category[:80],
                label=label[:120],
                summary=summary[:1200],
                confidence=_float_value(item.get("confidence")),
                evidence=[str(value)[:500] for value in evidence if str(value).strip()][:5],
            )
        )
    return signals


def _float_value(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return min(1.0, max(0.0, number))
