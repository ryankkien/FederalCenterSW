from __future__ import annotations

import csv
import hashlib
import itertools
import json
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Sequence
from uuid import NAMESPACE_URL, uuid4, uuid5
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contract, KnowledgeIngestionRun, KnowledgeSourceRecord
from app.service_taxonomy import is_service_psc, psc_family


NAVY_SUBTIER_CODE = "1700"
NAVY_SUBTIER_NAME = "DEPT OF THE NAVY"
FEDERAL_REGISTER_DOCUMENT_TAGS = {"RULE", "PRORULE", "NOTICE", "PRESDOCU"}


@dataclass(frozen=True)
class BulkImportResult:
    files_seen: int
    rows_seen: int
    rows_matched: int
    contracts_upserted: int
    source_records_upserted: int
    run_id: str


def import_usaspending_bulk(
    db: Session,
    paths: Sequence[Path],
    limit: Optional[int] = None,
    source_label: str = "usaspending_bulk",
) -> BulkImportResult:
    run = KnowledgeIngestionRun(
        id=str(uuid4()),
        scope="dept_of_navy_service_bulk",
        status="running",
        sources_requested=[source_label],
        limit=limit,
        prompt_version="bulk_import_v1",
        metadata_json={
            "source_policy": "bulk_first_no_keyed_api",
            "target_subtier_code": NAVY_SUBTIER_CODE,
            "target_subtier_name": NAVY_SUBTIER_NAME,
            "target_psc_families": "service",
        },
    )
    db.add(run)
    db.flush()

    files_seen = 0
    rows_seen = 0
    rows_matched = 0
    contract_numbers: List[str] = []
    source_records = 0
    contract_cache: Dict[str, Contract] = {}
    try:
        for file_path, row in _iter_usaspending_rows(paths):
            files_seen += 1 if rows_seen == 0 else 0
            rows_seen += 1
            if not is_navy_service_award(row):
                continue
            rows_matched += 1
            contract = _upsert_contract(db, row, file_path, contract_cache)
            _upsert_source_record(db, run, contract, row, file_path, source_label)
            source_records += 1
            contract_numbers.append(contract.contract_number)
            if rows_matched % 1000 == 0:
                db.flush()
            if limit is not None and rows_matched >= limit:
                break

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.contract_ids = sorted(set(contract_numbers))
        run.metadata_json = {
            **(run.metadata_json or {}),
            "rows_seen": rows_seen,
            "rows_matched": rows_matched,
            "source_records_upserted": source_records,
        }
        db.flush()
        return BulkImportResult(
            files_seen=len(list(_candidate_files(paths))),
            rows_seen=rows_seen,
            rows_matched=rows_matched,
            contracts_upserted=len(set(contract_numbers)),
            source_records_upserted=source_records,
            run_id=run.id,
        )
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise


def import_ecfr_title48_bulk(
    db: Session,
    paths: Sequence[Path],
    limit: Optional[int] = None,
    source_label: str = "ecfr_title48_bulk",
) -> BulkImportResult:
    run = KnowledgeIngestionRun(
        id=str(uuid4()),
        scope="acquisition_regulation_bulk",
        status="running",
        sources_requested=[source_label],
        limit=limit,
        prompt_version="ecfr_title48_bulk_v1",
        metadata_json={
            "source_policy": "bulk_first_no_keyed_api",
            "title": "48",
            "collection": "ECFR",
        },
    )
    db.add(run)
    db.flush()

    rows_seen = 0
    rows_matched = 0
    source_records = 0
    try:
        for source_path, section in _iter_ecfr_sections(paths):
            rows_seen += 1
            if not section["section_number"]:
                continue
            rows_matched += 1
            _upsert_ecfr_source_record(db, run, section, source_path, source_label)
            source_records += 1
            if rows_matched % 500 == 0:
                db.flush()
            if limit is not None and rows_matched >= limit:
                break

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.contract_ids = []
        run.metadata_json = {
            **(run.metadata_json or {}),
            "rows_seen": rows_seen,
            "rows_matched": rows_matched,
            "source_records_upserted": source_records,
        }
        db.flush()
        return BulkImportResult(
            files_seen=len(list(_candidate_xml_files(paths))),
            rows_seen=rows_seen,
            rows_matched=rows_matched,
            contracts_upserted=0,
            source_records_upserted=source_records,
            run_id=run.id,
        )
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise


