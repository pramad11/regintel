"""
REGINTEL — GAP ANALYZER
========================
Compares each regulatory change against current system configuration
(Argus Safety rules, E2B profiles, SOPs, RegIntel ROD) and identifies
every gap that must be closed before the regulation's effective date.

Input:  ClassifiedChange + SystemConfiguration
Output: List[ComplianceGap] → fed to TaskGenerator
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional
import anthropic
import psycopg2
from psycopg2.extras import Json, RealDictCursor

log = logging.getLogger("gap_analyzer")


# ─────────────────────────────────────────────────────────────────
# SYSTEM CONFIGURATION MODEL
# ─────────────────────────────────────────────────────────────────

@dataclass
class ArgusReportingRule:
    """Represents a single reporting rule configured in Argus Safety."""
    rule_id: str
    ha_code: str
    report_type: str           # 'expedited_7d' | 'expedited_15d' | 'periodic_90d' etc.
    product_type: str
    phase: str
    timeline_days: int
    format: str                # 'E2B_R3' | 'MedWatch_3500A' | 'J_ICSR' etc.
    gateway_profile: str
    is_active: bool
    last_validated_date: str
    notes: str = ""


@dataclass
class SystemConfiguration:
    """
    Snapshot of current PV system configuration for a sponsor.
    In production this would be pulled from Argus API / config DB.
    """
    sponsor_id: str
    argus_reporting_rules: list[ArgusReportingRule]
    ev_export_profiles: list[dict]     # EudraVigilance export profiles
    active_sops: list[dict]            # PV SOPs with version and content refs
    rod_snapshot: list[dict]           # Current RegIntel ROD entries
    active_has: list[str]              # HA codes currently configured
    products: list[dict]               # Active product profiles
    last_config_review: str


@dataclass
class ComplianceGap:
    """A single gap between current configuration and new regulatory requirement."""
    gap_id: str
    change_id: str
    ha_code: str
    gap_type: str              # argus_rule | ev_profile | sop | rod | gateway |
                               # training | submission_format | new_ha
    system: str                # Which system has the gap
    current_state: str         # What is configured now
    required_state: str        # What the regulation requires
    gap_description: str       # Clear description of the gap
    regulatory_basis: str      # Which article of which regulation requires this
    priority: str              # P1 | P2 | P3
    implementation_lead_days: int  # Days needed to implement (for deadline calc)
    validation_required: bool  # Does this require GxP validation?
    gxp_impact: str            # 'GxP critical' | 'GxP significant' | 'administrative'
    affected_products: list[str]
    affected_phases: list[str]


# ─────────────────────────────────────────────────────────────────
# SYSTEM CONFIG LOADER (reads from DB / Argus API)
# ─────────────────────────────────────────────────────────────────

class SystemConfigLoader:
    """Loads current system configuration from database."""

    def __init__(self, db_conn):
        self.db = db_conn

    def load_argus_rules(self, sponsor_id: str) -> list[ArgusReportingRule]:
        """Load current Argus Safety reporting rules."""
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM argus_reporting_rules
                WHERE sponsor_id = %s AND is_active = true
                ORDER BY ha_code, report_type
            """, (sponsor_id,))
            rows = cur.fetchall()

        return [ArgusReportingRule(
            rule_id=r["rule_id"],
            ha_code=r["ha_code"],
            report_type=r["report_type"],
            product_type=r["product_type"],
            phase=r["phase"],
            timeline_days=r["timeline_days"],
            format=r["format"],
            gateway_profile=r["gateway_profile"],
            is_active=r["is_active"],
            last_validated_date=str(r.get("last_validated_date", "")),
            notes=r.get("notes", "")
        ) for r in rows]

    def load_rod_snapshot(self) -> list[dict]:
        """Load current RegIntel ROD entries."""
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT ro.*, ha.ha_code, ha.ha_name
                FROM reporting_obligation ro
                JOIN health_authority ha ON ha.ha_id = ro.ha_id
                WHERE ro.active = true
                ORDER BY ha.ha_code, ro.report_name
            """)
            return [dict(r) for r in cur.fetchall()]

    def load_active_sops(self, sponsor_id: str) -> list[dict]:
        """Load active PV SOPs."""
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT sop_id, sop_number, title, version, effective_date,
                       content_summary, ha_codes_covered, review_due_date
                FROM pv_sops
                WHERE sponsor_id = %s AND status = 'active'
            """, (sponsor_id,))
            return [dict(r) for r in cur.fetchall()]

    def build_config_snapshot(self, sponsor_id: str) -> dict:
        """Build a JSON snapshot of current configuration for the gap analyzer."""
        argus_rules = self.load_argus_rules(sponsor_id)
        rod = self.load_rod_snapshot()
        sops = self.load_active_sops(sponsor_id)

        return {
            "sponsor_id": sponsor_id,
            "argus_rules": [
                {
                    "rule_id": r.rule_id,
                    "ha": r.ha_code,
                    "type": r.report_type,
                    "timeline_days": r.timeline_days,
                    "format": r.format,
                    "gateway": r.gateway_profile,
                    "last_validated": r.last_validated_date
                }
                for r in argus_rules
            ],
            "rod_entries": [
                {
                    "ha": r["ha_code"],
                    "report_name": r["report_name"],
                    "timeline_days": r["timeline_days"],
                    "format": r.get("report_format", []),
                    "regulation_ref": r.get("conditions_text", "")
                }
                for r in rod
            ],
            "active_sops": [
                {
                    "sop_number": s["sop_number"],
                    "title": s["title"],
                    "version": s["version"],
                    "ha_scope": s.get("ha_codes_covered", []),
                    "review_due": str(s.get("review_due_date", ""))
                }
                for s in sops
            ],
            "ev_profiles": [],  # Populated from Argus API or manual entry
        }


