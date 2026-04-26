from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Sequence
from uuid import NAMESPACE_URL, uuid5


ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "testdocs"
DEFAULT_OUTPUT_DIR = ROOT / "backend" / "data" / "corpus" / "navy-service-v1"


@dataclass(frozen=True)
class CorpusBuildResult:
    output_dir: Path
    fixture_groups: int
    contracts: int
    real_documents: int
    synthetic_documents: int


@dataclass(frozen=True)
class SyntheticDocument:
    contract_number: Optional[str]
    title: str
    filename: str
    document_kind: str
    content_type: str
    text: str
    expected_signal_types: Sequence[str]
    purpose: str


CONTRACTS = [
    {
        "fixture_group": "wwr",
        "contract_number": "M0026426R0001",
        "title": "Sergeant Merlin German Wounded Warrior Outreach and Resource Support Services",
        "agency_name": "United States Marine Corps",
        "office_name": "RCO Quantico",
        "contractor_name": "WWR Fixture Contractor",
        "psc_family": "R",
        "service_category": "Professional, Administrative & Management Support Services",
        "security_level": "unclassified_fixture",
        "notes": "Real local anchor includes one RFP PDF plus monthly status report PDFs.",
    },
    {
        "fixture_group": "agor",
        "contract_number": "N00014-12-C-0305",
        "title": "AGOR 28 Shipyard Representative Bi-Weekly Progress Reports",
        "agency_name": "Office of Naval Research",
        "office_name": "Shipyard Representative",
        "contractor_name": "Dakota Creek Industries",
        "psc_family": "J",
        "service_category": "Maintenance, Repair & Rebuilding of Equipment",
        "security_level": "unclassified_fixture",
        "notes": "Report-only local anchor; synthetic baseline bridge fills the missing source-contract gap for testing.",
    },
    {
        "fixture_group": "natalie",
        "contract_number": "N40080-24-D-1042",
        "title": "Environmental Compliance and Permitting Support Services",
        "agency_name": "Department of the Navy",
        "office_name": "NAVFAC Washington",
        "contractor_name": "Atlantic Environmental",
        "psc_family": "R",
        "service_category": "Professional, Administrative & Management Support Services",
        "security_level": "distribution_c_fixture",
        "notes": "Part of the multi-contract Natalie fixture set.",
    },
    {
        "fixture_group": "natalie",
        "contract_number": "N40080-25-D-2087",
        "title": "Naval Family Outreach and Resource Support Services",
        "agency_name": "Department of the Navy",
        "office_name": "NAVFAC Washington",
        "contractor_name": "Beacon Family Outreach",
        "psc_family": "G",
        "service_category": "Social Services",
        "security_level": "distribution_c_fixture",
        "notes": "Part of the multi-contract Natalie fixture set.",
    },
    {
        "fixture_group": "natalie",
        "contract_number": "N40080-23-D-3155",
        "title": "Installation IT Help Desk and Tier 2 Support Services",
        "agency_name": "Department of the Navy",
        "office_name": "NAVFAC Washington",
        "contractor_name": "Cardinal Technology Group",
        "psc_family": "D",
        "service_category": "IT & Telecommunications Services",
        "security_level": "distribution_c_fixture",
        "notes": "Part of the multi-contract Natalie fixture set.",
    },
    {
        "fixture_group": "natalie",
        "contract_number": "N40080-22-D-4221",
        "title": "Facility Engineering and Sustainment Support Services",
        "agency_name": "Department of the Navy",
        "office_name": "NAVFAC Atlantic",
        "contractor_name": "Meridian Engineering Partners",
        "psc_family": "C",
        "service_category": "Architect & Engineering Services",
        "security_level": "distribution_c_fixture",
        "notes": "Part of the multi-contract Natalie fixture set.",
    },
    {
        "fixture_group": "natalie",
        "contract_number": "N40080-25-D-5318",
        "title": "Energy Audit and Optimization Support Services",
        "agency_name": "Department of the Navy",
        "office_name": "NAVFAC Atlantic",
        "contractor_name": "Solstice Energy Consulting LLC",
        "psc_family": "R",
        "service_category": "Professional, Administrative & Management Support Services",
        "security_level": "distribution_c_fixture",
        "notes": "Part of the multi-contract Natalie fixture set.",
    },
]