def import_sam_opportunities_bulk(
    db: Session,
    paths: Sequence[Path],
    limit: Optional[int] = None,
    source_label: str = "sam_opportunities_bulk",
) -> BulkImportResult:
    run = KnowledgeIngestionRun(
        id=str(uuid4()),
        scope="dept_of_navy_service_opportunities_bulk",
        status="running",
        sources_requested=[source_label],
        limit=limit,
        prompt_version="sam_opportunities_bulk_v1",
        metadata_json={
            "source_policy": "bulk_first_no_keyed_api",
            "target_subtier_code": NAVY_SUBTIER_CODE,
            "target_subtier_name": NAVY_SUBTIER_NAME,
            "target_psc_families": "service",
        },
    )
    db.add(run)
    db.flush()

    rows_seen = 0
    rows_matched = 0
    source_records = 0
    try:
        for file_path, row in _iter_delimited_rows(paths):
            rows_seen += 1
            if not is_navy_service_opportunity(row):
                continue
            rows_matched += 1
            _upsert_sam_source_record(db, run, row, file_path, source_label)
            source_records += 1
            if rows_matched % 500 == 0:
                db.flush()
            if limit is not None and rows_matched >= limit:
                break

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.contract_ids = []
        run.metadata_json = {
            **(run.metadata_json or {}),
            "rows_seen": rows_seen,
            "rows_matched": rows_matched,
            "source_records_upserted": source_records,
        }
        db.flush()
        return BulkImportResult(
            files_seen=len(list(_candidate_files(paths))),
            rows_seen=rows_seen,
            rows_matched=rows_matched,
            contracts_upserted=0,
            source_records_upserted=source_records,
            run_id=run.id,
        )
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise


def import_federal_register_bulk(
    db: Session,
    paths: Sequence[Path],
    limit: Optional[int] = None,
    source_label: str = "federal_register_bulk",
) -> BulkImportResult:
    run = KnowledgeIngestionRun(
        id=str(uuid4()),
        scope="acquisition_federal_register_bulk",
        status="running",
        sources_requested=[source_label],
        limit=limit,
        prompt_version="federal_register_bulk_v1",
        metadata_json={
            "source_policy": "bulk_first_no_keyed_api",
            "collection": "FR",
            "filter": "far_dfars_ofpp_navy_acquisition",
        },
    )
    db.add(run)
    db.flush()

    rows_seen = 0
    rows_matched = 0
    source_records = 0
    try:
        for source_ref, document in _iter_federal_register_documents(paths):
            rows_seen += 1
            if not _is_federal_register_acquisition_relevant(document):
                continue
            rows_matched += 1
            _upsert_federal_register_source_record(db, run, document, source_ref, source_label)
            source_records += 1
            if rows_matched % 250 == 0:
                db.flush()
            if limit is not None and rows_matched >= limit:
                break

        run.status = "completed"
        run.completed_at = datetime.now(timezone.utc)
        run.contract_ids = []
        run.metadata_json = {
            **(run.metadata_json or {}),
            "rows_seen": rows_seen,
            "rows_matched": rows_matched,
            "source_records_upserted": source_records,
        }
        db.flush()
        return BulkImportResult(
            files_seen=len(list(_candidate_federal_register_files(paths))),
            rows_seen=rows_seen,
            rows_matched=rows_matched,
            contracts_upserted=0,
            source_records_upserted=source_records,
            run_id=run.id,
        )
    except Exception as error:
        run.status = "failed"
        run.error_message = str(error)[:2000]
        run.completed_at = datetime.now(timezone.utc)
        db.flush()
        raise


def is_navy_service_award(row: Dict[str, str]) -> bool:
    subtier_code = _value(row, "awarding_sub_agency_code", "awarding_subtier_code", "awarding_subtier_agency_code")
    subtier_name = _value(row, "awarding_sub_agency_name", "awarding_subtier_name", "awarding_subtier_agency_name")
    psc_code = _value(row, "product_or_service_code", "psc_code")
    is_navy = subtier_code == NAVY_SUBTIER_CODE or "NAVY" in subtier_name.upper()
    return is_navy and is_service_psc(psc_code)


