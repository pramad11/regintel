"""
REGINTEL — DELIVERY LAYER + PIPELINE ORCHESTRATOR
===================================================
Routes generated tasks to external systems and assembles
the full human-readable change management report.

Delivery targets:
  - JIRA / ServiceNow (ticket creation via API)
  - Slack / Teams (P1 alerts)
  - Email (change control package)
  - PDF report (full change pack for QA review)
  - RegIntel dashboard (status updates)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional
import anthropic
import httpx

log = logging.getLogger("delivery_layer")


# ─────────────────────────────────────────────────────────────────
# SLACK NOTIFIER
# ─────────────────────────────────────────────────────────────────

class SlackNotifier:
    def __init__(self, webhook_url: str):
        self.webhook = webhook_url

    async def send_change_alert(self, change: dict, tasks: list, pack) -> bool:
        p1_tasks = [t for t in tasks if t.priority == "P1"]
        color = "#E24B4A" if p1_tasks else "#EF9F27"

        blocks = [
            {"type": "header", "text": {"type": "plain_text",
             "text": f"⚠️ Regulatory Change Detected — {change['ha_code']}"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Change:*\n{change['title']}"},
                {"type": "mrkdwn", "text": f"*Regulation:*\n{change['regulation_ref']}"},
                {"type": "mrkdwn", "text": f"*Effective date:*\n{change['effective_date']}"},
                {"type": "mrkdwn", "text": f"*Tasks generated:*\n{len(tasks)} ({len(p1_tasks)} P1)"},
            ]},
        ]

        if p1_tasks:
            task_list = "\n".join(f"• {t.title}" for t in p1_tasks[:3])
            blocks.append({"type": "section",
                "text": {"type": "mrkdwn",
                         "text": f"*P1 Tasks requiring immediate action:*\n{task_list}"}})

        blocks.append({"type": "section",
            "text": {"type": "mrkdwn",
                     "text": f"*Implementation deadline:* {change.get('implementation_deadline', 'TBD')}\n"
                             f"*Change pack:* {pack.pack_id}"}})

        payload = {"attachments": [{"color": color, "blocks": blocks}]}

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook, json=payload)
                return resp.status_code == 200
        except Exception as e:
            log.error(f"Slack notification failed: {e}")
            return False


# ─────────────────────────────────────────────────────────────────
# JIRA CONNECTOR
# ─────────────────────────────────────────────────────────────────

class JiraConnector:
    def __init__(self, base_url: str, email: str, api_token: str, project_key: str):
        self.base_url = base_url.rstrip("/")
        self.auth = (email, api_token)
        self.project_key = project_key

    def create_ticket(self, task) -> Optional[str]:
        """Create a JIRA ticket for a compliance task. Returns ticket ID."""
        priority_map = {"P1": "Highest", "P2": "High", "P3": "Medium"}

        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": f"[RegIntel] {task.jira_summary}",
                "description": {
                    "type": "doc", "version": 1,
                    "content": [{"type": "paragraph",
                                 "content": [{"type": "text", "text": task.jira_description}]}]
                },
                "issuetype": {"name": "Task"},
                "priority": {"name": priority_map.get(task.priority, "Medium")},
                "labels": task.jira_labels,
                "duedate": task.deadline,
                "customfield_10001": task.regulatory_citation,  # adjust field ID per JIRA config
            }
        }

        try:
            resp = httpx.post(
                f"{self.base_url}/rest/api/3/issue",
                json=payload, auth=self.auth,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 201:
                ticket_id = resp.json()["key"]
                log.info(f"JIRA ticket created: {ticket_id} for task {task.task_id}")
                return ticket_id
            else:
                log.error(f"JIRA creation failed: {resp.status_code} {resp.text[:200]}")
                return None
        except Exception as e:
            log.error(f"JIRA connector error: {e}")
            return None

    def create_epic(self, change: dict, pack) -> Optional[str]:
        """Create a JIRA epic for the regulatory change."""
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": f"[RegIntel] {change['ha_code']}: {change['title'][:80]}",
                "description": {"type": "doc", "version": 1,
                    "content": [{"type": "paragraph",
                        "content": [{"type": "text",
                            "text": f"Regulatory change: {change['regulation_ref']}\n"
                                    f"Effective: {change['effective_date']}\n"
                                    f"Change pack: {pack.pack_id}\n\n"
                                    f"Impact: {pack.impact_assessment}"}]}]},
                "issuetype": {"name": "Epic"},
                "labels": ["pharmacovigilance", "regulatory-change", change["ha_code"].lower()],
                "duedate": change.get("implementation_deadline", ""),
            }
        }
        try:
            resp = httpx.post(f"{self.base_url}/rest/api/3/issue",
                              json=payload, auth=self.auth,
                              headers={"Content-Type": "application/json"})
            if resp.status_code == 201:
                return resp.json()["key"]
        except Exception as e:
            log.error(f"JIRA epic creation failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────
# CHANGE PACK REPORT GENERATOR
# ─────────────────────────────────────────────────────────────────

class ChangePackReporter:
    """Generates human-readable change control document."""

    def generate_markdown(self, change: dict, gaps: list[dict],
                           tasks, pack) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        p1 = [t for t in tasks if t.priority == "P1"]
        p2 = [t for t in tasks if t.priority == "P2"]
        p3 = [t for t in tasks if t.priority == "P3"]

        md = f"""# Change Control Package — {pack.pack_id}
