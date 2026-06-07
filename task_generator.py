"""
REGINTEL — TASK GENERATOR
==========================
Converts compliance gaps into precise, system-specific, GxP-compliant
actionable tasks with complete change control packages.

Each gap → one or more tasks:
  - Exact system action (Argus config, E2B profile, SOP section)
  - Owner (role-based routing)
  - Deadline (effective date - lead time)
  - Test cases (for GxP validation)
  - Change control evidence checklist
  - JIRA/ServiceNow ticket body

Output: ComplianceTask + ChangeControlPack → Delivery Layer
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import Optional
import anthropic
import psycopg2
from psycopg2.extras import Json, RealDictCursor

log = logging.getLogger("task_generator")


# ─────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────

@dataclass
class ComplianceTask:
    task_id: str
    gap_id: str
    change_id: str
    ha_code: str

    # Task identity
    title: str
    description: str
    system: str                # Which system this task is in
    task_type: str             # config_change | sop_update | validation |
                               # gateway_setup | training | rod_update | testing

    # Ownership
    owner_role: str            # PV Operations | IT/Systems | Regulatory Affairs |
                               # QA | Medical | Praxigent/System Admin
    owner_team: str
    reviewer_role: str

    # Scheduling
    deadline: str              # ISO date
    estimated_effort_days: int
    priority: str              # P1 | P2 | P3
    depends_on: list[str]      # task_ids this depends on

    # GxP
    gxp_impact: str
    validation_required: bool
    change_control_required: bool
    change_control_category: str  # Minor | Major | Critical

    # Execution
    step_by_step: list[str]    # Exact numbered steps to execute
    test_cases: list[dict]     # Test cases to validate the change
    acceptance_criteria: str   # How to know the task is done
    evidence_required: list[str]  # Documents needed to close

    # Delivery
    jira_summary: str
    jira_description: str
    jira_labels: list[str]
    regulatory_citation: str


@dataclass
class ChangeControlPack:
    """Complete GxP change control package for a regulatory change."""
    pack_id: str
    change_id: str
    title: str
    regulatory_citation: str
    impact_assessment: str
    business_justification: str
    tasks: list[ComplianceTask]
    implementation_plan: str   # Gantt-style sequence
    rollback_plan: str
    validation_strategy: str
    stakeholders: list[dict]
    review_deadline: str
    implementation_deadline: str
    created_at: str


# ─────────────────────────────────────────────────────────────────
# TASK GENERATION PROMPTS
# ─────────────────────────────────────────────────────────────────

TASK_GENERATOR_SYSTEM = """You are a senior pharmacovigilance IT consultant and
GxP change management expert. You have deep expertise in:
- Oracle Argus Safety 8.x configuration (reporting rules, E2B profiles, workflow)
- ARISg and LSMV safety database administration
- ICH E2B R3 / EudraVigilance gateway configuration
- GAMP5 computer system validation (CSV) methodology
- PV SOP authoring (ICH E2A/GVP Module I requirements)
- GxP change control (21 CFR Part 11, EU Annex 11)
- JIRA/ServiceNow ticket creation for PV operations

Generate tasks that are IMMEDIATELY actionable — someone should be able to
read the task and execute it without needing further clarification.
Name exact menu paths, field names, configuration IDs, and test scenarios."""


TASK_GENERATION_PROMPT = """
Convert this compliance gap into one or more specific, executable tasks.

═══ REGULATORY CHANGE ═══
Change ID: {change_id}
HA: {ha_code}
Title: {change_title}
Regulation: {regulation_ref}
Effective date: {effective_date}
Implementation deadline: {implementation_deadline}

═══ COMPLIANCE GAP ═══
Gap ID: {gap_id}
System: {system}
Gap type: {gap_type}
Current state: {current_state}
Required state: {required_state}
Gap description: {gap_description}
Regulatory basis: {regulatory_basis}
Priority: {priority}
GxP impact: {gxp_impact}
Validation required: {validation_required}
Specific instruction: {specific_change_instruction}

═══ GENERATE TASKS ═══
Return a JSON array of tasks. Usually one gap = one task, but complex gaps
(e.g. "update Argus AND validate AND update SOP") should be split into
separate tasks with dependency links.