def is_navy_service_opportunity(row: Dict[str, str]) -> bool:
    fpds_code = _value(row, "fpds_code", "fpdscode")
    subtier_name = _value(row, "sub_tier", "subtier")
    department = _value(row, "department_ind_agency", "department/ind.agency")
    office_name = _value(row, "office")
    psc_code = _value(row, "classification_code", "classificationcode", "psc_code")
    is_navy = (
        fpds_code == NAVY_SUBTIER_CODE
        or "NAVY" in subtier_name.upper()
        or "DEPT OF THE NAVY" in department.upper()
        or "NAVY" in office_name.upper()
    )
    return is_navy and is_service_psc(psc_code)


def _iter_usaspending_rows(paths: Sequence[Path]) -> Iterator[tuple[Path, Dict[str, str]]]:
    yield from _iter_delimited_rows(paths)


def _iter_delimited_rows(paths: Sequence[Path]) -> Iterator[tuple[Path, Dict[str, str]]]:
    for path in _candidate_files(paths):
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if not name.lower().endswith((".csv", ".tsv")):
                        continue
                    with archive.open(name) as handle:
                        yield from _csv_rows(path, (line.decode("utf-8-sig", errors="replace") for line in handle))
            continue
        if path.suffix.lower() in {".csv", ".tsv"}:
            with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                yield from _csv_rows(path, handle)


def _iter_ecfr_sections(paths: Sequence[Path]) -> Iterator[tuple[Path, Dict[str, object]]]:
    for path in _candidate_xml_files(paths):
        tree = ElementTree.parse(path)
        root = tree.getroot()
        parent_by_child = {child: parent for parent in root.iter() for child in parent}
        amendment_date = _text_of(root.find(".//AMDDATE"))
        for element in root.iter():
            if element.get("TYPE") != "SECTION":
                continue
            section_number = (element.get("N") or "").strip()
            heading = _first_child_text(element, "HEAD")
            text = _normalized_text(element)
            if not section_number and heading:
                section_number = heading.split(" ", 1)[0].strip()
            yield (
                path,
                {
                    "title": "48",
                    "section_number": section_number,
                    "node": (element.get("NODE") or "").strip(),
                    "heading": heading,
                    "chapter": _ancestor_heading(element, parent_by_child, "CHAPTER"),
                    "subchapter": _ancestor_heading(element, parent_by_child, "SUBCHAP"),
                    "part": _ancestor_heading(element, parent_by_child, "PART"),
                    "subpart": _ancestor_heading(element, parent_by_child, "SUBPART"),
                    "amendment_date": amendment_date,
                    "text": text,
                },
            )


def _iter_federal_register_documents(paths: Sequence[Path]) -> Iterator[tuple[str, Dict[str, object]]]:
    for path in _candidate_federal_register_files(paths):
        if path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if name.lower().endswith(".xml"):
                        source_ref = f"{path}::{name}"
                        yield from _federal_register_documents_from_xml(source_ref, archive.read(name))
            continue
        if path.suffix.lower() == ".xml":
            yield from _federal_register_documents_from_xml(str(path), path.read_bytes())


def _federal_register_documents_from_xml(source_ref: str, content: bytes) -> Iterator[tuple[str, Dict[str, object]]]:
    root = ElementTree.fromstring(content)
    package_id = Path(source_ref.split("::")[-1]).stem
    publication_date = _federal_register_publication_date(package_id, _first_child_text(root, "DATE"))
    for element in root.iter():
        if element.tag not in FEDERAL_REGISTER_DOCUMENT_TAGS:
            continue
        text = _normalized_text(element)
        fr_document_number = _federal_register_document_number(_first_descendant_text(element, "FRDOC"))
        yield (
            source_ref,
            {
                "package_id": package_id,
                "publication_date": publication_date.isoformat() if publication_date else None,
                "document_type": element.tag,
                "agency": _first_descendant_text(element, "AGENCY"),
                "subagency": _first_descendant_text(element, "SUBAGY"),
                "cfr": _first_descendant_text(element, "CFR"),
                "docket": _first_descendant_text(element, "DEPDOC"),
                "rin": _first_descendant_text(element, "RIN"),
                "subject": _first_descendant_text(element, "SUBJECT") or _first_descendant_text(element, "TITLE"),
                "action": _first_descendant_text(element, "ACT"),
                "summary": _first_descendant_text(element, "SUM"),
                "dates": _first_descendant_text(element, "DATES"),
                "fr_document": _first_descendant_text(element, "FRDOC"),
                "fr_document_number": fr_document_number,
                "billing_code": _first_descendant_text(element, "BILCOD"),
                "relevance_terms": _federal_register_relevance_terms(element),
                "text": text,
            },
        )


