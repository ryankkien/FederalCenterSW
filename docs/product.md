# Product Direction

Federal Center SW is being built as a contract performance visibility system for
government acquisition users.

This document is a future-build product brief. It records capabilities to design and
build over time; it should not be read as a statement that these features already exist.

## Product Positioning

The platform ingests contractor reports and uses AI to extract and structure
institutional knowledge, capturing risks, decisions, outcomes, and lessons learned in a
form that can be reused across contracts with appropriate permissions. The intended
result is a shared intelligence layer that helps agencies identify patterns, avoid
repeating mistakes, and continuously improve contract performance at scale.

During early development, synthetic fixture evidence may be used to prove the workflow
around the three downloaded fixture families. Synthetic records must stay clearly
marked and separate from official or uploaded evidence so generated data can validate
extraction, permissions, and cross-contract reuse without being mistaken for a real
government source.

## Users And Access

Primary users:

- CO: Contracting Officer.
- COR: Contracting Officer Representative.
- PM: Project or Program Manager.

Users authenticate with Microsoft Entra ID. Authorization should use RBAC backed by
federated groups for role membership. Contract data visibility must honor the security
level required for that contract and its attached reports.

## Contract Record

The system should maintain one structured JSON-style record per contract. Expected fields:

- Contract ID.
- Contract or order number.
- Reporting period.
- Start date and end date.
- OCR-ed contract text and source document reference.
- Reports bucket, populated over time.
- Component or program office.
- Security level required to view the contract data.
- COR.
- CO.
- PM.
- Contractor identifiers and category codes such as DUNS, PSC, and NAICS when
  available from authoritative sources.
- Contract category, using official government codes rather than local labels.

## Intake Sources

Weekly performance reports can arrive through:

- Email intake, such as `reporting@navy.mil` or an equivalent mailbox.
- Automated matching to Contract ID and related metadata, similar to receipt matching
  workflows in expense systems.
- Manual upload through the portal.
- Scanned report uploads through the portal.

Both contractor and federal users may submit reports when authorized.

Additional data sources to support:

- CPARS unclassified evaluation records, including qualitative CO/COR narratives,
  contractor response narratives, structured ratings, evaluation type, and period of
  performance.
- IPMDAR CPD: Contract Performance Dataset JSON.
- IPMDAR SPD: Schedule Performance Dataset JSON.
- IPMDAR narrative performance reports in Word or PDF form.
- OIG or GAO reports that identify specific contract issues, when available.

Current official-source discovery should prioritize Department of Navy service
contracts. Treat this as a v1 targeting filter for SAM.gov, USAspending, and related
official-source mining, not as a substitute for authoritative contract identifiers,
PSC, NAICS, or security/access metadata.
SAM.gov Contract Opportunities records should be treated as discovery/source evidence
until they can be linked to an award, task order, or uploaded contract file; solicitations
and sources-sought notices should not create canonical contract records by themselves.
Federal Register records should be used as regulatory context, especially FAR, DFARS,
OFPP, and Navy acquisition notices; they should support interpretation and rule-tracking
rather than contract-level performance findings.

For Navy service-contract labeling, use PSC families as the first taxonomy layer:
`A` R&D, `B` studies/analysis, `C` A&E, `D` IT/telecom, `E` structures/facilities
purchase, `F` natural resources, `G` social services, `H` quality/testing/inspection,
`J` equipment maintenance, `K` equipment modification, `L` technical representatives,
`M` government-owned facility operation, `N` equipment installation, `P` salvage,
`Q` medical, `R` professional/admin/management support, `S` utilities/housekeeping,
`T` publication/media services, `U` education/training, `V` transportation/travel,
`W` equipment lease/rental, `X` facilities lease/rental, `Y` construction, and `Z`
real-property maintenance/repair/alteration. Preserve full PSC, NAICS, command,
contracting office, funding office, vendor UEI/CAGE, dates, value, competition,
set-aside, and place-of-performance metadata as additional labels.

