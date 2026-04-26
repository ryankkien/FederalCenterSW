import json

from app.ai.providers import NullAIProvider, get_ai_provider
from app.chunking import chunk_text
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


def test_default_ai_provider_is_null_when_disabled(monkeypatch):
    monkeypatch.delenv("AI_PROCESSING_ENABLED", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = get_ai_provider()

    assert provider.status.name == "null"
    assert provider.status.available is False


def test_contract_matching_finds_wwr_contract_from_filename():
    result = match_contract(
        contracts=[{"id": "wwr", "contract_number": "M0026426R0001"}],
        context=ContractMatchContext(filename="D.1+RFP+M0026426R0001 (2).pdf"),
    )

    assert result.status == "matched"
    assert result.source == "deterministic"
    assert result.matched_contract_id == "wwr"


def test_contract_matching_finds_agor_contract_from_text():
    result = match_contract(
        contracts=[{"id": "agor", "contract_number": "N00014-12-C-0305"}],
        context=ContractMatchContext(text="Monthly report for contract N00014-12-C-0305."),
    )

    assert result.status == "matched"
    assert result.source == "deterministic"
    assert result.matched_contract_number == "N00014-12-C-0305"


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