def _upsert_ecfr_source_record(
    db: Session,
    run: KnowledgeIngestionRun,
    section: Dict[str, object],
    source_path: Path,
    source_label: str,
) -> KnowledgeSourceRecord:
    source_identifier = str(section.get("node") or section["section_number"])
    source_key = f"{source_label}:48:{source_identifier}"[:500]
    record = db.scalars(
        select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.source_name == source_label,
            KnowledgeSourceRecord.source_key == source_key,
        )
    ).first()
    if record is None:
        record = KnowledgeSourceRecord(id=str(uuid4()), source_name=source_label, source_key=source_key)
        db.add(record)
    text = str(section.get("text") or "")
    record.ingestion_run_id = run.id
    record.source_type = "official_bulk"
    record.status = "available"
    record.unavailable_reason = None
    record.url = _ecfr_section_url(str(section["section_number"]))
    record.title = str(section.get("heading") or f"48 CFR {section['section_number']}")[:500]
    record.text = text
    record.raw_json = {key: value for key, value in section.items() if key != "text"}
    record.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record.source_timestamp = _ecfr_amendment_datetime(str(section.get("amendment_date") or ""))
    record.contract_id = None
    record.vendor_uei = None
    record.metadata_json = {
        "record_type": "ecfr_title48_section",
        "source_file": str(source_path),
        "title": "48",
        "section_number": section["section_number"],
        "chapter": section.get("chapter"),
        "part": section.get("part"),
        "subpart": section.get("subpart"),
    }
    return record


def _upsert_federal_register_source_record(
    db: Session,
    run: KnowledgeIngestionRun,
    document: Dict[str, object],
    source_ref: str,
    source_label: str,
) -> KnowledgeSourceRecord:
    source_identifier = str(document.get("fr_document_number") or document["package_id"])
    source_key = f"{source_label}:{document['package_id']}:{source_identifier}"[:500]
    record = db.scalars(
        select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.source_name == source_label,
            KnowledgeSourceRecord.source_key == source_key,
        )
    ).first()
    if record is None:
        record = KnowledgeSourceRecord(id=str(uuid4()), source_name=source_label, source_key=source_key)
        db.add(record)
    text = str(document.get("text") or "")
    record.ingestion_run_id = run.id
    record.source_type = "official_bulk"
    record.status = "available"
    record.unavailable_reason = None
    record.url = _federal_register_url(str(document["package_id"]), str(document.get("fr_document_number") or ""))
    record.title = str(document.get("subject") or f"Federal Register {document['package_id']}")[:500]
    record.text = text
    record.raw_json = {key: value for key, value in document.items() if key != "text"}
    record.content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    record.source_timestamp = _parse_datetime(str(document.get("publication_date") or ""))
    record.contract_id = None
    record.vendor_uei = None
    record.metadata_json = {
        "record_type": "federal_register_document",
        "source_file": source_ref,
        "package_id": document["package_id"],
        "document_type": document["document_type"],
        "agency": document.get("agency"),
        "subagency": document.get("subagency"),
        "relevance_terms": document.get("relevance_terms"),
    }
    return record


def _candidate_files(paths: Sequence[Path]) -> Iterator[Path]:
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_dir():
            yield from sorted(
                item for item in path.rglob("*") if item.suffix.lower() in {".csv", ".tsv", ".zip"}
            )
        elif path.exists() and path.suffix.lower() in {".csv", ".tsv", ".zip"}:
            yield path


def _candidate_xml_files(paths: Sequence[Path]) -> Iterator[Path]:
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_dir():
            yield from sorted(item for item in path.rglob("*.xml") if item.is_file())
        elif path.exists() and path.suffix.lower() == ".xml":
            yield path


