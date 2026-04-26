# Test Documents

The files under `testdocs/` are product fixtures for the contract performance
visibility system described in `docs/product.md`. They can be uploaded through the
portal, attached through email intake, or seeded directly through the fixture CLI.
Seeded and uploaded files become `DocumentUpload` rows and blob assets under:

```text
contracts/{document_id}/main.pdf
contracts/{document_id}/text.json
```

The fixture CLI seeds stable contract records, report buckets, extracted page text,
processing jobs, and downstream analysis rows for local development.

## Product Fit

The 2026 SCSP Hackathon source note frames the product as a secure knowledge system
that turns recurring contractor reports and official evaluation data into persistent
contract knowledge records. The test documents fit that flow:

1. Ingest recurring reports at the contract or program level.
2. Extract text and entities from PDFs, and validate structured JSON reports when
   available.
3. Match reports to a contract record.
4. Use LLM-assisted review to identify risks, delays, staffing issues, deliverables,
   cost/timeline signals, decisions, outcomes, lessons learned, and successes.
5. Aggregate lessons across contracts within role, organization, and security
   boundaries.

Treat `docs/product.md` as the canonical product direction. Treat the hackathon PDF
as background context for why these fixtures exist.

## Fixture Sets

### `testdocs/WWR/`

Primary demo set for the first deliverable: a contract-level UI that shows one
contract record, its ingested reports, processing outputs, and extracted signals.

- Contract: `M0026426R0001`.
- Program: Sergeant Merlin German Wounded Warrior Outreach and Resource Support
  Services.
- Customer/program office: Wounded Warrior Regiment, Marine Corps Installations
  National Capital Region, RCO Quantico.
- Security marking in reports: `UNCLASSIFIED`, Distribution Statement A.
- Source contract fixture:
  `testdocs/WWR/contract/D.1+RFP+M0026426R0001 (2).pdf`.
- Recurring report fixtures: monthly status reports from March 2027 through
  January 2028.

The fixture CLI seeds the RFP PDF as the source contract document and attaches the
monthly status reports as the contract's reports bucket. These reports are the best
local fixtures for report-to-contract matching because the same contract ID is visible
in the report text and filenames are organized by reporting month.

### `testdocs/agor/`

Secondary recurring-report corpus for extraction robustness and cross-contract
aggregation.

- Contract: `N00014-12-C-0305`.
- Project: `AGOR 28`.
- Report type: SIO Shipyard Representative Bi-Weekly Progress Report.
- Shipyard: Dakota Creek Industries.
- Program office: Office of Naval Research.
- Security marking in reports: Distribution Statement A.
- Report dates represented in the local fixture set range from March 28, 2013
  through June 18, 2016.

This folder does not currently include the source contract document. The fixture CLI
therefore seeds AGOR as a report-only contract fixture. It is useful for testing the
processing pipeline on a different domain from WWR: shipyard progress, technical
issues, logistics, operator concerns, trial cards, spares, vendor coordination, and
schedule/work-item updates.

### `testdocs/natalies/`

Primary multi-contract fixture set for the contract analyst pipeline.

- Contracts:
  - `N40080-24-D-1042` Environmental Compliance and Permitting Support Services.
  - `N40080-25-D-2087` Naval Family Outreach and Resource Support Services.
  - `N40080-23-D-3155` Installation IT Help Desk and Tier 2 Support Services.
  - `N40080-22-D-4221` Facility Engineering and Sustainment Support Services.
  - `N40080-25-D-5318` Energy Program Support and Audit Services.
- `reports_pdf/` contains 30 weekly report PDFs whose filenames include the hard
  parent contract number.
- `reports_markdown/` contains expected-output style contract metadata and weekly
  report narratives that can seed local fixture contracts and baseline hints.

The fixture CLI seeds all five contracts from markdown metadata and attaches all 30
PDFs as weekly reports. Use this set to validate hard-link matching, regression
detection, hypothesis deduplication, and cross-contract semantic links. Expected
recurring patterns include tenant command verbal direction bypassing COR authority,
aging RFIs, scope ambiguity, cost variance tied to out-of-scope or superseded
direction, and government action delays blocking schedule-critical work.

## How To Use Them In The Build

Current use with the app:

- Seed all fixtures:

  ```sh
  bun run fixtures:seed -- --fixtures all
  bun run processing:run -- --limit 200
  ```

- Reset derived analysis for selected fixture families:

  ```sh
  bun run fixtures:seed -- --fixtures wwr,natalie --reset-analysis
  ```

- Upload selected PDFs through the contractor portal to validate PDF storage,
  extracted `text.json`, official review visibility, download, and SAS fallback
  behavior.
- Attach selected PDFs to intake emails to validate automated attachment storage
  and deterministic document IDs.
- Use WWR reports first because they form a clean end-to-end story around one
  contract ID.
- Build the local file-first synthetic corpus when the goal is cross-contract
  knowledge testing without relying on local SQL as the source of truth:

  ```sh
  bun run corpus:build-synthetic
  ```

  This writes an ignored corpus under `backend/data/corpus/navy-service-v1/` with
  `manifest.json`, `extraction_packet.jsonl`, and generated synthetic markdown/JSON
  source documents. The downloaded files under `testdocs/` are labeled
  `real_fixture`; generated reports, CPARS-style narratives, IPMDAR-style JSON, and
  lesson notes are labeled `synthetic_fixture`. Each contract in the generated
  corpus has one CPARS-style synthetic narrative marked `cpars_evaluation`; these
  are model-assisted fixture records for extraction testing, not real CPARS data.

Next product step:

- Continue improving source-contract baselines for WWR and Natalie.
- Prefer complete demo/eval packets when available: real source contract, CDRLs that
  require monthly performance reporting, the monthly reports, end-of-base-year CPARS,
  and PNRs. Those packets should become the best validation source for similar-contract
  failure-point analysis and future contract-writing guidance because they connect
  contract language, required reports, actual performance, and outcome evaluation.
- Add the AGOR source contract before treating AGOR as a complete baseline-bearing
  contract record.
- Expand deterministic and AI-backed extractors for report periods, labor metrics,
  deliverables, government actions, cost/schedule signals, and clause references.
- Use WWR, AGOR, and Natalie fixture sets for cross-contract dashboards as signal
  extraction matures.
- Expand the synthetic CPARS and IPMDAR fixtures as extraction needs become more
  specific. CPD/SPD JSON should test direct JSON ingestion; narrative Word/PDF files
  should test the OCR, NER, and LLM-assisted review pipeline.

Do not infer final government category codes from folder names alone. Parse them from
source contract metadata or a trusted procurement data source when category support is
implemented.