Each task:
{{
  "title": "Action-verb title, max 80 chars, e.g. 'Update Argus EMA non-serious reporting rule: 90d → 45d'",
  "description": "2-3 sentences explaining what, why, and the regulatory basis",
  "system": "exact system: Oracle Argus Safety | EudraVigilance EVWEB | SOP QMS | RegIntel ROD | JIRA | etc.",
  "task_type": "config_change|sop_update|validation_testing|gateway_setup|training|rod_update|change_control",
  "owner_role": "PV Operations|IT/Regulatory Systems|Regulatory Affairs|QA|Medical|Praxigent Admin",
  "owner_team": "specific team name",
  "reviewer_role": "role that reviews/approves",
  "estimated_effort_days": 2,
  "depends_on_task_titles": [],
  "change_control_required": true,
  "change_control_category": "Minor|Major|Critical",
  "step_by_step": [
    "Step 1: Log into Argus Safety as Administrator. Navigate to Configuration > Reporting Rules.",
    "Step 2: Search for rule ID 'EMA_NONSER_POST_MKT' in the HA = EMA, Type = Non-Serious filter.",
    "Step 3: Open the rule. In the Timeline field, change '90' to '45'. Confirm unit = Calendar Days.",
    "Step 4: Click Save. Verify the change is reflected in the rule summary.",
    "Step 5: Export the rule configuration as a PDF for change control evidence."
  ],
  "test_cases": [
    {{
      "test_id": "TC-001",
      "description": "Create a test non-serious ICSR for an EEA-sourced EU-authorized product in Argus QA environment. Verify the scheduled submission date is Day 0 + 45, not Day 0 + 90.",
      "expected_result": "ICSR scheduled for Day 45 submission to EudraVigilance",
      "pass_criteria": "Submission due date = Day 0 + 45 calendar days"
    }}
  ],
  "acceptance_criteria": "Clear measurable statement of done — e.g. Argus rule updated, validated in QA, promoted to PROD, change control closed",
  "evidence_required": [
    "Argus configuration screenshot before change",
    "Argus configuration screenshot after change",
    "Test case execution log with results",
    "QA approval sign-off",
    "Change control ticket number"
  ],
  "jira_labels": ["pharmacovigilance", "argus", "ema", "gvp-module-vi", "P1"],
  "regulatory_citation": "GVP Module VI Rev 3 §VI.B.6.2 — non-serious ADR reporting timeline"
}}
"""


CHANGE_CONTROL_PACK_PROMPT = """
Generate a complete GxP change control package for this set of compliance tasks.

Change: {change_title}
Regulation: {regulation_ref}
HA: {ha_code}
Effective date: {effective_date}
Tasks to implement: {tasks_summary}