The v1 wiki index should be contract-first. Clicking a contract should onboard a CO,
COR, or PM with a cited article covering identity, contractor, baseline obligations,
latest weekly/monthly updates, open issues, official-source context, limitations, and
links to contractor and topic pages. Contractor pages should present evidence labels
such as schedule variance events, funding variance events, unresolved issues, and
contradiction counts rather than unsupported character judgments.

For CPARS, treat unclassified records as a high-value qualitative source. Candidate
ingestion should start from contract numbers, potentially discovered through SAM.gov
where Navy-scoped API access is available, then parse authenticated CPARS HTML from
an authorized Focal Point-style session into JSON for the contract record. Extract
quality, schedule, cost control, management, and regulatory compliance ratings; CO/COR
and contractor narratives; rating definitions such as Exceptional through
Unsatisfactory; evaluation type such as interim or final; and the period of
performance. Join CPARS records to the contract master record through `contract_id`.

For IPMDAR, treat CPD and SPD as structured monthly JSON inputs. CPD covers earned
value measures such as BCWS, BCWP, ACWP, ETC, and EAC by control account. SPD covers
schedule measures such as milestones, critical path, and planned versus actual dates.
Those JSON datasets should be ingested directly without OCR. IPMDAR narrative
performance reports may arrive as Word or PDF and should use the OCR, named entity
recognition, and LLM-assisted review pipeline. Historical EVM-CR access may require
portal/manual retrieval if no API is available; current and future reports should also
be routed to the intake mailbox when possible.

## Document Processing

Incoming documents should flow through:

1. OCR.
2. Named entity recognition.
3. LLM-assisted review.

Structured JSON inputs such as IPMDAR CPD and SPD should bypass OCR and flow through
schema validation, direct fact extraction, contract matching, and downstream analysis.

The review pipeline should extract and classify:

- Timeliness.
- Cost status, including on target, below target, and above target.
- Process documentation.
- Lessons learned.
- Risks and problems.
- Successes.
- Delays and performance patterns.
- Staffing problems.
- Missing or late deliverables.
- Inconsistencies.
- Comparisons and benchmarking.
- CPARS rating trends and narrative themes.
- Earned value and schedule variance from IPMDAR CPD/SPD inputs.

Extracted information must be sorted into the relevant contract category.

## Contract Analyst Pipeline

The analyst pipeline should keep hard parentage and soft similarity separate:

- `document_uploads.contract_id` records the hard parent contract for a document.
- Semantic links connect related contracts or documents without changing the hard
  parent relationship.

Baseline processing should maintain an interpreted current baseline per contract,
baseline obligations, and append-only revisions when source contract documents, task
orders, modifications, or official direction change the baseline.

Weekly and monthly report processing should compare new evidence against the baseline,
prior reports, prior decisions, active topics, and open hypotheses. Regression findings
should be citation-backed and grouped into hypotheses only when the underlying evidence
supports the narrative. Hypotheses can be proposed, investigating, supported,
contradicted, or closed, and should not be presented as fact unless supported by linked
evidence.

External research can support explanatory context, but v1 should restrict it to
official sources such as `.gov`, `.mil`, Acquisition.gov, Federal Register, GAO/OIG,
Congress.gov, and agency domains. Uploaded contract-file evidence remains authoritative
for contract-specific findings.

## Future Build Targets

Build these capabilities in this general order unless a later implementation plan says
otherwise:

1. Contract record foundation: store one structured JSON-style record per contract with
   role-aware visibility.
2. Report intake: support email intake, automated contract matching, manual portal upload,
   and scanned report uploads.
3. Document processing: run OCR, named entity recognition, and LLM-assisted review.
4. Contract UI: display the contract record, ingested reports, processing outputs, and
   extracted performance signals by contract.
5. Cross-contract insights: aggregate signals across contracts and categories into
   dashboards and reports.

## Deliverables

First deliverable: a portal UI that displays the contract record, ingested reports,
processing outputs, and extracted performance signals by contract.

Second deliverable: cross-contract aggregation and insights, including dashboards and
reports that surface lessons learned within and across contract categories.
