import json
from pathlib import Path
from typing import Union

from app.synthetic_corpus import SYNTHETIC_DOCUMENTS, build_synthetic_corpus


def test_build_synthetic_corpus_marks_generated_documents_and_real_anchors(tmp_path) -> None:
    fixture_root = tmp_path / "testdocs"
    _write_fixture_file(fixture_root / "WWR" / "contract" / "D.1+RFP+M0026426R0001 (2).pdf", b"%PDF-1.4 wwr")
    _write_fixture_file(fixture_root / "WWR" / "MSR_April2027.pdf", b"%PDF-1.4 msr")
    _write_fixture_file(fixture_root / "agor" / "ADA581639.pdf", b"%PDF-1.4 agor")
    _write_fixture_file(
        fixture_root / "natalies" / "reports_markdown" / "contract_1_atlantic_environmental.md",
        "# Contract N40080-24-D-1042\n",
    )
    _write_fixture_file(
        fixture_root / "natalies" / "reports_pdf" / "N40080-24-D-1042_WSR-001.pdf",
        b"%PDF-1.4 natalie",
    )
    output_dir = tmp_path / "corpus"

    result = build_synthetic_corpus(fixture_root=fixture_root, output_dir=output_dir)

    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    extraction_rows = [
        json.loads(line)
        for line in (output_dir / "extraction_packet.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result.fixture_groups == 3
    assert result.real_documents == 5
    assert result.synthetic_documents == len(SYNTHETIC_DOCUMENTS)
    assert manifest["source_policy"]["api_policy"] == "No keyed APIs and no SAM.gov web-UI scraping."
    assert any(doc["source_type"] == "real_fixture" and not doc["synthetic"] for doc in extraction_rows)
    assert any(
        doc["source_type"] == "synthetic_fixture"
        and doc["synthetic"]
        and "Not an official government record" in (doc["text"] or "")
        for doc in extraction_rows
    )
    assert len(manifest["cross_contract_patterns"]) >= 3
    assert (output_dir / "synthetic" / "cross_contract" / "shared" / "synthetic_cross_contract_lessons.md").exists()


def _write_fixture_file(path: Path, content: Union[bytes, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
