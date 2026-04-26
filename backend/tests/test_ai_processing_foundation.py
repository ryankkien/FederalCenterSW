import json

from app.ai.providers import AIContractHint, NullAIProvider, StructuredAnalysisResult, get_ai_provider
from app.chunking import chunk_text
from app.config import (
    get_ai_inline_processing_enabled,
    get_ai_processing_enabled,
    get_openai_llm_model,
)
from app.contract_analysis import classify_document
from app.contract_matching import ContractMatchContext, match_contract
from app.processing import TextJsonPayload, gate_text_payload, process_document_upload


class MemoryStorage:
    def __init__(self):
        self.objects = {}

    def upload_bytes(self, path, data, content_type):
        self.objects[path] = {"data": data, "content_type": content_type}

    def download_bytes(self, path):
        return self.objects[path]["data"]

    def create_read_url(self, path, expires_in_minutes=15):
        return path


class CountingProvider(NullAIProvider):
    def __init__(self):
        super().__init__("test")
        self.extract_calls = 0
        self._status.available = True
        self._status.enabled = True
        self._status.name = "counting"

    def extract_document_signals(self, request):
        self.extract_calls += 1
        return super().extract_document_signals(request)


class ClassificationProvider(NullAIProvider):
    def __init__(self, document_kind="ipmdar_pnr", confidence=0.91):
        super().__init__("test")
        self.classify_calls = 0
        self.document_kind = document_kind
        self.confidence = confidence
        self._status.available = True
        self._status.enabled = True
        self._status.name = "classification-test"

    def classify_document(self, payload):
        self.classify_calls += 1
        return StructuredAnalysisResult(
            provider=self.status.name,
            data={
                "document_kind": self.document_kind,
                "confidence": self.confidence,
                "rationale": f"The document is classified as {self.document_kind}.",
            },
        )


class MatchProvider(NullAIProvider):
    def __init__(self):
        super().__init__("test")
        self._status.available = True
        self._status.enabled = True
        self._status.name = "match-test"

    def suggest_contract_matches(self, context, candidate_contract_numbers):
        return [
            AIContractHint(
                contract_number="N00014-12-C-0305",
                confidence=0.93,
                rationale="The report narrative names the AGOR contract family.",
            )
        ]


def test_ai_defaults_enabled_but_unavailable_without_openai_key(monkeypatch):
    monkeypatch.delenv("AI_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("AI_INLINE_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = get_ai_provider()

    assert get_ai_processing_enabled() is True
    assert get_ai_inline_processing_enabled() is True
    assert provider.status.name == "null"
    assert provider.status.enabled is False
    assert provider.status.available is False
    assert provider.status.reason == "OPENAI_API_KEY is not configured"


def test_ai_flags_default_on_when_openai_key_is_present(monkeypatch):
    monkeypatch.delenv("AI_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("AI_INLINE_PROCESSING_ENABLED", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    assert get_ai_processing_enabled() is True
    assert get_ai_inline_processing_enabled() is True


def test_ai_flags_can_force_disable_with_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AI_PROCESSING_ENABLED", "false")
    monkeypatch.setenv("AI_INLINE_PROCESSING_ENABLED", "false")

    assert get_ai_processing_enabled() is False
    assert get_ai_inline_processing_enabled() is False


def test_openai_llm_default_matches_current_config(monkeypatch):
    monkeypatch.delenv("OPENAI_LLM_MODEL", raising=False)

    assert get_openai_llm_model() == "gpt-5.5"


def test_contract_matching_finds_wwr_contract_from_filename():
    result = match_contract(
        contracts=[{"id": "wwr", "contract_number": "M0026426R0001"}],
        context=ContractMatchContext(filename="D.1+RFP+M0026426R0001 (2).pdf"),
    )

    assert result.status == "matched"
    assert result.source == "deterministic"
    assert result.matched_contract_id == "wwr"


def test_contract_matching_uses_ai_before_regex_fallback():
    result = match_contract(
        contracts=[
            {"id": "wwr", "contract_number": "M0026426R0001"},
            {"id": "agor", "contract_number": "N00014-12-C-0305"},
        ],
        context=ContractMatchContext(filename="D.1+RFP+M0026426R0001 (2).pdf"),
        ai_provider=MatchProvider(),
    )

    assert result.status == "matched"
    assert result.source == "ai"
    assert result.matched_contract_id == "agor"


def test_document_classification_uses_ai_and_reuses_result():
    provider = ClassificationProvider()
    document = {
        "original_filename": "IPMDAR_PNR_Submission1_Month06_Mar2025.docx",
        "title": "Submission 1",
        "document_kind": "other",
        "metadata_json": {},
    }

    first = classify_document(document, "Integrated Program Management Data and Analysis Report", provider)
    second = classify_document(document, "Integrated Program Management Data and Analysis Report", provider)

    assert first == ("ipmdar_pnr", None)
    assert second == ("ipmdar_pnr", None)
    assert provider.classify_calls == 1
    assert document["metadata_json"]["classification"]["source"] == "ai"


def test_document_classification_accepts_ai_cdrl_and_other_kinds():
    for expected_kind in ("cdrl", "other"):
        provider = ClassificationProvider(document_kind=expected_kind)
        document = {
            "original_filename": f"{expected_kind}.pdf",
            "title": expected_kind,
            "document_kind": "source_contract",
            "metadata_json": {},
        }

        result = classify_document(document, "Ambiguous administrative document text", provider)

        assert result == (expected_kind, None)
        assert document["document_kind"] == expected_kind
        assert document["metadata_json"]["classification"]["source"] == "ai"


def test_contract_matching_finds_agor_contract_from_text():
    result = match_contract(
        contracts=[{"id": "agor", "contract_number": "N00014-12-C-0305"}],
        context=ContractMatchContext(text="Monthly report for contract N00014-12-C-0305."),
    )

    assert result.status == "matched"
    assert result.source == "deterministic"
    assert result.matched_contract_number == "N00014-12-C-0305"


def test_contract_matching_preserves_hints_without_known_contracts():
    result = match_contract(
        contracts=[],
        context=ContractMatchContext(text="Source contract N40080-26-C-1001 for review."),
    )

    assert result.status == "unmatched"
    assert result.hints == ["N40080-26-C-1001"]


def test_gate_failed_empty_text_without_ai_call():
    provider = CountingProvider()
    storage = MemoryStorage()
    storage.upload_bytes(
        "contracts/doc-1/text.json",
        json.dumps(
            {
                "document_id": "doc-1",
                "original_filename": "scan.pdf",
                "text": "",
                "extraction_status": "failed",
                "extraction_error": "PDF OCR completed but produced no text",
            }
        ).encode("utf-8"),
        "application/json",
    )

    result = process_document_upload({"id": "doc-1", "title": "Scan"}, storage, [], provider)

    assert result.status == "failed"
    assert result.text_gate.reason == "PDF OCR completed but produced no text"
    assert provider.extract_calls == 0


def test_gate_empty_text_no_extractable_text():
    gate = gate_text_payload(
        TextJsonPayload(
            document_id="doc-1",
            text=" \n ",
            extraction_status="extracted",
        )
    )

    assert gate.status == "no_extractable_text"


def test_chunk_text_has_offsets_and_overlap():
    text = ("Alpha beta gamma delta. " * 1000).strip()
    chunks = chunk_text(text, target_tokens=900, overlap_tokens=100)

    assert len(chunks) > 1
    assert chunks[0].start_char == 0
    assert chunks[0].end_char <= len(text)
    assert chunks[1].start_char < chunks[0].end_char
    assert all(chunk.text for chunk in chunks)