SYNTHETIC_DOCUMENTS = [
    SyntheticDocument(
        contract_number="M0026426R0001",
        title="Synthetic Weekly Contractor Report - Outreach Backlog and Access Delays",
        filename="synthetic_weekly_report_2028-02-04.md",
        document_kind="weekly_report",
        content_type="text/markdown",
        purpose="Adds report-level risks, decisions, outcomes, and reusable lessons around a WWR-style service contract.",
        expected_signal_types=("risk", "decision", "outcome", "lesson_learned", "government_action_delay"),
        text="""# Synthetic Weekly Contractor Report

**Contract:** M0026426R0001
**Reporting Period:** 29 January 2028 - 04 February 2028
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Work Completed

- Completed 48 wounded warrior outreach contacts and 11 resource-navigation follow-ups.
- Closed 7 previously delayed referrals after base access rosters were refreshed.
- Delivered the draft outreach-event after-action matrix to the COR.

## Risks

- **Risk WWR-R-017, Base Access Delay:** Three new outreach specialists remain unable to access the installation case-management workspace. Expected impact is a 10 to 14 day delay in referral closure if credentials are not active by 09 February 2028.
- **Risk WWR-R-019, Stakeholder Direction:** A tenant command requested direct contractor support for a family resource event outside the approved monthly outreach schedule. Contractor is holding pending written COR direction.

## Decisions Requested

- COR decision requested on whether the family resource event is in scope or should be handled as a separately funded task.
- COR decision requested on whether referral aging above 21 days should trigger a weekly exception report.

## Outcomes This Period

- Referral backlog dropped from 31 to 24 open items after government roster correction.
- No personally identifiable information is included in this fixture report.

## Lesson Learned Candidate

When contractor staff onboarding depends on government access provisioning, the contract record should track credential lead time as a recurring risk metric. Future outreach support awards should include an onboarding service-level expectation and a named government access owner.
""",
    ),
    SyntheticDocument(
        contract_number="M0026426R0001",
        title="Synthetic Interim CPARS-Style Narrative - Outreach Services",
        filename="synthetic_cpars_interim_2028-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** M0026426R0001
**Evaluation Type:** Interim
**Evaluation Period:** 01 August 2027 - 31 January 2028
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Very Good. Contractor outreach specialists consistently produced complete referral notes and timely resource-navigation summaries. Minor quality issues involved inconsistent use of the latest monthly reporting template.

## Schedule

Rating: Satisfactory. Most monthly reports were submitted on time. Referral closure slipped in December and January when government access rosters were not updated for new staff.

## Management

Rating: Very Good. The contractor escalated out-of-scope stakeholder requests and avoided acting on verbal direction without COR confirmation.

## Reusable Lesson

For people-centered support services, management quality is strongly tied to disciplined direction control and early escalation of government access blockers.
""",
    ),
    SyntheticDocument(
        contract_number="N00014-12-C-0305",
        title="Synthetic Baseline Bridge - AGOR 28 Reporting Obligations",
        filename="synthetic_baseline_bridge.md",
        document_kind="source_contract_bridge",
        content_type="text/markdown",
        purpose="Fills the missing AGOR source-contract baseline so report-only PDFs can be analyzed in context.",
        expected_signal_types=("baseline_obligation", "reporting_cadence", "deliverable", "limitation"),
        text="""# Synthetic Baseline Bridge

**Contract:** N00014-12-C-0305
**Program:** AGOR 28
**Source Type:** Synthetic fixture for product testing because the local AGOR folder does not include the source contract.

## Baseline Assumptions For Testing

- Contractor and shipyard representative reports should identify construction progress, open technical issues, government-furnished information, trial-card status, spares, and schedule risks.
- Bi-weekly progress reporting is treated as the recurring report cadence.
- Trial-card closure, long-lead equipment status, and government review turnaround are expected monitored deliverables.

## Known Limitation

This bridge is not evidence of actual contract terms. It exists only to let the analyst pipeline test baseline-aware extraction against the downloaded AGOR progress reports.
""",
    ),
    SyntheticDocument(
        contract_number="N00014-12-C-0305",
        title="Synthetic Shipyard Decision Log - AGOR 28",
        filename="synthetic_decision_log_2016-06.md",
        document_kind="decision_log",
        content_type="text/markdown",
        purpose="Adds explicit decisions/outcomes around shipyard progress issues for cross-contract lesson extraction.",
        expected_signal_types=("decision", "outcome", "risk", "lesson_learned"),
        text="""# Synthetic Shipyard Decision Log

**Contract:** N00014-12-C-0305
**Reporting Month:** June 2016
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Decision 1 - Trial Card Prioritization

The program office directed closure of propulsion and habitability trial cards before lower-priority documentation clean-up items. Outcome: critical trial-card aging improved, but technical manual updates shifted two weeks later.

## Decision 2 - Long-Lead Spares Tracking

The shipyard representative requested a weekly spares exception list for items with delivery risk above 30 days. Outcome: three vendor delays were escalated earlier than in prior periods.

## Lesson Learned Candidate

Shipyard support contracts need a single visible aging list for trial cards, vendor spares, and government review actions. Treating those queues separately hides the combined schedule risk.
""",
    ),
    SyntheticDocument(
        contract_number="N00014-12-C-0305",
        title="Synthetic IPMDAR CPD Extract - AGOR 28",
        filename="synthetic_ipmdar_cpd_2016-06.json",
        document_kind="ipmdar_cpd",
        content_type="application/json",
        purpose="Provides direct-ingest JSON for earned-value style extraction tests.",
        expected_signal_types=("cost_variance", "schedule_variance", "earned_value"),
        text=json.dumps(
            {
                "source_type": "synthetic_fixture",
                "contract_number": "N00014-12-C-0305",
                "dataset": "IPMDAR_CPD",
                "period_end": "2016-06-18",
                "control_accounts": [
                    {
                        "wbs": "1.1 Shipyard Technical Support",
                        "bcws": 8200000,
                        "bcwp": 7950000,
                        "acwp": 8425000,
                        "variance_driver": "rework and late vendor responses",
                    },
                    {
                        "wbs": "1.2 Trial Card Closure",
                        "bcws": 1450000,
                        "bcwp": 1325000,
                        "acwp": 1510000,
                        "variance_driver": "government review cycle longer than plan",
                    },
                ],
            },
            indent=2,
        )
        + "\n",
    ),
    SyntheticDocument(
        contract_number="N00014-12-C-0305",
        title="Synthetic Interim CPARS-Style Narrative - AGOR 28",
        filename="synthetic_cpars_interim_2016-06.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N00014-12-C-0305
**Evaluation Type:** Interim
**Evaluation Period:** 01 January 2016 - 30 June 2016
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Satisfactory. Shipyard representative reporting captured material progress, technical issues, trial-card status, and vendor-spares concerns with enough detail for government review. Minor quality weaknesses involved inconsistent linkage between open issues and the affected work packages.

## Schedule

Rating: Marginal. Trial-card closure and technical manual updates slipped when government review queues and long-lead vendor responses aged beyond planned turnaround. The contractor improved visibility through exception lists, but the schedule impact was not fully recovered by the end of the period.

## Cost Control

Rating: Satisfactory. Earned-value style indicators showed unfavorable variance in shipyard technical support and trial-card closure. The contractor identified rework and late vendor responses as drivers and supported corrective tracking, but variance explanations arrived after the trend was already visible.

## Management

Rating: Satisfactory. The team remained responsive to program-office direction and escalated aging spares and trial-card issues. Management would be stronger with a single integrated government-action aging list shared across reviews.

## Reusable Lesson

Shipyard support contracts should track trial cards, vendor spares, and government review actions in one visible queue because separate lists hide the combined schedule risk.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-24-D-1042",
        title="Synthetic Environmental Compliance Decision Memo",
        filename="synthetic_decision_memo_2026-02-06.md",
        document_kind="decision_memo",
        content_type="text/markdown",
        purpose="Adds a clean decision/outcome artifact for a Natalie environmental contract.",
        expected_signal_types=("decision", "outcome", "scope_boundary", "lesson_learned"),
        text="""# Synthetic Decision Memo

**Contract:** N40080-24-D-1042
**Date:** 06 February 2026
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Decision

The COR confirmed that emergency spill-response tabletop facilitation is in scope only when tied to the approved compliance training calendar. A tenant command request for a separate weekend exercise requires written tasking and funding review before contractor support begins.

## Outcome

Atlantic Environmental avoided unplanned weekend labor and updated the risk register to flag tenant requests that bypass the approved training calendar.

## Reusable Lesson

Environmental service contracts need a visible boundary between recurring compliance support and event-driven operational response.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-24-D-1042",
        title="Synthetic Interim CPARS-Style Narrative - Environmental Compliance",
        filename="synthetic_cpars_interim_2026-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N40080-24-D-1042
**Evaluation Type:** Interim
**Evaluation Period:** 05 January 2026 - 06 February 2026
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Very Good. Environmental compliance work products were technically sound, used the required weekly reporting format, and identified scope-boundary questions before the contractor performed potentially unauthorized tenant-command support.

## Schedule

Rating: Satisfactory. The stormwater permit renewal task order remained executable, but RFI-004 on permit pathway selection created a five-day schedule slip against the original baseline. The contractor clearly flagged the critical-path impact and updated the projected submittal date.

## Cost Control

Rating: Satisfactory. No material cost overrun is shown in the fixture period. Cost exposure was limited because the contractor waited for written direction before accepting emergency exercise support outside the approved compliance calendar.

## Management

Rating: Very Good. Management disciplined informal stakeholder requests, documented COR decisions on RFIs, and separated recurring compliance support from event-driven response work.

## Reusable Lesson

Environmental service contracts should make scope boundaries and RFI aging visible on the contract page so tenant requests, permit-path decisions, and schedule impacts are reviewed together.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-25-D-2087",
        title="Synthetic Interim CPARS-Style Narrative - Family Outreach",
        filename="synthetic_cpars_interim_2026-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N40080-25-D-2087
**Evaluation Type:** Interim
**Evaluation Period:** 05 January 2026 - 06 February 2026
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Satisfactory. Outreach interactions and weekly reports were complete and appropriate for a family-support services contract. The contractor maintained respectful communication and documented referrals without including sensitive personal details in the fixture record.

## Schedule

Rating: Satisfactory. Routine outreach events and weekly reports stayed on cadence, but referral follow-up timeliness showed early risk as workload increased. The contractor identified aging referrals and began separating urgent family-resource requests from routine outreach work.

## Cost Control

Rating: Satisfactory. The fixture period does not show a cost overrun. Future cost pressure could emerge if referral volume requires additional staffing or more frequent outreach events than the baseline assumed.

## Management

Rating: Satisfactory. Program management was transparent about workload risk and kept the COR informed when stakeholder requests could affect staffing or referral priorities.

## Reusable Lesson

Family outreach contracts should track referral aging, outreach volume, and staffing capacity together. Early warning thresholds help distinguish normal demand variation from a service-level risk that needs government action.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-23-D-3155",
        title="Synthetic IT Help Desk Staffing Corrective Action Plan",
        filename="synthetic_corrective_action_plan_2026-02.md",
        document_kind="corrective_action_plan",
        content_type="text/markdown",
        purpose="Adds contractor-side mitigation content for service desk delays and staffing risk.",
        expected_signal_types=("staffing_issue", "risk", "mitigation", "outcome"),
        text="""# Synthetic Corrective Action Plan

**Contract:** N40080-23-D-3155
**Month:** February 2026
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Trigger

Tier 2 average time to resolve exceeded the 5.0 day target for two consecutive weekly reports. Open RFIs on after-hours scope and tenant-specific software deployment remain unresolved.

## Contractor Mitigation

- Add one temporary Tier 2 analyst for 30 days using existing labor ceiling.
- Freeze tenant-requested software deployments that lack approved security baseline documentation.
- Provide a weekly aging list for incidents blocked by government access or authorization.

## Expected Outcome

Reduce Tier 2 average time to resolve below 4.8 days by the end of February if government decisions on RFI-041 and RFI-044 are received by 13 February.

## Lesson Learned Candidate

Help desk service levels degrade when tenant-specific requests are accepted without a controlled intake and authorization path.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-23-D-3155",
        title="Synthetic Interim CPARS-Style Narrative - IT Help Desk",
        filename="synthetic_cpars_interim_2026-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N40080-23-D-3155
**Evaluation Type:** Interim
**Evaluation Period:** 01 January 2026 - 28 February 2026
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Satisfactory. Help desk documentation and technical resolutions were generally complete, but Tier 2 aging increased when tenant-specific software requests lacked approved security baseline documentation.

## Schedule

Rating: Marginal. Average time to resolve exceeded the 5.0 day target for two consecutive weekly reports. The contractor proposed a temporary Tier 2 analyst and an aging list, but the recovery depended on government decisions for RFI-041 and RFI-044.

## Cost Control

Rating: Satisfactory. The temporary staffing action used existing labor ceiling in the fixture scenario. Continued unresolved scope questions could create future cost pressure if after-hours or tenant-specific work expands without authorization.

## Management

Rating: Satisfactory. Management acknowledged the service-level degradation, froze unsupported tenant deployments, and submitted a corrective action plan. Stronger intake controls would have reduced the recurring issue earlier.

## Reusable Lesson

IT service contracts need controlled intake, government authorization status, and staffing risk on the same dashboard because unresolved tenant requests can look like contractor delay.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-22-D-4221",
        title="Synthetic Engineering Services REA Chronology",
        filename="synthetic_rea_chronology_2026-02.md",
        document_kind="rea_chronology",
        content_type="text/markdown",
        purpose="Adds a structured chronology for verbal direction, rework, and scope-control analysis.",
        expected_signal_types=("scope_change", "cost_variance", "decision", "lesson_learned"),
        text="""# Synthetic REA Chronology

**Contract:** N40080-22-D-4221
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Chronology

- 15 April 2025: Tenant stakeholder verbally requested Hangar 405 mechanical analysis using legacy facility data.
- 03 June 2025: Contractor completed first analysis package.
- 18 July 2025: COR issued written direction requiring updated as-built drawings.
- 29 August 2025: Contractor completed re-analysis and identified $187K of rework labor.
- 05 February 2026: Contractor prepared REA narrative for government review.

## Decision Point

KO/COR must determine whether the rework was caused by government direction change, contractor planning assumptions, or ambiguous baseline scope.

## Reusable Lesson

Engineering support services need written task confirmation before work starts when a tenant stakeholder provides technical direction that changes source data, assumptions, or deliverable format.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-22-D-4221",
        title="Synthetic Interim CPARS-Style Narrative - Facility Engineering",
        filename="synthetic_cpars_interim_2026-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N40080-22-D-4221
**Evaluation Type:** Interim
**Evaluation Period:** 15 April 2025 - 05 February 2026
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Satisfactory. Engineering analysis packages were technically useful, but early work relied on legacy facility data and later required re-analysis after the COR directed use of updated as-built drawings.

## Schedule

Rating: Marginal. Re-analysis shifted deliverable completion and created a chronology of verbal direction, written correction, and follow-on review. The contractor documented the sequence, but written task confirmation should have occurred before the initial analysis began.

## Cost Control

Rating: Marginal. The fixture chronology identifies approximately $187K in rework labor tied to the changed source data and resulting request for equitable adjustment analysis.

## Management

Rating: Satisfactory. Management preserved the decision record and elevated the cause of rework for KO/COR determination. Performance would improve with firmer controls on tenant-provided direction.

## Reusable Lesson

Engineering support contracts should require written COR confirmation when stakeholder direction changes assumptions, source data, labor mix, or deliverable format. That control prevents ambiguous rework from becoming a late cost dispute.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-25-D-5318",
        title="Synthetic Energy Audit Outcome Report",
        filename="synthetic_outcome_report_2026-02.md",
        document_kind="outcome_report",
        content_type="text/markdown",
        purpose="Adds measurable success/outcome content so cross-contract aggregation includes positive lessons.",
        expected_signal_types=("success", "outcome", "lesson_learned", "deliverable"),
        text="""# Synthetic Energy Audit Outcome Report

**Contract:** N40080-25-D-5318
**Reporting Period:** February 2026
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Outcome

Solstice Energy completed four metering reviews and identified two controls changes projected to reduce annual energy use by 6.5 percent for the reviewed facilities.

## Decision

The COR approved a focused follow-on analysis for Building 221 because the initial audit showed high return and no expected mission disruption.

## Success Pattern

Energy support work produced faster decisions when findings were tied to facility-level cost, expected payback period, and operational disruption risk in the same report.

## Reusable Lesson

Outcome reports should connect technical recommendations to dollars, mission disruption, and implementation owner. This makes cross-contract benchmarking more useful than a simple list of audit findings.
""",
    ),
    SyntheticDocument(
        contract_number="N40080-25-D-5318",
        title="Synthetic Interim CPARS-Style Narrative - Energy Audit",
        filename="synthetic_cpars_interim_2026-02.md",
        document_kind="cpars_evaluation",
        content_type="text/markdown",
        purpose="Provides qualitative evaluation-style text for CPARS extraction without using protected CPARS data.",
        expected_signal_types=("rating_trend", "quality", "schedule", "cost_control", "management", "lesson_learned"),
        text="""# Synthetic Interim CPARS-Style Narrative

**Contract:** N40080-25-D-5318
**Evaluation Type:** Interim
**Evaluation Period:** 01 February 2026 - 28 February 2026
**Source Type:** Synthetic fixture for product testing. Not CPARS data.

## Quality

Rating: Very Good. Energy audit findings connected technical controls changes to facility-level cost, projected annual energy reduction, payback considerations, and mission-disruption risk.

## Schedule

Rating: Very Good. The contractor completed four metering reviews during the reporting period and produced actionable recommendations early enough for COR follow-on analysis approval.

## Cost Control

Rating: Very Good. The fixture outcome report identifies two controls changes projected to reduce annual energy use by 6.5 percent. Recommendations were framed with implementation owner and operational impact, making cost-benefit review faster.

## Management

Rating: Very Good. Management coordinated effectively with facility stakeholders, separated quick-return controls changes from longer-term analysis, and presented decision-ready options to the COR.

## Reusable Lesson

Energy support work becomes more useful for benchmarking when outcome reports tie each recommendation to dollars, mission disruption, payback period, and implementation owner rather than listing findings alone.
""",
    ),
    SyntheticDocument(
        contract_number=None,
        title="Synthetic Cross-Contract Lesson Notes",
        filename="synthetic_cross_contract_lessons.md",
        document_kind="cross_contract_lessons",
        content_type="text/markdown",
        purpose="Provides a human-readable target for the shared intelligence layer across the three fixture groups.",
        expected_signal_types=("cross_contract_pattern", "lesson_learned", "control_recommendation"),
        text="""# Synthetic Cross-Contract Lesson Notes

**Scope:** WWR, AGOR, and Natalie fixture groups
**Source Type:** Synthetic fixture for product testing. Not an official government record.

## Pattern 1 - Verbal Or Informal Direction Creates Rework

Seen in WWR outreach event requests, Cardinal tenant-specific IT requests, and Meridian engineering tasking. Reusable control: require written COR confirmation before contractor execution when the request changes schedule, labor mix, source data, or deliverable format.

## Pattern 2 - Government Action Aging Drives Contractor Performance Risk

Seen in access roster delays, open RFIs, trial-card review queues, and authorization-dependent help desk incidents. Reusable control: show government-owned aging queues beside contractor-owned performance measures.

## Pattern 3 - Outcome Reports Need Decision Context

Seen in energy audit outcomes and outreach backlog reporting. Reusable control: each report should identify the decision needed, owner, due date, expected impact, and permission boundary.

## Pattern 4 - Positive Lessons Matter

The knowledge layer should capture successful mitigations, not only risks. Useful examples include written direction discipline, weekly exception lists, staffing surge actions, and outcome reports tied to measurable operational impact.
""",
    ),
]