def _candidate_federal_register_files(paths: Sequence[Path]) -> Iterator[Path]:
    for raw_path in paths:
        path = raw_path.expanduser()
        if path.is_dir():
            yield from sorted(item for item in path.rglob("*") if item.suffix.lower() in {".xml", ".zip"})
        elif path.exists() and path.suffix.lower() in {".xml", ".zip"}:
            yield path


def _csv_rows(path: Path, lines: Iterable[str]) -> Iterator[tuple[Path, Dict[str, str]]]:
    sample = []
    iterator = iter(lines)
    for _ in range(8):
        try:
            sample.append(next(iterator))
        except StopIteration:
            break
    dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    if sample:
        try:
            dialect = csv.Sniffer().sniff("\n".join(sample))
        except csv.Error:
            pass
    reader = csv.DictReader(itertools.chain(sample, iterator), dialect=dialect)
    for row in reader:
        yield path, {_normalize_key(key): (value or "").strip() for key, value in row.items() if key}


def _upsert_contract(
    db: Session,
    row: Dict[str, str],
    source_path: Path,
    contract_cache: Dict[str, Contract],
) -> Contract:
    contract_number = _contract_number(row)
    contract = contract_cache.get(contract_number)
    if contract is None:
        contract = db.scalars(select(Contract).where(Contract.contract_number == contract_number)).first()
    if contract is None:
        contract = Contract(id=str(uuid5(NAMESPACE_URL, f"usaspending:{contract_number}")), contract_number=contract_number)
        db.add(contract)
    contract_cache[contract_number] = contract
    labels = _labels(row)
    contract.title = _title(row, labels)
    contract.description = _value(row, "award_description", "description") or contract.description
    contract.agency_name = _value(row, "awarding_sub_agency_name", "awarding_subtier_name") or NAVY_SUBTIER_NAME
    contract.office_name = _value(row, "awarding_office_name", "funding_office_name") or contract.office_name
    contract.vendor_name = _value(row, "recipient_name", "awardee_or_recipient_legal", "awardee_name")
    contract.vendor_uei = _value(row, "recipient_uei", "recipient_unique_entity_id", "awardee_uei") or contract.vendor_uei
    contract.naics_code = _value(row, "naics_code", "principal_naics_code") or contract.naics_code
    contract.psc_code = _value(row, "product_or_service_code", "psc_code") or contract.psc_code
    contract.period_start = _date_value(row, "period_of_performance_start_date", "action_date")
    contract.period_end = _date_value(
        row,
        "period_of_performance_current_end_date",
        "period_of_performance_potential_end_date",
        "ordering_period_end_date",
    )
    contract.status = "active"
    contract.security_level = "standard"
    contract.metadata_json = {
        **(contract.metadata_json or {}),
        "source": "usaspending_bulk",
        "source_file": str(source_path),
        "navy_service_labels": labels,
        "award_key": _award_key(row),
        "raw_usaspending_row": row,
    }
    return contract


def _upsert_source_record(
    db: Session,
    run: KnowledgeIngestionRun,
    contract: Contract,
    row: Dict[str, str],
    source_path: Path,
    source_label: str,
) -> KnowledgeSourceRecord:
    source_key = f"{source_label}:{_award_key(row)}"[:500]
    record = db.scalars(
        select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.source_name == source_label,
            KnowledgeSourceRecord.source_key == source_key,
        )
    ).first()
    if record is None:
        record = KnowledgeSourceRecord(id=str(uuid4()), source_name=source_label, source_key=source_key)
        db.add(record)
    text = _source_text(contract, row)
    record.ingestion_run_id = run.id
    record.source_type = "official_bulk"
    record.status = "available"
    record.unavailable_reason = None
    record.url = _usaspending_award_url(row)
    record.title = f"USAspending bulk award {contract.contract_number}"[:500]
    record.text = text
    record.raw_json = row
    record.content_hash = hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
    record.source_timestamp = _datetime_value(row, "action_date", "last_modified_date")
    record.contract_id = contract.id
    record.vendor_uei = contract.vendor_uei
    record.metadata_json = {
        "record_type": "usaspending_contract_award",
        "source_file": str(source_path),
        "navy_service_labels": _labels(row),
    }
    return record