**Generated:** {now}
**Status:** Draft — Pending QA Review

---

## 1. Change Summary

| Field | Detail |
|---|---|
| **Change ID** | {change['change_id']} |
| **Health Authority** | {change['ha_code']} |
| **Change type** | {change.get('change_type', '—')} |
| **Regulation** | {change['regulation_ref']} |
| **Effective date** | {change['effective_date']} |
| **Implementation deadline** | {change.get('implementation_deadline', '—')} |
| **Urgency** | {change.get('urgency', '—').upper()} |

**Title:** {change['title']}

**Description:**
{change.get('description', '')}

---

## 2. Impact Assessment

{pack.impact_assessment}

**Business justification:**
{pack.business_justification}

---

## 3. Compliance Gaps Identified ({len(gaps)})

"""
        for gap in gaps:
            md += f"""### Gap: {gap.get('gap_id', '')} — {gap.get('system', '')}
- **Priority:** {gap.get('priority', '')} | **GxP impact:** {gap.get('gxp_impact', '')}
- **Current state:** {gap.get('current_state', '')}
- **Required state:** {gap.get('required_state', '')}
- **Regulatory basis:** {gap.get('regulatory_basis', '')}

"""

        md += f"""---

## 4. Tasks ({len(tasks)} total — {len(p1)} P1 · {len(p2)} P2 · {len(p3)} P3)

"""
        for task in sorted(tasks, key=lambda t: t.priority):
            steps_md = "\n".join(f"   {i+1}. {s}" for i, s in enumerate(task.step_by_step))
            tests_md = "\n".join(f"   - {tc['test_id']}: {tc['description']}"
                                  for tc in task.test_cases)
            evidence_md = "\n".join(f"   - [ ] {e}" for e in task.evidence_required)

            md += f"""### [{task.priority}] {task.title}

| Field | Detail |
|---|---|
| **Task ID** | {task.task_id} |
| **System** | {task.system} |
| **Owner** | {task.owner_role} ({task.owner_team}) |
| **Reviewer** | {task.reviewer_role} |
| **Deadline** | {task.deadline} |
| **Effort** | ~{task.estimated_effort_days} day(s) |
| **GxP impact** | {task.gxp_impact} |
| **Validation** | {'Required' if task.validation_required else 'Not required'} |
| **Change control** | {task.change_control_category if task.change_control_required else 'Not required'} |

**Description:** {task.description}

**Implementation steps:**
{steps_md}

**Test cases:**
{tests_md}

**Acceptance criteria:** {task.acceptance_criteria}

**Evidence required:**
{evidence_md}

**Regulatory citation:** {task.regulatory_citation}