CROSS_CONTRACT_PATTERNS = [
    {
        "pattern_id": "direction-control",
        "title": "Informal stakeholder direction creates rework and cost variance",
        "contracts": ["M0026426R0001", "N40080-23-D-3155", "N40080-22-D-4221"],
        "signal_types": ["scope_boundary", "cost_variance", "decision", "lesson_learned"],
        "recommended_control": "Require written COR confirmation before executing tenant requests that change labor, schedule, assumptions, or deliverable format.",
    },
    {
        "pattern_id": "government-action-aging",
        "title": "Aging government actions block service performance",
        "contracts": ["M0026426R0001", "N00014-12-C-0305", "N40080-23-D-3155"],
        "signal_types": ["government_action_delay", "risk", "schedule_variance"],
        "recommended_control": "Track government-owned action age beside contractor-owned service metrics on every contract page.",
    },
    {
        "pattern_id": "outcome-context",
        "title": "Reports become reusable when outcomes are tied to decisions and owners",
        "contracts": ["N40080-25-D-5318", "M0026426R0001", "N00014-12-C-0305"],
        "signal_types": ["outcome", "decision", "success", "lesson_learned"],
        "recommended_control": "Require outcome reports to name decision owner, expected impact, and next action.",
    },
]


def build_synthetic_corpus(
    fixture_root: Path = FIXTURE_ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> CorpusBuildResult:
    fixture_root = fixture_root.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    synthetic_root = output_dir / "synthetic"
    synthetic_root.mkdir(parents=True, exist_ok=True)
    real_documents = _real_fixture_documents(fixture_root)
    synthetic_documents = _write_synthetic_documents(synthetic_root, output_dir)

    manifest = {
        "schema_version": "synthetic_corpus_v1",
        "corpus_name": "Department of Navy service-contract v1 fixture corpus",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_policy": {
            "real_sources": "Downloaded/local fixture PDFs and markdown under testdocs.",
            "synthetic_sources": "Generated local fixture documents, always marked synthetic_fixture.",
            "api_policy": "No keyed APIs and no SAM.gov web-UI scraping.",
            "database_policy": "File corpus is authoritative for this phase; local SQL is optional scratch state.",
        },
        "fixture_groups": [
            {
                "name": "wwr",
                "description": "One RFP plus recurring monthly status reports for Wounded Warrior outreach support.",
            },
            {
                "name": "agor",
                "description": "Report-only AGOR 28 shipyard representative progress-report corpus.",
            },
            {
                "name": "natalie",
                "description": "Multi-contract NAVFAC weekly-report corpus with expected-output markdown.",
            },
        ],
        "contracts": _contracts_with_documents(real_documents, synthetic_documents),
        "cross_contract_patterns": CROSS_CONTRACT_PATTERNS,
        "recommended_next_pipeline": [
            "Extract text from PDFs where text artifacts are absent.",
            "Run cheap model labeling over synthetic and real fixture text.",
            "Use Sonnet-level synthesis for cited contract pages and cross-contract lessons.",
            "Keep synthetic_fixture evidence visually distinct from real_fixture and official evidence.",
        ],
    }
    _write_json(output_dir / "manifest.json", manifest)
    _write_jsonl(output_dir / "extraction_packet.jsonl", _extraction_rows(real_documents, synthetic_documents, output_dir))
    _write_markdown_readme(output_dir, manifest, len(real_documents), len(synthetic_documents))

    return CorpusBuildResult(
        output_dir=output_dir,
        fixture_groups=3,
        contracts=len(CONTRACTS),
        real_documents=len(real_documents),
        synthetic_documents=len(synthetic_documents),
    )