def _upsert_sam_source_record(
    db: Session,
    run: KnowledgeIngestionRun,
    row: Dict[str, str],
    source_path: Path,
    source_label: str,
) -> KnowledgeSourceRecord:
    source_key = f"{source_label}:{_sam_opportunity_key(row)}"[:500]
    record = db.scalars(
        select(KnowledgeSourceRecord).where(
            KnowledgeSourceRecord.source_name == source_label,
            KnowledgeSourceRecord.source_key == source_key,
        )
    ).first()
    if record is None:
        record = KnowledgeSourceRecord(id=str(uuid4()), source_name=source_label, source_key=source_key)
        db.add(record)
    text = _sam_source_text(row)
    record.ingestion_run_id = run.id
    record.source_type = "official_bulk"
    record.status = "available"
    record.unavailable_reason = None
    record.url = _value(row, "link")
    record.title = (_value(row, "title") or f"SAM.gov opportunity {_sam_opportunity_key(row)}")[:500]
    record.text = text
    record.raw_json = row
    record.content_hash = hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
    record.source_timestamp = _datetime_value(row, "posteddate", "posted_date")
    record.contract_id = None
    record.vendor_uei = None
    record.metadata_json = {
        "record_type": "sam_contract_opportunity",
        "source_file": str(source_path),
        "navy_service_labels": _sam_labels(row),
    }
    return record


def _labels(row: Dict[str, str]) -> Dict[str, object]:
    family = psc_family(_value(row, "product_or_service_code", "psc_code"))
    return {
        "department": NAVY_SUBTIER_NAME,
        "subtier_code": NAVY_SUBTIER_CODE,
        "psc_code": _value(row, "product_or_service_code", "psc_code"),
        "psc_family_code": family.code if family else None,
        "psc_family": family.label if family else None,
        "naics_code": _value(row, "naics_code", "principal_naics_code"),
        "naics_description": _value(row, "naics_description", "principal_naics_description"),
        "contracting_office": _value(row, "awarding_office_name"),
        "funding_office": _value(row, "funding_office_name"),
        "award_type": _value(row, "award_type", "award_type_code"),
        "competition": _value(row, "extent_competed", "extent_competed_description"),
        "set_aside": _value(row, "type_set_aside", "type_of_set_aside", "type_of_set_aside_description"),
        "place_of_performance": _place_of_performance(row),
        "total_obligated_amount": _value(row, "total_obligated_amount", "federal_action_obligation"),
        "potential_total_value": _value(row, "potential_total_value_of_award", "base_and_all_options_value"),
    }


def _sam_labels(row: Dict[str, str]) -> Dict[str, object]:
    psc_code = _value(row, "classification_code", "classificationcode", "psc_code")
    family = psc_family(psc_code)
    return {
        "department": _value(row, "department_ind_agency", "department/ind.agency"),
        "subtier": _value(row, "sub_tier", "subtier"),
        "fpds_code": _value(row, "fpds_code", "fpdscode"),
        "office": _value(row, "office"),
        "aac_code": _value(row, "aac_code", "aaccode"),
        "psc_code": psc_code,
        "psc_family_code": family.code if family else None,
        "psc_family": family.label if family else None,
        "naics_code": _value(row, "naics_code", "naicscode"),
        "notice_type": _value(row, "type"),
        "base_type": _value(row, "basetype", "base_type"),
        "archive_type": _value(row, "archivetype", "archive_type"),
        "set_aside": _value(row, "setaside", "set_aside"),
        "set_aside_code": _value(row, "setasidecode", "set_aside_code"),
        "active": _value(row, "active"),
        "posted_date": _value(row, "posteddate", "posted_date"),
        "response_deadline": _value(row, "responsedeadline", "response_deadline"),
        "place_of_performance": _sam_place_of_performance(row),
        "award_number": _value(row, "awardnumber", "award_number"),
        "award_date": _value(row, "awarddate", "award_date"),
        "award_amount": _value(row, "award", "award_amount"),
        "awardee": _value(row, "awardee"),
    }


