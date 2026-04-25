# Product Direction

Federal Center SW is being built as a contract performance visibility system for
government acquisition users.

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
- Reporting period.
- Start date and end date.
- OCR-ed contract text and source document reference.
- Reports bucket, populated over time.
- Component or program office.
- Security level required to view the contract data.
- COR.
- CO.
- PM.
- Contract category, using official government letter codes rather than local labels.

## Intake Sources

Weekly performance reports can arrive through:

- Email intake, such as `reporting@navy.mil` or an equivalent mailbox.
- Automated matching to Contract ID and related metadata, similar to receipt matching
  workflows in expense systems.
- Manual upload through the portal.
- Scanned report uploads through the portal.

Both contractor and federal users may submit reports when authorized.

Additional data sources to support:

- Narrative performance reports from IPMDAR.
- CPD: Contract Performance Dataset.
- OIG or GAO reports that identify specific contract issues, when available.

## Document Processing

Incoming documents should flow through:

1. OCR.
2. Named entity recognition.
3. LLM-assisted review.

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

Extracted information must be sorted into the relevant contract category.

## Deliverables

First deliverable: a portal UI that displays the contract record, ingested reports,
processing outputs, and extracted performance signals by contract.

Second deliverable: cross-contract aggregation and insights, including dashboards and
reports that surface lessons learned within and across contract categories.