def _real_fixture_documents(fixture_root: Path) -> List[dict]:
    documents: List[dict] = []
    wwr_root = fixture_root / "WWR"
    agor_root = fixture_root / "agor"
    natalie_root = fixture_root / "natalies"

    wwr_contract = wwr_root / "contract" / "D.1+RFP+M0026426R0001 (2).pdf"
    if wwr_contract.exists():
        documents.append(
            _real_doc(
                path=wwr_contract,
                fixture_group="wwr",
                contract_number="M0026426R0001",
                title="WWR RFP",
                document_kind="source_contract",
            )
        )
    for path in sorted(wwr_root.glob("*.pdf")):
        documents.append(
            _real_doc(
                path=path,
                fixture_group="wwr",
                contract_number="M0026426R0001",
                title=path.stem.replace("_", " "),
                document_kind="monthly_report",
            )
        )

    for path in sorted(agor_root.glob("*.pdf")):
        documents.append(
            _real_doc(
                path=path,
                fixture_group="agor",
                contract_number="N00014-12-C-0305",
                title=f"AGOR progress report {path.stem}",
                document_kind="biweekly_report",
            )
        )

    natalie_markdown_by_contract = {
        "contract_1": "N40080-24-D-1042",
        "contract_2": "N40080-25-D-2087",
        "contract_3": "N40080-23-D-3155",
        "contract_4": "N40080-22-D-4221",
        "contract_5": "N40080-25-D-5318",
    }
    for path in sorted((natalie_root / "reports_markdown").glob("*.md")):
        prefix = path.name.split("_", 2)[0] + "_" + path.name.split("_", 2)[1]
        documents.append(
            _real_doc(
                path=path,
                fixture_group="natalie",
                contract_number=natalie_markdown_by_contract.get(prefix, ""),
                title=path.stem.replace("_", " ").title(),
                document_kind="fixture_expected_output",
            )
        )
    for path in sorted((natalie_root / "reports_pdf").glob("*.pdf")):
        contract_number = path.name.split("_", 1)[0]
        documents.append(
            _real_doc(
                path=path,
                fixture_group="natalie",
                contract_number=contract_number,
                title=path.stem.replace("_", " "),
                document_kind="weekly_report",
            )
        )
    return documents