def _source_text(contract: Contract, row: Dict[str, str]) -> str:
    labels = _labels(row)
    return (
        f"{contract.contract_number}: {contract.title}. Contractor: {contract.vendor_name or 'unknown'}. "
        f"Department: {labels['department']}. PSC: {labels['psc_code']} ({labels['psc_family']}). "
        f"NAICS: {labels['naics_code']} {labels['naics_description']}. "
        f"Office: {labels['contracting_office'] or labels['funding_office']}. "
        f"Obligated: {labels['total_obligated_amount']}. Competition: {labels['competition']}. "
        f"Set-aside: {labels['set_aside']}. Description: {contract.description or ''}"
    )


def _sam_source_text(row: Dict[str, str]) -> str:
    labels = _sam_labels(row)
    return (
        f"{_value(row, 'noticeid', 'notice_id')}: {_value(row, 'title')}. "
        f"Solicitation: {_value(row, 'sol')}. "
        f"Department: {labels['department']} / {labels['subtier']}. "
        f"Office: {labels['office']}. Type: {labels['notice_type']}. "
        f"PSC: {labels['psc_code']} ({labels['psc_family']}). "
        f"NAICS: {labels['naics_code']}. Set-aside: {labels['set_aside']}. "
        f"Posted: {labels['posted_date']}. Response deadline: {labels['response_deadline']}. "
        f"Place of performance: {labels['place_of_performance']}. "
        f"Award: {labels['award_number']} {labels['award_amount']} {labels['awardee']}. "
        f"Description: {_value(row, 'description')}"
    )


def _title(row: Dict[str, str], labels: Dict[str, object]) -> str:
    description = _value(row, "award_description", "description")
    if description:
        return description[:300]
    family = str(labels.get("psc_family") or "Service")
    vendor = _value(row, "recipient_name", "awardee_name") or "Unknown contractor"
    return f"{family} award to {vendor}"[:300]


def _contract_number(row: Dict[str, str]) -> str:
    return (
        _value(row, "award_id_piid", "piid", "contract_award_id")
        or _value(row, "generated_unique_award_id", "contract_award_unique_key")
        or _award_key(row)
    )[:120]


def _award_key(row: Dict[str, str]) -> str:
    return (
        _value(row, "contract_transaction_unique_key")
        or _value(row, "contract_award_unique_key", "generated_unique_award_id", "award_id")
        or f"{_value(row, 'award_id_piid', 'piid')}:{_value(row, 'modification_number')}"
        or hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
    )


def _sam_opportunity_key(row: Dict[str, str]) -> str:
    return (
        _value(row, "noticeid", "notice_id")
        or _value(row, "sol")
        or _value(row, "link")
        or hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()
    )