---
"""

        md += f"""
## 5. Implementation Plan

{pack.implementation_plan}

## 6. Rollback Plan

{pack.rollback_plan}

## 7. Validation Strategy

{pack.validation_strategy}

## 8. Stakeholders

| Role | Responsibility |
|---|---|
"""
        for s in pack.stakeholders:
            md += f"| {s.get('role', '')} — {s.get('name', '')} | {s.get('responsibility', '')} |\n"

        md += f"""
---

## 9. Approval

| Action | Name | Date | Signature |
|---|---|---|---|
| Prepared by | PV Operations | {now[:10]} | |
| Reviewed by QA | | | |
| QPPV approval | | | |
| IT Systems sign-off | | | |

---
*Generated by Praxigent RegIntel Change Management Platform*
*Regulatory change source: {change.get('source_url', '')}*
"""
        return md

    def generate_html(self, change: dict, gaps: list[dict], tasks, pack) -> str:
        """Generate styled HTML version of the change pack."""
        md = self.generate_markdown(change, gaps, tasks, pack)
        # Simple markdown → HTML conversion
        html = md.replace("---", "<hr/>")
        html = "<br/>".join(html.split("\n"))
        return f"""<!DOCTYPE html>
<html><head>
<meta charset="UTF-8"/>
<title>{pack.pack_id}</title>
<style>
body{{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;color:#1A1A18;line-height:1.6;}}
h1{{color:#03203C;border-bottom:2px solid #1D9E75;padding-bottom:8px;}}
h2{{color:#042C53;margin-top:32px;}}
h3{{color:#0A5F9A;}}
table{{width:100%;border-collapse:collapse;margin:12px 0;}}
th{{background:#042C53;color:#B5D4F4;padding:8px 12px;text-align:left;font-size:12px;}}
td{{padding:8px 12px;border-bottom:1px solid #EEE9E0;font-size:13px;}}
code{{background:#F0EDE6;padding:2px 6px;border-radius:4px;font-size:12px;}}
hr{{border:none;border-top:1px solid #EEE9E0;margin:24px 0;}}
.p1{{color:#A32D2D;font-weight:bold;}}
.p2{{color:#854F0B;font-weight:bold;}}
</style>
</head><body>
{html}
</body></html>"""


# ─────────────────────────────────────────────────────────────────
# MAIN PIPELINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────

class RegIntelChangePipeline:
    """
    End-to-end pipeline:
    HA change detected → classified → gaps found → tasks generated → delivered

    Usage:
        pipeline = RegIntelChangePipeline(api_key, db_conn, config)
        result = pipeline.run(change_id="CHG-20260607-EMA-001", sponsor_id="verastem")
    """

    def __init__(self, api_key: str, db_conn=None, config: dict = None):
        from feed.ha_feed_engine import HAFeedEngine
        from gap.gap_analyzer import GapAnalyzer
        from tasks.task_generator import TaskGenerator

        self.api_key = api_key
        self.db = db_conn
        self.config = config or {}

        self.feed_engine = HAFeedEngine(db_conn, api_key)
        self.gap_analyzer = GapAnalyzer(api_key, db_conn)
        self.task_generator = TaskGenerator(api_key, db_conn)
        self.reporter = ChangePackReporter()

        # Optional delivery targets
        if self.config.get("slack_webhook"):
            self.slack = SlackNotifier(self.config["slack_webhook"])
        if self.config.get("jira_url"):
            self.jira = JiraConnector(
                self.config["jira_url"],
                self.config.get("jira_email", ""),
                self.config.get("jira_token", ""),
                self.config.get("jira_project", "PV")
            )

    def run_from_change(self, change: dict, sponsor_id: str,
                         output_dir: str = "/tmp") -> dict:
        """
        Run gap analysis and task generation for a pre-classified change.
        Used when a change is already in the DB.
        """
        log.info(f"Running change pipeline for {change['change_id']}")

        # 1. Gap analysis
        gaps = self.gap_analyzer.analyze(change, sponsor_id)
        log.info(f"  Found {len(gaps)} gaps")

        # 2. Task generation
        from tasks.task_generator import ComplianceTask
        tasks, pack = self.task_generator.generate_all_tasks(
            change,
            [{"gap_id": g.gap_id, "ha_code": g.ha_code, "gap_type": g.gap_type,
              "system": g.system, "current_state": g.current_state,
              "required_state": g.required_state, "gap_description": g.gap_description,
              "regulatory_basis": g.regulatory_basis, "priority": g.priority,
              "implementation_lead_days": g.implementation_lead_days,
              "validation_required": g.validation_required,
              "gxp_impact": g.gxp_impact, "specific_change_instruction": ""}
             for g in gaps]
        )
        log.info(f"  Generated {len(tasks)} tasks")

        # 3. Generate report
        gaps_dicts = [{"gap_id": g.gap_id, "system": g.system,
                        "priority": g.priority, "gxp_impact": g.gxp_impact,
                        "current_state": g.current_state, "required_state": g.required_state,
                        "regulatory_basis": g.regulatory_basis,
                        "gap_description": g.gap_description} for g in gaps]
        report_md = self.reporter.generate_markdown(change, gaps_dicts, tasks, pack)

        report_path = f"{output_dir}/{pack.pack_id}.md"
        with open(report_path, "w") as f:
            f.write(report_md)
        log.info(f"  Report saved: {report_path}")

        return {
            "change_id": change["change_id"],
            "gaps": len(gaps),
            "tasks": len(tasks),
            "pack_id": pack.pack_id,
            "report_path": report_path,
            "p1_tasks": [t.title for t in tasks if t.priority == "P1"],
            "p2_tasks": [t.title for t in tasks if t.priority == "P2"],
            "p3_tasks": [t.title for t in tasks if t.priority == "P3"],
        }

    def run_demo(self) -> str:
        """Run the full pipeline in demo mode (no DB needed)."""
        from gap.gap_analyzer import GapAnalyzer
        from tasks.task_generator import run_demo_pipeline

        print("\n" + "="*60)
        print("REGINTEL CHANGE MANAGEMENT PIPELINE — FULL DEMO")
        print("="*60)
        print("\nStep 1: Running gap analyzer...")

        analyzer = GapAnalyzer(api_key=self.api_key, db_conn=None)
        gaps = analyzer.run_demo_analysis()
        print(f"  → {len(gaps)} gaps identified\n")

        print("Step 2: Running task generator...")
        tasks, pack = run_demo_pipeline(self.api_key)

        print(f"\nStep 3: Generating change control report...")
        sample_change = {
            "change_id": "CHG-20260607-EMA-001",
            "ha_code": "EMA",
            "change_type": "timeline_change",
            "title": "GVP Module VI Rev 3 — non-serious ICSR reporting window 90d → 45d",
            "description": "EMA amended §VI.B.6.2: non-serious ADR reporting from 90 to 45 calendar days",
            "regulation_ref": "GVP Module VI Rev 3 §VI.B.6.2",
            "effective_date": "2026-09-05",
            "implementation_deadline": "2026-08-06",
            "urgency": "high",
            "source_url": "https://www.ema.europa.eu/en/documents/scientific-guideline/gvp-module-vi-rev-3"
        }

        report = self.reporter.generate_markdown(sample_change, gaps, tasks, pack)
        report_path = "/tmp/CCR-CHG-20260607-EMA-001.md"
        with open(report_path, "w") as f:
            f.write(report)

        print(f"  → Report saved: {report_path}")
        print(f"\n{'='*60}")
        print(f"PIPELINE COMPLETE")
        print(f"  Change: CHG-20260607-EMA-001")
        print(f"  Gaps:   {len(gaps)}")
        print(f"  Tasks:  {len(tasks)}")
        print(f"  Pack:   {pack.pack_id}")
        print(f"  Report: {report_path}")
        print(f"{'='*60}\n")

        return report_path


if __name__ == "__main__":
    API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    pipeline = RegIntelChangePipeline(api_key=API_KEY)
    pipeline.run_demo()