def _real_doc(path: Path, fixture_group: str, contract_number: str, title: str, document_kind: str) -> dict:
    suffix = path.suffix.lower()
    content_type = "application/pdf" if suffix == ".pdf" else "text/markdown" if suffix == ".md" else "application/octet-stream"
    return {
        "document_id": _document_id("real_fixture", path.as_posix()),
        "fixture_group": fixture_group,
        "contract_number": contract_number,
        "title": title,
        "document_kind": document_kind,
        "source_type": "real_fixture",
        "synthetic": False,
        "path": _relative(path),
        "content_type": content_type,
        "sha256": _sha256(path),
        "text_available": suffix == ".md",
        "expected_signal_types": [],
        "purpose": "Downloaded/local fixture source anchor.",
    }


def _write_synthetic_documents(synthetic_root: Path, output_dir: Path) -> List[dict]:
    documents: List[dict] = []
    for item in SYNTHETIC_DOCUMENTS:
        group = "cross_contract" if item.contract_number is None else _group_for_contract(item.contract_number)
        contract_dir = synthetic_root / group / (item.contract_number or "shared")
        contract_dir.mkdir(parents=True, exist_ok=True)
        path = contract_dir / item.filename
        path.write_text(item.text, encoding="utf-8")
        documents.append(
            {
                "document_id": _document_id("synthetic_fixture", f"{item.contract_number}:{item.filename}"),
                "fixture_group": group,
                "contract_number": item.contract_number,
                "title": item.title,
                "document_kind": item.document_kind,
                "source_type": "synthetic_fixture",
                "synthetic": True,
                "path": _relative_to(path, output_dir),
                "content_type": item.content_type,
                "sha256": _sha256(path),
                "text_available": True,
                "expected_signal_types": list(item.expected_signal_types),
                "purpose": item.purpose,
            }
        )
    return documents