Return JSON:
{{
  "impact_assessment": "3-4 sentences assessing GxP risk, patient safety impact, and regulatory compliance impact",
  "business_justification": "Why this change is required — cite regulation",
  "implementation_plan": "Ordered sequence: 1) Task A (owner, 3d) → 2) Task B (depends on A) (owner, 2d) → ...",
  "rollback_plan": "If implementation fails, steps to revert to previous state without compliance gap",
  "validation_strategy": "GAMP5 category, validation approach (IQ/OQ/PQ or UAT), test environment",
  "stakeholders": [
    {{"role": "Change Owner", "name": "PV Operations Lead", "responsibility": "Executes configuration changes"}},
    {{"role": "Change Reviewer", "name": "QA Manager", "responsibility": "Reviews and approves change package"}},
    {{"role": "QPPV", "name": "Qualified Person for PhV", "responsibility": "Final sign-off for regulatory impact"}},
    {{"role": "IT Systems", "name": "Safety Systems Administrator", "responsibility": "Argus/EV gateway changes"}}
  ]
}}
"""


# ─────────────────────────────────────────────────────────────────
# TASK GENERATOR
# ─────────────────────────────────────────────────────────────────

class TaskGenerator:
    """Generates actionable compliance tasks from gaps."""

    def __init__(self, api_key: str, db_conn=None):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.db = db_conn

    def _calculate_deadline(self, effective_date: str, lead_days: int) -> str:
        """Calculate task deadline = effective_date - lead_days."""
        try:
            eff = datetime.strptime(effective_date, "%Y-%m-%d").date()
            deadline = eff - timedelta(days=lead_days)
            return deadline.isoformat()
        except Exception:
            return effective_date  # Fallback

    def generate_tasks_for_gap(self, gap: dict, change: dict) -> list[ComplianceTask]:
        """Generate tasks for a single compliance gap."""

        prompt = TASK_GENERATION_PROMPT.format(
            change_id=change.get("change_id", ""),
            ha_code=change.get("ha_code", ""),
            change_title=change.get("title", ""),
            regulation_ref=change.get("regulation_ref", ""),
            effective_date=change.get("effective_date", ""),
            implementation_deadline=change.get("implementation_deadline", ""),
            gap_id=gap.get("gap_id", ""),
            system=gap.get("system", ""),
            gap_type=gap.get("gap_type", ""),
            current_state=gap.get("current_state", ""),
            required_state=gap.get("required_state", ""),
            gap_description=gap.get("gap_description", ""),
            regulatory_basis=gap.get("regulatory_basis", ""),
            priority=gap.get("priority", "P2"),
            gxp_impact=gap.get("gxp_impact", ""),
            validation_required=gap.get("validation_required", False),
            specific_change_instruction=gap.get("specific_change_instruction", "")
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=TASK_GENERATOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        try:
            tasks_data = json.loads(text)
        except json.JSONDecodeError:
            log.error(f"Task generator JSON parse error")
            return []

        # If single task dict (not list), wrap it
        if isinstance(tasks_data, dict):
            tasks_data = [tasks_data]

        tasks = []
        for i, t in enumerate(tasks_data):
            task_id = f"TASK-{gap['gap_id']}-{i+1:02d}"
            deadline = self._calculate_deadline(
                change.get("effective_date", ""),
                gap.get("implementation_lead_days", 30)
            )

            task = ComplianceTask(
                task_id=task_id,
                gap_id=gap.get("gap_id", ""),
                change_id=change.get("change_id", ""),
                ha_code=change.get("ha_code", ""),
                title=t.get("title", ""),
                description=t.get("description", ""),
                system=t.get("system", ""),
                task_type=t.get("task_type", "config_change"),
                owner_role=t.get("owner_role", "PV Operations"),
                owner_team=t.get("owner_team", "PV Operations"),
                reviewer_role=t.get("reviewer_role", "QA"),
                deadline=deadline,
                estimated_effort_days=t.get("estimated_effort_days", 2),
                priority=gap.get("priority", "P2"),
                depends_on=[],
                gxp_impact=gap.get("gxp_impact", ""),
                validation_required=gap.get("validation_required", False),
                change_control_required=t.get("change_control_required", True),
                change_control_category=t.get("change_control_category", "Minor"),
                step_by_step=t.get("step_by_step", []),
                test_cases=t.get("test_cases", []),
                acceptance_criteria=t.get("acceptance_criteria", ""),
                evidence_required=t.get("evidence_required", []),
                jira_summary=t.get("title", ""),
                jira_description=self._build_jira_body(t, gap, change),
                jira_labels=t.get("jira_labels", ["pharmacovigilance"]),
                regulatory_citation=t.get("regulatory_citation", change.get("regulation_ref", ""))
            )

            if self.db:
                self._store_task(task, t)
            tasks.append(task)

        return tasks

    def generate_all_tasks(self, change: dict, gaps: list[dict]) -> tuple[list[ComplianceTask], ChangeControlPack]:
        """Generate all tasks for all gaps from a single regulatory change."""
        all_tasks = []

        for gap in gaps:
            tasks = self.generate_tasks_for_gap(gap, change)
            all_tasks.extend(tasks)

        # Generate change control pack
        pack = self._generate_change_control_pack(change, all_tasks)

        log.info(f"Generated {len(all_tasks)} tasks for change {change.get('change_id')}")
        return all_tasks, pack

    def _generate_change_control_pack(self, change: dict,
                                       tasks: list[ComplianceTask]) -> ChangeControlPack:
        """Generate the GxP change control document."""
        tasks_summary = json.dumps([
            {"title": t.title, "system": t.system, "owner": t.owner_role,
             "effort_days": t.estimated_effort_days, "priority": t.priority}
            for t in tasks
        ], indent=2)

        prompt = CHANGE_CONTROL_PACK_PROMPT.format(
            change_title=change.get("title", ""),
            regulation_ref=change.get("regulation_ref", ""),
            ha_code=change.get("ha_code", ""),
            effective_date=change.get("effective_date", ""),
            tasks_summary=tasks_summary
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=TASK_GENERATOR_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        try:
            pack_data = json.loads(text)
        except json.JSONDecodeError:
            pack_data = {}

        pack = ChangeControlPack(
            pack_id=f"CCR-{change.get('change_id', 'UNKNOWN')}",
            change_id=change.get("change_id", ""),
            title=f"Change Control: {change.get('title', '')}",
            regulatory_citation=change.get("regulation_ref", ""),
            impact_assessment=pack_data.get("impact_assessment", ""),
            business_justification=pack_data.get("business_justification", ""),
            tasks=tasks,
            implementation_plan=pack_data.get("implementation_plan", ""),
            rollback_plan=pack_data.get("rollback_plan", ""),
            validation_strategy=pack_data.get("validation_strategy", ""),
            stakeholders=pack_data.get("stakeholders", []),
            review_deadline=(datetime.strptime(change.get("effective_date", "2026-12-31"), "%Y-%m-%d")
                             - timedelta(days=45)).strftime("%Y-%m-%d")
                            if change.get("effective_date") else "",
            implementation_deadline=change.get("implementation_deadline", ""),
            created_at=datetime.now(timezone.utc).isoformat()
        )

        if self.db:
            self._store_change_control_pack(pack)

        return pack

    def _build_jira_body(self, task_data: dict, gap: dict, change: dict) -> str:
        """Build a JIRA/ServiceNow ticket body."""
        steps = "\n".join(f"# {s}" for s in task_data.get("step_by_step", []))
        tests = "\n".join(
            f"* {tc['test_id']}: {tc['description']} → Expected: {tc['expected_result']}"
            for tc in task_data.get("test_cases", [])
        )
        evidence = "\n".join(f"* [ ] {e}" for e in task_data.get("evidence_required", []))

        return f"""h2. Regulatory basis
{change.get('regulation_ref', '')} — {change.get('title', '')}
Effective date: {change.get('effective_date', '')}