# ─────────────────────────────────────────────────────────────────
# GAP ANALYZER (Claude API)
# ─────────────────────────────────────────────────────────────────

GAP_ANALYZER_SYSTEM = """You are a senior pharmacovigilance compliance consultant
specializing in safety database systems (Oracle Argus Safety, ARISg, LSMV),
ICH E2B R3, GVP compliance, and GxP change management.

Your job is to analyze a regulatory change and compare it against the current
system configuration of a pharmaceutical sponsor. You must identify every gap —
every place where the current configuration does not yet comply with the new
regulation — with surgical precision.

Be specific: name the exact Argus rule, SOP section, E2B field, or ROD row that
needs to change. Cite the exact regulation article that requires it.
Assess GxP impact honestly — not everything requires full GAMP5 validation."""


GAP_ANALYSIS_PROMPT = """
A regulatory change has been classified. Compare it against current system
configuration and identify all compliance gaps.

═══ REGULATORY CHANGE ═══
HA: {ha_code}
Change type: {change_type}
Title: {title}
Description: {description}
Regulation reference: {regulation_ref}
Affected product types: {affected_product_types}
Affected phases: {affected_phases}
Effective date: {effective_date}
Implementation deadline: {implementation_deadline}
Systems flagged: {systems_requiring_change}

═══ CURRENT SYSTEM CONFIGURATION ═══
{config_snapshot}

═══ TASK ═══
Identify every compliance gap. For each gap, specify:
1. Which system has the gap
2. What is currently configured (current state)
3. What the regulation requires (required state)
4. How to close the gap (specific change description)
5. Which regulation article requires this
6. Priority and GxP impact

Return ONLY a valid JSON array. Each element:
{{
  "gap_type": "argus_rule|ev_profile|sop|rod|gateway|training|submission_format|new_ha|other",
  "system": "exact system name",
  "current_state": "what is configured now — be specific",
  "required_state": "what the regulation requires — cite the article",
  "gap_description": "clear description of the gap in 1-2 sentences",
  "regulatory_basis": "exact regulation article e.g. GVP Module VI Rev 3 §VI.B.6.2",
  "priority": "P1|P2|P3",
  "implementation_lead_days": 30,
  "validation_required": true,
  "gxp_impact": "GxP critical|GxP significant|administrative",
  "affected_products": ["all" or specific product types],
  "affected_phases": ["all" or specific phases],
  "specific_change_instruction": "exactly what to do: e.g. In Argus Safety, navigate to Configuration > Reporting Rules > EMA_NONSER_POST_MKT. Change Timeline Days from 90 to 45. Save and raise change control."
}}

If no gaps exist (system already compliant), return an empty array [].
Prioritize: P1 = must fix before effective date (GxP critical, direct compliance impact),
P2 = should fix before effective date (significant but not immediately blocking),
P3 = nice to have / documentation (administrative, no direct submission impact).
"""