def _contracts_with_documents(real_documents: Sequence[dict], synthetic_documents: Sequence[dict]) -> List[dict]:
    all_documents = list(real_documents) + list(synthetic_documents)
    contracts = []
    for contract in CONTRACTS:
        contract_documents = [
            doc for doc in all_documents if doc.get("contract_number") == contract["contract_number"]
        ]
        contracts.append(
            {
                **contract,
                "document_counts": {
                    "real_fixture": sum(1 for doc in contract_documents if doc["source_type"] == "real_fixture"),
                    "synthetic_fixture": sum(
                        1 for doc in contract_documents if doc["source_type"] == "synthetic_fixture"
                    ),
                },
                "documents": contract_documents,
            }
        )
    shared_synthetic = [doc for doc in synthetic_documents if not doc.get("contract_number")]
    if shared_synthetic:
        contracts.append(
            {
                "fixture_group": "cross_contract",
                "contract_number": None,
                "title": "Cross-contract shared intelligence fixtures",
                "agency_name": "Department of the Navy",
                "office_name": "Fixture corpus",
                "contractor_name": None,
                "psc_family": None,
                "service_category": "Cross-contract lessons",
                "security_level": "fixture",
                "notes": "Synthetic shared lessons and patterns; not tied to a single contract.",
                "document_counts": {"real_fixture": 0, "synthetic_fixture": len(shared_synthetic)},
                "documents": shared_synthetic,
            }
        )
    return contracts