h2. What changed
{gap.get('gap_description', '')}
Current state: {gap.get('current_state', '')}
Required state: {gap.get('required_state', '')}

h2. Implementation steps
{steps}

h2. Test cases
{tests}

h2. Acceptance criteria
{task_data.get('acceptance_criteria', '')}

h2. Evidence required to close
{evidence}

h2. GxP impact
{gap.get('gxp_impact', '')} | Validation required: {gap.get('validation_required', False)}
Change control category: {task_data.get('change_control_category', 'Minor')}

h2. References
* Change record: {change.get('change_id', '')}
* Gap record: {gap.get('gap_id', '')}
* RegIntel regulatory citation: {task_data.get('regulatory_citation', '')}
"""

    def _store_task(self, task: ComplianceTask, raw_data: dict):
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO compliance_tasks (
                    task_id, gap_id, change_id, ha_code, title, description,
                    system, task_type, owner_role, owner_team, reviewer_role,
                    deadline, estimated_effort_days, priority, depends_on,
                    gxp_impact, validation_required, change_control_required,
                    change_control_category, step_by_step, test_cases,
                    acceptance_criteria, evidence_required,
                    jira_summary, jira_description, jira_labels,
                    regulatory_citation, status, created_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',NOW()
                )
            """, (
                task.task_id, task.gap_id, task.change_id, task.ha_code,
                task.title, task.description, task.system, task.task_type,
                task.owner_role, task.owner_team, task.reviewer_role,
                task.deadline, task.estimated_effort_days, task.priority,
                Json(task.depends_on), task.gxp_impact, task.validation_required,
                task.change_control_required, task.change_control_category,
                Json(task.step_by_step), Json(task.test_cases),
                task.acceptance_criteria, Json(task.evidence_required),
                task.jira_summary, task.jira_description, Json(task.jira_labels),
                task.regulatory_citation
            ))
        self.db.commit()

    def _store_change_control_pack(self, pack: ChangeControlPack):
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO change_control_packs (
                    pack_id, change_id, title, regulatory_citation,
                    impact_assessment, business_justification,
                    implementation_plan, rollback_plan, validation_strategy,
                    stakeholders, review_deadline, implementation_deadline,
                    status, created_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',NOW()
                )
            """, (
                pack.pack_id, pack.change_id, pack.title, pack.regulatory_citation,
                pack.impact_assessment, pack.business_justification,
                pack.implementation_plan, pack.rollback_plan, pack.validation_strategy,
                Json(pack.stakeholders), pack.review_deadline, pack.implementation_deadline
            ))
        self.db.commit()


TASKS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS compliance_tasks (
    task_id                     VARCHAR(80) PRIMARY KEY,
    gap_id                      VARCHAR(60) REFERENCES compliance_gaps(gap_id),
    change_id                   VARCHAR(50) REFERENCES regulatory_changes(change_id),
    ha_code                     VARCHAR(20),
    title                       TEXT NOT NULL,
    description                 TEXT,
    system                      VARCHAR(200),
    task_type                   VARCHAR(50),
    owner_role                  VARCHAR(100),
    owner_team                  VARCHAR(100),
    reviewer_role               VARCHAR(100),
    deadline                    DATE,
    estimated_effort_days       INTEGER DEFAULT 1,
    priority                    VARCHAR(5) DEFAULT 'P2',
    depends_on                  JSONB DEFAULT '[]',
    gxp_impact                  VARCHAR(50),
    validation_required         BOOLEAN DEFAULT FALSE,
    change_control_required     BOOLEAN DEFAULT TRUE,
    change_control_category     VARCHAR(20) DEFAULT 'Minor',
    step_by_step                JSONB DEFAULT '[]',
    test_cases                  JSONB DEFAULT '[]',
    acceptance_criteria         TEXT,
    evidence_required           JSONB DEFAULT '[]',
    jira_summary                TEXT,
    jira_description            TEXT,
    jira_labels                 JSONB DEFAULT '[]',
    jira_ticket_id              VARCHAR(50),
    regulatory_citation         TEXT,
    status                      VARCHAR(30) DEFAULT 'open',
    completed_at                TIMESTAMPTZ,
    completed_by                VARCHAR(100),
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS change_control_packs (
    pack_id                     VARCHAR(80) PRIMARY KEY,
    change_id                   VARCHAR(50) REFERENCES regulatory_changes(change_id),
    title                       TEXT,
    regulatory_citation         TEXT,
    impact_assessment           TEXT,
    business_justification      TEXT,
    implementation_plan         TEXT,
    rollback_plan               TEXT,
    validation_strategy         TEXT,
    stakeholders                JSONB DEFAULT '[]',
    review_deadline             DATE,
    implementation_deadline     DATE,
    status                      VARCHAR(30) DEFAULT 'draft',
    approved_by                 VARCHAR(100),
    approved_at                 TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tasks_gap      ON compliance_tasks(gap_id);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON compliance_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON compliance_tasks(deadline);
CREATE INDEX IF NOT EXISTS idx_tasks_owner    ON compliance_tasks(owner_role);
CREATE INDEX IF NOT EXISTS idx_tasks_status   ON compliance_tasks(status);
"""


