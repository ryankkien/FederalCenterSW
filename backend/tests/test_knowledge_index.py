from datetime import datetime, timezone
from typing import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, get_db
from app.knowledge_bulk import (
    import_ecfr_title48_bulk,
    import_federal_register_bulk,
    import_sam_opportunities_bulk,
    import_usaspending_bulk,
)
from app.main import app
from app.models import (
    Contract,
    ContractAccessGrant,
    DocumentUpload,
    KnowledgeCitation,
    KnowledgeNode,
    KnowledgeSourceRecord,
    RegressionFinding,
)


def test_knowledge_ingestion_builds_cited_contract_and_contractor_wiki(tmp_path, monkeypatch) -> None:
    client = _client_with_test_db(tmp_path)
    official_token = _token(client, "official")
    contractor_token = _token(client, "contractor")
    monkeypatch.delenv("SAM_API_KEY", raising=False)
    monkeypatch.delenv("CPARS_IMPORT_DIR", raising=False)

    with next(_test_db_session(tmp_path)) as db:
        db.add(
            Contract(
                id="atlantic",
                contract_number="N40080-24-D-1042",
                title="Environmental Compliance and Permitting Support Services",
                vendor_name="Atlantic Environmental",
                vendor_uei="UEIATLANTIC1",
                agency_name="Department of the Navy",
                office_name="NAVFAC Washington",
            )
        )
        db.add(
            ContractAccessGrant(
                id="grant-atlantic",
                contract_id="atlantic",
                principal_id="official-demo",
                role="viewer",
            )
        )
        db.add(_document("doc-1", "atlantic"))
        db.add(
            RegressionFinding(
                id="reg-1",
                contract_id="atlantic",
                document_upload_id="doc-1",
                finding_type="schedule_regression",
                title="Aging RFI",
                summary="RFI is 21 days open.",
                severity="medium",
                status="open",
                quote="RFI is 21 days open.",
            )
        )
        db.commit()

    run = client.post(
        "/api/knowledge/ingestion-runs",
        headers={"Authorization": f"Bearer {official_token}"},
        json={"scope": "visible", "sources": ["sam", "cpars"], "limit": 10},
    )
    search = client.get("/api/wiki/search", headers={"Authorization": f"Bearer {official_token}"})
    contract_article = client.get(
        "/api/wiki/contracts/atlantic",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    contractor_article = client.get(
        "/api/wiki/contractors/UEIATLANTIC1",
        headers={"Authorization": f"Bearer {official_token}"},
    )
    contractor_blocked = client.get(
        "/api/wiki/contracts/atlantic",
        headers={"Authorization": f"Bearer {contractor_token}"},
    )

    with next(_test_db_session(tmp_path)) as db:
        doc = db.get(DocumentUpload, "doc-1")
        source_records = db.scalars(select(KnowledgeSourceRecord)).all()
        nodes = db.scalars(select(KnowledgeNode)).all()
        citations = db.scalars(select(KnowledgeCitation)).all()

    assert run.status_code == 202
    assert run.json()["status"] == "completed"
    assert run.json()["node_count"] >= 2
    assert search.status_code == 200
    assert {"contract", "contractor"}.issubset({item["node_type"] for item in search.json()})
    assert contract_article.status_code == 200
    assert "Performance Evidence Labels" in {section["title"] for section in contract_article.json()["sections"]}
    assert contract_article.json()["citations"]
    assert contractor_article.status_code == 200
    assert "moral judgments" in " ".join(contractor_article.json()["limitations"])
    assert contractor_blocked.status_code == 404
    assert doc is not None
    assert doc.contract_id == "atlantic"
    assert {record.status for record in source_records} == {"unavailable"}
    assert len(nodes) >= 2
    assert len(citations) >= 1


def test_usaspending_bulk_import_filters_navy_service_awards(tmp_path) -> None:
    csv_path = tmp_path / "usaspending.csv"
    csv_path.write_text(
        "\n".join(
            [
                "contract_award_unique_key,award_id_piid,awarding_sub_agency_code,awarding_sub_agency_name,awarding_office_name,recipient_name,recipient_uei,product_or_service_code,product_or_service_code_description,naics_code,naics_description,award_description,total_obligated_amount,period_of_performance_start_date,period_of_performance_current_end_date,extent_competed_description,type_of_set_aside_description",
                "award-1,N40080-26-C-0001,1700,DEPT OF THE NAVY,NAVFAC WASHINGTON,ATLANTIC ENVIRONMENTAL,UEIATLANTIC1,R499,OTHER PROFESSIONAL SERVICES,541620,ENVIRONMENTAL CONSULTING,Navy environmental support,125000,2026-01-01,2026-12-31,FULL AND OPEN COMPETITION,NO SET ASIDE USED",
                "award-2,W912DY-26-C-0002,2100,DEPT OF THE ARMY,USACE,ARMY VENDOR,UEIARMY,J099,MAINTENANCE,811310,REPAIR,Army maintenance,1000,2026-01-01,2026-12-31,FULL AND OPEN COMPETITION,NO SET ASIDE USED",
                "award-3,N40080-26-C-0003,1700,DEPT OF THE NAVY,NAVFAC WASHINGTON,NAVY SUPPLIES,UEISUPPLY,5965,HEADSETS,334310,AUDIO SUPPLIES,Navy supply buy,500,2026-01-01,2026-12-31,FULL AND OPEN COMPETITION,NO SET ASIDE USED",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with next(_test_db_session(tmp_path)) as db:
        result = import_usaspending_bulk(db, [csv_path])
        db.commit()
        contracts = list(db.scalars(select(Contract)).all())
        sources = list(db.scalars(select(KnowledgeSourceRecord)).all())

    assert result.rows_seen == 3
    assert result.rows_matched == 1
    assert [contract.contract_number for contract in contracts] == ["N40080-26-C-0001"]
    assert contracts[0].metadata_json["navy_service_labels"]["psc_family_code"] == "R"
    assert contracts[0].metadata_json["navy_service_labels"]["department"] == "DEPT OF THE NAVY"
    assert len(sources) == 1
    assert sources[0].source_type == "official_bulk"


def test_ecfr_title48_bulk_imports_sections(tmp_path) -> None:
    xml_path = tmp_path / "ECFR-title48.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" ?>
<DLPSTEXTCLASS>
  <TEXT>
    <BODY>
      <ECFRBRWS>
        <AMDDATE>Mar. 13, 2026</AMDDATE>
        <DIV3 N="1" NODE="48:1.0.1" TYPE="CHAPTER">
          <HEAD>CHAPTER 1--FEDERAL ACQUISITION REGULATION</HEAD>
          <DIV5 N="37" NODE="48:1.0.1.20.37" TYPE="PART">
            <HEAD>PART 37--SERVICE CONTRACTING</HEAD>
            <DIV8 N="37.102" NODE="48:1.0.1.20.37.1.1.2" TYPE="SECTION">
              <HEAD>37.102 Policy.</HEAD>
              <P>Performance-based acquisition is the preferred method for acquiring services.</P>
            </DIV8>
          </DIV5>
        </DIV3>
      </ECFRBRWS>
    </BODY>
  </TEXT>
</DLPSTEXTCLASS>
""",
        encoding="utf-8",
    )

    with next(_test_db_session(tmp_path)) as db:
        result = import_ecfr_title48_bulk(db, [xml_path])
        db.commit()
        sources = list(db.scalars(select(KnowledgeSourceRecord)).all())

    assert result.rows_seen == 1
    assert result.rows_matched == 1
    assert len(sources) == 1
    assert sources[0].source_name == "ecfr_title48_bulk"
    assert sources[0].source_type == "official_bulk"
    assert sources[0].title == "37.102 Policy."
    assert sources[0].url == "https://www.ecfr.gov/current/title-48/section-37.102"
    assert sources[0].metadata_json["part"] == "PART 37--SERVICE CONTRACTING"


def test_sam_opportunities_bulk_import_filters_navy_service_notices(tmp_path) -> None:
    csv_path = tmp_path / "sam-opportunities.csv"
    csv_path.write_text(
        "\n".join(
            [
                "NoticeId,Title,Sol#,Department/Ind.Agency,CGAC,Sub-Tier,FPDS Code,Office,AAC Code,PostedDate,Type,BaseType,ArchiveType,SetAsideCode,SetAside,ResponseDeadLine,NaicsCode,ClassificationCode,PopCity,PopState,PopCountry,Active,AwardNumber,AwardDate,Award$,Awardee,Link,Description",
                "notice-1,Ship repair support,N00024-26-R-0001,DEPT OF DEFENSE,017,DEPT OF THE NAVY,1700,NAVSEA HQ,N00024,2026-04-25 22:22:47.454-04,Solicitation,Solicitation,auto15,NONE,No Set aside used,2026-05-29T12:30:00-04:00,336611,J998,Norfolk,VA,USA,Yes,,,,,https://sam.gov/opp/notice-1/view,Navy ship repair services",
                "notice-2,Army maintenance,W912DY-26-R-0002,DEPT OF DEFENSE,021,DEPT OF THE ARMY,2100,USACE,W912DY,2026-04-25,Solicitation,Solicitation,auto15,NONE,No Set aside used,2026-05-29,811310,J099,Huntsville,AL,USA,Yes,,,,,https://sam.gov/opp/notice-2/view,Army services",
                "notice-3,Navy headset buy,N00024-26-Q-0003,DEPT OF DEFENSE,017,DEPT OF THE NAVY,1700,NAVSEA HQ,N00024,2026-04-25,Solicitation,Solicitation,auto15,NONE,No Set aside used,2026-05-29,334310,5965,Washington,DC,USA,Yes,,,,,https://sam.gov/opp/notice-3/view,Navy supply buy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with next(_test_db_session(tmp_path)) as db:
        result = import_sam_opportunities_bulk(db, [csv_path])
        db.commit()
        contracts = list(db.scalars(select(Contract)).all())
        sources = list(db.scalars(select(KnowledgeSourceRecord)).all())

    assert result.rows_seen == 3
    assert result.rows_matched == 1
    assert contracts == []
    assert len(sources) == 1
    assert sources[0].source_name == "sam_opportunities_bulk"
    assert sources[0].source_type == "official_bulk"
    assert sources[0].title == "Ship repair support"
    assert sources[0].url == "https://sam.gov/opp/notice-1/view"
    assert sources[0].metadata_json["navy_service_labels"]["psc_family_code"] == "J"
    assert sources[0].metadata_json["navy_service_labels"]["subtier"] == "DEPT OF THE NAVY"


def test_federal_register_bulk_import_filters_acquisition_documents(tmp_path) -> None:
    xml_path = tmp_path / "FR-2026-01-05.xml"
    xml_path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<FEDREG>
  <DATE>Monday, January 5, 2026</DATE>
  <NOTICES>
    <NOTICE>
      <PREAMB>
        <AGENCY TYPE="S">DEPARTMENT OF DEFENSE</AGENCY>
        <SUBAGY>Defense Acquisition Regulations System</SUBAGY>
        <SUBJECT>Information Collection Requirement; Defense Federal Acquisition Regulation Supplement (DFARS) Part 237, Service Contracting, and Related Clauses</SUBJECT>
        <SUM>Defense contractors use these service contracting clauses.</SUM>
        <FRDOC>[FR Doc. 2026-00001 Filed 1-2-26; 8:45 am]</FRDOC>
      </PREAMB>
    </NOTICE>
    <NOTICE>
      <PREAMB>
        <AGENCY TYPE="S">ENVIRONMENTAL PROTECTION AGENCY</AGENCY>
        <SUBJECT>Agency Information Collection Activities</SUBJECT>
        <SUM>Unrelated notice.</SUM>
        <FRDOC>[FR Doc. 2026-00002 Filed 1-2-26; 8:45 am]</FRDOC>
      </PREAMB>
    </NOTICE>
  </NOTICES>
</FEDREG>
""",
        encoding="utf-8",
    )

    with next(_test_db_session(tmp_path)) as db:
        result = import_federal_register_bulk(db, [xml_path])
        db.commit()
        sources = list(db.scalars(select(KnowledgeSourceRecord)).all())

    assert result.rows_seen == 2
    assert result.rows_matched == 1
    assert len(sources) == 1
    assert sources[0].source_name == "federal_register_bulk"
    assert sources[0].title.startswith("Information Collection Requirement")
    assert sources[0].url == "https://www.govinfo.gov/app/details/FR-2026-01-05/2026-00001"
    assert sources[0].metadata_json["relevance_terms"]


def _client_with_test_db(tmp_path) -> TestClient:
    app.dependency_overrides.clear()

    def override_get_db() -> Generator[Session, None, None]:
        yield from _test_db_session(tmp_path)

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _test_db_session(tmp_path) -> Generator[Session, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'knowledge-index.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _token(client: TestClient, role: str) -> str:
    response = client.post("/api/auth/mock-login", json={"role": role})
    assert response.status_code == 200
    return response.json()["access_token"]


def _document(id: str, contract_id: str) -> DocumentUpload:
    return DocumentUpload(
        id=id,
        contract_id=contract_id,
        title="Weekly Status Report",
        document_type="Weekly Status Report",
        document_kind="weekly_report",
        intake_source="portal",
        notes="RFI is 21 days open.",
        original_filename="N40080-24-D-1042_WSR-002.pdf",
        content_type="application/pdf",
        size_bytes=5,
        blob_path=f"contracts/{id}/main.pdf",
        text_blob_path=f"contracts/{id}/text.json",
        match_status="matched",
        processing_status="completed",
        uploader_id="other-contractor",
        uploader_role="contractor",
        created_at=datetime.now(timezone.utc),
    )