def _value(row: Dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(_normalize_key(key), "")
        if value:
            return value
    return ""


def _normalize_key(value: object) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", str(value or "").strip().lower()).strip("_")


def _date_value(row: Dict[str, str], *keys: str) -> Optional[date]:
    parsed = _datetime_value(row, *keys)
    return parsed.date() if parsed else None


def _datetime_value(row: Dict[str, str], *keys: str) -> Optional[datetime]:
    value = _value(row, *keys)
    if not value:
        return None
    parsed = _parse_datetime(value)
    if parsed:
        return parsed
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value[:26], fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _parse_datetime(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("Z", "+00:00")
    if re.search(r"[+-]\d{2}$", cleaned):
        cleaned = f"{cleaned}:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _place_of_performance(row: Dict[str, str]) -> str:
    return ", ".join(
        value
        for value in (
            _value(row, "primary_place_of_performance_city_name"),
            _value(row, "primary_place_of_performance_state_name", "primary_place_of_performance_country_name"),
        )
        if value
    )


def _sam_place_of_performance(row: Dict[str, str]) -> str:
    return ", ".join(
        value
        for value in (
            _value(row, "popcity", "pop_city"),
            _value(row, "popstate", "pop_state"),
            _value(row, "popcountry", "pop_country"),
        )
        if value
    )


def _is_federal_register_acquisition_relevant(document: Dict[str, object]) -> bool:
    agency = str(document.get("agency") or "").upper()
    subagency = str(document.get("subagency") or "").upper()
    subject = str(document.get("subject") or "").upper()
    cfr = str(document.get("cfr") or "").upper()
    text = str(document.get("text") or "").upper()
    if "COMMITTEE FOR PURCHASE FROM PEOPLE WHO ARE BLIND OR SEVERELY DISABLED" in agency:
        return False
    if "DEFENSE ACQUISITION REGULATIONS SYSTEM" in subagency:
        return True
    if "DFARS" in subject or "DEFENSE FEDERAL ACQUISITION REGULATION SUPPLEMENT" in subject:
        return True
    if "OFFICE OF FEDERAL PROCUREMENT POLICY" in subagency:
        return True
    if "FEDERAL ACQUISITION REGULATION" in subject:
        return True
    acquisition_subject = any(
        term in subject
        for term in ("ACQUISITION", "PROCUREMENT", "CONTRACT", "CONTRACTOR", "SOLICITATION")
    )
    acquisition_agency = any(
        term in agency
        for term in (
            "DEPARTMENT OF DEFENSE",
            "GENERAL SERVICES ADMINISTRATION",
            "NATIONAL AERONAUTICS AND SPACE ADMINISTRATION",
            "OFFICE OF MANAGEMENT AND BUDGET",
        )
    )
    if "48 CFR" in cfr and acquisition_agency and acquisition_subject:
        return True
    if "DEPARTMENT OF THE NAVY" in text and acquisition_subject:
        return True
    return False


def _federal_register_relevance_terms(element) -> List[str]:
    text = _normalized_text(element).upper()
    checks = (
        "DEFENSE ACQUISITION REGULATIONS SYSTEM",
        "DFARS",
        "DEFENSE FEDERAL ACQUISITION REGULATION SUPPLEMENT",
        "FEDERAL ACQUISITION REGULATION",
        "OFFICE OF FEDERAL PROCUREMENT POLICY",
        "48 CFR",
        "DEPARTMENT OF THE NAVY",
        "SERVICE CONTRACTING",
        "PROCUREMENT",
        "CONTRACTOR",
    )
    return [term for term in checks if term in text]


def _usaspending_award_url(row: Dict[str, str]) -> Optional[str]:
    key = _value(row, "generated_unique_award_id", "contract_award_unique_key")
    if not key:
        return None
    return f"https://www.usaspending.gov/award/{key}"


def _ecfr_section_url(section_number: str) -> str:
    return f"https://www.ecfr.gov/current/title-48/section-{section_number}"


def _federal_register_url(package_id: str, fr_document_number: str) -> str:
    if fr_document_number:
        return f"https://www.govinfo.gov/app/details/{package_id}/{fr_document_number}"
    return f"https://www.govinfo.gov/app/details/{package_id}"


def _federal_register_document_number(value: str) -> str:
    match = re.search(r"FR Doc\.\s*([^\s\]]+)", value)
    return match.group(1) if match else ""


def _federal_register_publication_date(package_id: str, display_date: str) -> Optional[date]:
    match = re.search(r"FR-(\d{4}-\d{2}-\d{2})", package_id)
    if match:
        parsed = _parse_datetime(match.group(1))
        return parsed.date() if parsed else None
    for fmt in ("%A, %B %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(display_date.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _ancestor_heading(element, parent_by_child: Dict[object, object], type_name: str) -> str:
    parent = parent_by_child.get(element)
    while parent is not None:
        if parent.get("TYPE") == type_name:
            return _first_child_text(parent, "HEAD")
        parent = parent_by_child.get(parent)
    return ""


def _first_child_text(element, tag: str) -> str:
    for child in list(element):
        if child.tag == tag:
            return _text_of(child)
    return ""


def _first_descendant_text(element, tag: str) -> str:
    child = element.find(f".//{tag}")
    return _text_of(child) if child is not None else ""


def _text_of(element) -> str:
    if element is None:
        return ""
    return " ".join(text.strip() for text in element.itertext() if text and text.strip())


def _normalized_text(element) -> str:
    return " ".join(text.strip() for text in element.itertext() if text and text.strip())


def _ecfr_amendment_datetime(value: str) -> Optional[datetime]:
    cleaned = " ".join(value.replace("\n", " ").split())
    if not cleaned:
        return None
    month_aliases = {"Sept.": "Sep."}
    parts = cleaned.split(" ", 1)
    if parts and parts[0] in month_aliases:
        cleaned = f"{month_aliases[parts[0]]} {parts[1]}"
    for fmt in ("%b. %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