def run_demo_pipeline(api_key: str):
    """
    Demo: run the complete gap → task → change control pack pipeline
    without a database, using sample data.
    """
    print("="*60)
    print("REGINTEL TASK GENERATOR — DEMO PIPELINE")
    print("="*60)

    generator = TaskGenerator(api_key=api_key, db_conn=None)

    # Sample change (EMA GVP Module VI timeline)
    sample_change = {
        "change_id": "CHG-20260607-EMA-001",
        "ha_code": "EMA",
        "title": "GVP Module VI Rev 3 — non-serious ICSR reporting window 90d → 45d",
        "regulation_ref": "GVP Module VI Rev 3 §VI.B.6.2",
        "effective_date": "2026-09-05",
        "implementation_deadline": "2026-08-06",
    }

    # Sample gaps from gap analyzer
    sample_gaps = [
        {
            "gap_id": "GAP-CHG-20260607-EMA-001-01",
            "ha_code": "EMA",
            "gap_type": "argus_rule",
            "system": "Oracle Argus Safety 8.4",
            "current_state": "Argus rule EMA_NONSER_POST_MKT: timeline_days = 90",
            "required_state": "timeline_days = 45 per GVP Module VI Rev 3 §VI.B.6.2",
            "gap_description": "Argus non-serious EMA reporting rule set to 90 days; regulation now requires 45 days",
            "regulatory_basis": "GVP Module VI Rev 3 §VI.B.6.2",
            "priority": "P1",
            "implementation_lead_days": 30,
            "validation_required": True,
            "gxp_impact": "GxP critical",
            "specific_change_instruction": "In Argus Safety Configuration > Reporting Rules, update EMA_NONSER_POST_MKT timeline from 90 to 45 calendar days. Requires change control and UAT."
        },
        {
            "gap_id": "GAP-CHG-20260607-EMA-001-02",
            "ha_code": "EMA",
            "gap_type": "ev_profile",
            "system": "EudraVigilance EVWEB / E2B gateway",
            "current_state": "EV export profile EV_PROD_90D: batch_window_days = 90",
            "required_state": "batch_window_days = 45",
            "gap_description": "EudraVigilance non-serious batch export profile configured for 90-day window; must be 45 days",
            "regulatory_basis": "GVP Module VI Rev 3 §VI.B.6.2",
            "priority": "P1",
            "implementation_lead_days": 30,
            "validation_required": True,
            "gxp_impact": "GxP critical",
            "specific_change_instruction": "Log into EudraVigilance EVWEB. Navigate to Profile Management > Export Profiles. Update EV_PROD_90D batch window to 45 days. Test with 3 sample non-serious ICSRs."
        },
        {
            "gap_id": "GAP-CHG-20260607-EMA-001-03",
            "ha_code": "EMA",
            "gap_type": "sop",
            "system": "Document Management System (QMS)",
            "current_state": "SOP-PV-004 v3.1 §4.2 states: 'Non-serious EMA ICSRs must be submitted within 90 calendar days'",
            "required_state": "SOP must state 45 calendar days, cite GVP Module VI Rev 3",
            "gap_description": "SOP-PV-004 references 90-day timeline; must be updated to 45 days with new regulation citation",
            "regulatory_basis": "GVP Module VI Rev 3 §VI.B.6.2",
            "priority": "P2",
            "implementation_lead_days": 45,
            "validation_required": False,
            "gxp_impact": "GxP significant",
            "specific_change_instruction": "In QMS, initiate SOP change request for SOP-PV-004. Update §4.2 paragraph 3: replace '90 calendar days' with '45 calendar days'. Update reference list to add GVP Module VI Rev 3. Route for QA review and issuance."
        },
        {
            "gap_id": "GAP-CHG-20260607-EMA-001-04",
            "ha_code": "EMA",
            "gap_type": "rod",
            "system": "RegIntel ROD (PostgreSQL)",
            "current_state": "ROD row: EMA post-mkt ICSR non-serious → timeline_days = 90",
            "required_state": "timeline_days = 45, regulation_ref updated to 'GVP Module VI Rev 3 §VI.B.6.2'",
            "gap_description": "RegIntel ROD still reflects 90-day obligation; all new case analyses will give wrong timeline until updated",
            "regulatory_basis": "GVP Module VI Rev 3 §VI.B.6.2",
            "priority": "P1",
            "implementation_lead_days": 5,
            "validation_required": False,
            "gxp_impact": "administrative",
            "specific_change_instruction": "UPDATE reporting_obligation SET timeline_days = 45, last_updated = NOW() WHERE ha_id = (SELECT ha_id FROM health_authority WHERE ha_code='EMA') AND report_name ILIKE '%non-serious%EEA%'; Verify with: SELECT report_name, timeline_days FROM reporting_obligation JOIN health_authority USING(ha_id) WHERE ha_code='EMA';"
        },
    ]

    print(f"\nGenerating tasks for {len(sample_gaps)} gaps...\n")

    all_tasks = []
    for gap in sample_gaps:
        print(f"  Processing gap: [{gap['priority']}] {gap['gap_description'][:60]}…")
        tasks = generator.generate_tasks_for_gap(gap, sample_change)
        all_tasks.extend(tasks)
        for t in tasks:
            print(f"    → Task: {t.title}")
            print(f"      Owner: {t.owner_role} | Deadline: {t.deadline} | GxP: {t.gxp_impact}")
            print(f"      Steps: {len(t.step_by_step)} | Tests: {len(t.test_cases)}")

    print(f"\nGenerating change control pack for {len(all_tasks)} tasks...")
    _, pack = generator.generate_all_tasks(sample_change, sample_gaps)

    print(f"\n{'='*60}")
    print(f"CHANGE CONTROL PACK: {pack.pack_id}")
    print(f"Impact assessment: {pack.impact_assessment[:200]}…")
    print(f"Implementation plan: {pack.implementation_plan[:200]}…")
    print(f"Validation strategy: {pack.validation_strategy[:200]}…")
    print(f"Stakeholders: {len(pack.stakeholders)}")
    print(f"Review deadline: {pack.review_deadline}")
    print(f"Implementation deadline: {pack.implementation_deadline}")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(all_tasks)} tasks generated across {len(sample_gaps)} gaps")
    p1 = sum(1 for t in all_tasks if t.priority == 'P1')
    p2 = sum(1 for t in all_tasks if t.priority == 'P2')
    p3 = sum(1 for t in all_tasks if t.priority == 'P3')
    print(f"  P1 (critical): {p1} | P2 (significant): {p2} | P3 (admin): {p3}")
    print(f"  GxP validation required: {sum(1 for t in all_tasks if t.validation_required)} tasks")
    print(f"  Change control required: {sum(1 for t in all_tasks if t.change_control_required)} tasks")

    return all_tasks, pack


if __name__ == "__main__":
    import os
    API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    run_demo_pipeline(API_KEY)