class GapAnalyzer:
    """Core gap analysis engine."""

    def __init__(self, api_key: str, db_conn):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.config_loader = SystemConfigLoader(db_conn)
        self.db = db_conn

    def analyze(self, change: dict, sponsor_id: str) -> list[ComplianceGap]:
        """
        Analyze a regulatory change against sponsor's current configuration.
        Returns list of compliance gaps.
        """
        # Load current system config
        config = self.config_loader.build_config_snapshot(sponsor_id)
        config_json = json.dumps(config, indent=2, default=str)

        # Build prompt
        prompt = GAP_ANALYSIS_PROMPT.format(
            ha_code=change.get("ha_code", ""),
            change_type=change.get("change_type", ""),
            title=change.get("title", ""),
            description=change.get("description", ""),
            regulation_ref=change.get("regulation_ref", ""),
            affected_product_types=json.dumps(change.get("affected_product_types", ["all"])),
            affected_phases=json.dumps(change.get("affected_phases", ["all"])),
            effective_date=change.get("effective_date", ""),
            implementation_deadline=change.get("implementation_deadline", ""),
            systems_requiring_change=json.dumps(change.get("systems_requiring_change", []), indent=2),
            config_snapshot=config_json[:3000]  # Limit for token budget
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=GAP_ANALYZER_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        try:
            gaps_data = json.loads(text)
        except json.JSONDecodeError:
            log.error(f"Gap analyzer JSON parse error. Text: {text[:500]}")
            return []

        # Convert to ComplianceGap objects and store
        gaps = []
        for i, g in enumerate(gaps_data):
            gap = ComplianceGap(
                gap_id=f"GAP-{change['change_id']}-{i+1:02d}",
                change_id=change["change_id"],
                ha_code=change["ha_code"],
                gap_type=g.get("gap_type", "other"),
                system=g.get("system", ""),
                current_state=g.get("current_state", ""),
                required_state=g.get("required_state", ""),
                gap_description=g.get("gap_description", ""),
                regulatory_basis=g.get("regulatory_basis", ""),
                priority=g.get("priority", "P2"),
                implementation_lead_days=g.get("implementation_lead_days", 30),
                validation_required=g.get("validation_required", False),
                gxp_impact=g.get("gxp_impact", "administrative"),
                affected_products=g.get("affected_products", ["all"]),
                affected_phases=g.get("affected_phases", ["all"]),
            )
            # Store specific_change_instruction in DB
            self._store_gap(gap, g.get("specific_change_instruction", ""))
            gaps.append(gap)

        log.info(f"Gap analysis complete: {len(gaps)} gaps found for change {change['change_id']}")
        return gaps

    def _store_gap(self, gap: ComplianceGap, specific_instruction: str):
        """Store gap record in database."""
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO compliance_gaps (
                    gap_id, change_id, ha_code, gap_type, system,
                    current_state, required_state, gap_description,
                    regulatory_basis, priority, implementation_lead_days,
                    validation_required, gxp_impact, affected_products,
                    affected_phases, specific_change_instruction,
                    status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, 'open', NOW()
                )
            """, (
                gap.gap_id, gap.change_id, gap.ha_code, gap.gap_type,
                gap.system, gap.current_state, gap.required_state,
                gap.gap_description, gap.regulatory_basis, gap.priority,
                gap.implementation_lead_days, gap.validation_required,
                gap.gxp_impact, Json(gap.affected_products),
                Json(gap.affected_phases), specific_instruction
            ))
        self.db.commit()

    def run_demo_analysis(self, change_id: str = None) -> list[dict]:
        """Demo mode: run gap analysis without DB, using sample config."""

        # Sample regulatory change: EMA GVP Module VI non-serious timeline
        sample_change = {
            "change_id": change_id or "CHG-20260607-EMA-001",
            "ha_code": "EMA",
            "change_type": "timeline_change",
            "title": "GVP Module VI Rev 3 — non-serious ICSR reporting window 90d → 45d",
            "description": "EMA amended GVP Module VI §VI.B.6.2: non-serious ADR reporting from EEA sources reduced from 90 to 45 calendar days. Affects all post-marketing products with EU marketing authorization.",
            "regulation_ref": "GVP Module VI Rev 3 §VI.B.6.2",
            "affected_product_types": ["all"],
            "affected_phases": ["marketed"],
            "effective_date": "2026-09-05",
            "implementation_deadline": "2026-08-06",
            "systems_requiring_change": [
                {"system": "Oracle Argus Safety", "change_description": "Update EMA non-serious reporting rule timeline", "priority": "P1"},
                {"system": "EudraVigilance", "change_description": "Update E2B export batch window", "priority": "P1"},
                {"system": "SOP", "change_description": "Update SOP-004 §4.2", "priority": "P2"}
            ]
        }

        # Sample current config snapshot
        sample_config = {
            "sponsor_id": "verastem-oncology",
            "argus_rules": [
                {"rule_id": "EMA_NONSER_POST_MKT", "ha": "EMA", "type": "non_serious_postmkt",
                 "timeline_days": 90, "format": "E2B_R3", "gateway": "EV_EVWEB_PROD",
                 "last_validated": "2024-01-15"},
                {"rule_id": "EMA_SUSAR_CT", "ha": "EMA", "type": "susar_ct",
                 "timeline_days": 7, "format": "E2B_R3", "gateway": "CTIS_EVCTM",
                 "last_validated": "2024-01-15"},
                {"rule_id": "FDA_IND_7DAY", "ha": "FDA", "type": "expedited_7d",
                 "timeline_days": 7, "format": "E2B_R3", "gateway": "FDA_ESM",
                 "last_validated": "2024-06-01"},
            ],
            "rod_entries": [
                {"ha": "EMA", "report_name": "Post-mkt ICSR — non-serious (EEA)",
                 "timeline_days": 90, "format": ["E2B_R3"],
                 "regulation_ref": "Dir 2001/83/EC Art.107a(2) · GVP Module VI Rev 2 §VI.B.6.3"},
            ],
            "active_sops": [
                {"sop_number": "SOP-PV-004", "title": "ICSR Reporting Timelines",
                 "version": "3.1", "ha_scope": ["FDA", "EMA", "MHRA", "PMDA"],
                 "review_due": "2026-12-01"},
            ],
            "ev_profiles": [
                {"profile_id": "EV_PROD_90D", "type": "non_serious_batch",
                 "batch_window_days": 90, "format": "E2B_R3_v2.1",
                 "receiver": "EV_GATEWAY_EMA"}
            ]
        }

        # Call Claude for gap analysis
        prompt = GAP_ANALYSIS_PROMPT.format(
            ha_code=sample_change["ha_code"],
            change_type=sample_change["change_type"],
            title=sample_change["title"],
            description=sample_change["description"],
            regulation_ref=sample_change["regulation_ref"],
            affected_product_types=json.dumps(sample_change["affected_product_types"]),
            affected_phases=json.dumps(sample_change["affected_phases"]),
            effective_date=sample_change["effective_date"],
            implementation_deadline=sample_change["implementation_deadline"],
            systems_requiring_change=json.dumps(sample_change["systems_requiring_change"], indent=2),
            config_snapshot=json.dumps(sample_config, indent=2)
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=3000,
            system=GAP_ANALYZER_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        return json.loads(text)


GAPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS compliance_gaps (
    gap_id                      VARCHAR(60) PRIMARY KEY,
    change_id                   VARCHAR(50) REFERENCES regulatory_changes(change_id),
    ha_code                     VARCHAR(20),
    gap_type                    VARCHAR(50),
    system                      VARCHAR(200),
    current_state               TEXT,
    required_state              TEXT,
    gap_description             TEXT,
    regulatory_basis            TEXT,
    priority                    VARCHAR(5) DEFAULT 'P2',
    implementation_lead_days    INTEGER DEFAULT 30,
    validation_required         BOOLEAN DEFAULT FALSE,
    gxp_impact                  VARCHAR(50),
    affected_products           JSONB,
    affected_phases             JSONB,
    specific_change_instruction TEXT,
    status                      VARCHAR(30) DEFAULT 'open',
    task_id                     VARCHAR(60),
    closed_at                   TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gaps_change   ON compliance_gaps(change_id);
CREATE INDEX IF NOT EXISTS idx_gaps_priority ON compliance_gaps(priority);
CREATE INDEX IF NOT EXISTS idx_gaps_status   ON compliance_gaps(status);
CREATE INDEX IF NOT EXISTS idx_gaps_system   ON compliance_gaps(system);
"""


if __name__ == "__main__":
    import os

    API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    analyzer = GapAnalyzer(api_key=API_KEY, db_conn=None)

    print("Running demo gap analysis (no DB required)...")
    gaps = analyzer.run_demo_analysis()

    print(f"\n{'='*60}")
    print(f"Gaps found: {len(gaps)}")
    for i, g in enumerate(gaps, 1):
        print(f"\n  [{g['priority']}] Gap {i}: {g['gap_description']}")
        print(f"    System: {g['system']}")
        print(f"    Current: {g['current_state']}")
        print(f"    Required: {g['required_state']}")
        print(f"    GxP: {g['gxp_impact']} | Validation: {g['validation_required']}")
        print(f"    Instruction: {g['specific_change_instruction'][:120]}…")