def _extraction_rows(
    real_documents: Sequence[dict],
    synthetic_documents: Sequence[dict],
    output_dir: Path,
) -> Iterable[dict]:
    for doc in real_documents:
        row = {**doc, "text": None}
        path = ROOT / doc["path"]
        if doc["text_available"] and path.exists():
            row["text"] = path.read_text(encoding="utf-8", errors="replace")
        yield row
    for doc in synthetic_documents:
        path = output_dir / doc["path"]
        yield {**doc, "text": path.read_text(encoding="utf-8", errors="replace") if path.exists() else None}


def _write_markdown_readme(output_dir: Path, manifest: dict, real_count: int, synthetic_count: int) -> None:
    lines = [
        "# Navy Service V1 Fixture Corpus",
        "",
        "This local corpus combines downloaded fixture documents with clearly labeled synthetic fixture evidence.",
        "It is intended to exercise the institutional-knowledge workflow without treating generated material as official records.",
        "",
        f"- Fixture groups: {len(manifest['fixture_groups'])}",
        f"- Contract records represented: {len(CONTRACTS)}",
        f"- Real fixture documents: {real_count}",
        f"- Synthetic fixture documents: {synthetic_count}",
        "",
        "## Provenance Rules",
        "",
        "- `real_fixture` means a local downloaded or checked-in fixture file under `testdocs/`.",
        "- `synthetic_fixture` means generated data for product testing only.",
        "- Synthetic evidence can validate extraction, permissions, and UI behavior, but should not be shown as official source evidence.",
        "- This corpus intentionally avoids keyed APIs and SAM.gov web-UI scraping.",
        "",
        "## Files",
        "",
        "- `manifest.json`: contract, document, provenance, and pattern metadata.",
        "- `extraction_packet.jsonl`: flattened records for model labeling and synthesis.",
        "- `synthetic/`: generated markdown and JSON source documents.",
        "",
        "## Cross-Contract Patterns",
        "",
    ]
    for pattern in CROSS_CONTRACT_PATTERNS:
        lines.append(f"- **{pattern['title']}**: {pattern['recommended_control']}")
    lines.append("")
    (output_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def _group_for_contract(contract_number: str) -> str:
    for contract in CONTRACTS:
        if contract["contract_number"] == contract_number:
            return str(contract["fixture_group"])
    return "unknown"


def _document_id(source_type: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"{source_type}:{key}"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path) -> str:
    return _relative_to(path, ROOT)


def _relative_to(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the local Navy service synthetic fixture corpus.")
    parser.add_argument("--fixture-root", default=str(FIXTURE_ROOT))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()
    result = build_synthetic_corpus(
        fixture_root=Path(args.fixture_root),
        output_dir=Path(args.output_dir),
    )
    print(
        "Built synthetic Navy service corpus at "
        f"{result.output_dir}: {result.contracts} contract(s), "
        f"{result.real_documents} real fixture document(s), "
        f"{result.synthetic_documents} synthetic fixture document(s)."
    )


if __name__ == "__main__":
    main()
