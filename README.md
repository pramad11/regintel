# RegIntel Change Management Platform

**Praxigent RegIntel — Regulatory Change → Actionable Compliance Tasks**

Translates global regulatory changes into precise, system-specific,
GxP-compliant compliance tasks — automatically.

---

## Architecture

```
HA websites (187 sources)
        ↓
   ha_feed_engine.py        — scrape, hash, detect change
        ↓
   ChangeClassifier          — Claude AI: what changed, which ROD rows, urgency
        ↓
   gap_analyzer.py          — compare change vs current Argus/SOP/ROD config
        ↓
   task_generator.py        — Claude AI: generate step-by-step tasks + test cases
        ↓
   pipeline.py              — assemble change control pack, route to JIRA/Slack
        ↓
   RegIntel dashboard       — task tracker, deadline calendar, audit trail
```

---

## Quick start

```bash
# 1. Install
pip install -r requirements.txt

# 2. Set environment
export ANTHROPIC_API_KEY=sk-ant-...
export DATABASE_URL=postgresql://localhost/regintel

# 3. Create schema
psql $DATABASE_URL < schema/change_mgmt_schema.sql

# 4. Run feed engine (detect changes across all HAs)
cd feed && python ha_feed_engine.py

# 5. Run gap analyzer on a detected change
cd gap && python gap_analyzer.py

# 6. Run task generator (complete demo pipeline)
cd tasks && python task_generator.py

# 7. Run full pipeline
cd api && python pipeline.py
```

---

## What each module does

### `feed/ha_feed_engine.py`
- Scrapes 9 major HA websites (FDA, EMA, MHRA, PMDA, Health Canada, TGA, Swissmedic, ANVISA, CDSCO)
- Detects content changes via SHA-256 hash comparison
- Classifies changes using Claude API: change type, urgency, affected product types, ROD rows
- Stores classified changes in `regulatory_changes` table
- Filters out non-PV changes (website redesigns, non-regulatory content)

### `gap/gap_analyzer.py`
- Loads current system configuration from DB (Argus rules, SOPs, ROD snapshot)
- For each regulatory change, sends change + config to Claude API
- Claude identifies every gap: what's currently configured vs what regulation requires
- Returns structured gaps with: system, current state, required state, priority, GxP impact
- Stores gaps in `compliance_gaps` table

### `tasks/task_generator.py`
- For each gap, generates 1-N specific executable tasks
- Each task includes: step-by-step instructions, test cases, acceptance criteria, evidence checklist
- Routes tasks to correct owner: PV Operations / IT / Regulatory Affairs / QA / Medical
- Calculates deadline = effective_date - implementation_lead_days
- Generates GxP change control pack: impact assessment, validation strategy, rollback plan
- Builds JIRA ticket body for each task

### `api/pipeline.py`
- Orchestrates the full pipeline end-to-end
- Generates markdown + HTML change control document
- Routes P1 alerts to Slack
- Creates JIRA epic + child tickets
- Stores everything in PostgreSQL with full audit trail

---

## Database schema

See `schema/change_mgmt_schema.sql` for complete PostgreSQL schema including:
- `regulatory_changes` — one record per HA regulatory change
- `argus_reporting_rules` — current Argus Safety configuration (sample: Verastem)
- `pv_sops` — active PV SOPs with version and scope
- `compliance_gaps` — gaps between current config and new regulation
- `compliance_tasks` — actionable tasks with steps, tests, deadlines
- `change_control_packs` — GxP change control documents
- `task_audit_log` — completion audit trail
- `v_open_compliance_dashboard` — SQL view for dashboard

---

## Example: EMA GVP Module VI Rev 3 pipeline

```
Change detected: EMA GVP Module VI Rev 3 §VI.B.6.2
  Non-serious ICSR reporting: 90d → 45d
  Effective: 2026-09-05

Gaps found: 4
  [P1] Argus rule EMA_NONSER_POST_MKT: timeline 90d → 45d (GxP critical, validation needed)
  [P1] EV export profile EV_PROD_90D: batch window 90d → 45d (GxP critical)
  [P2] SOP-PV-004 §4.2: update 90d reference to 45d (GxP significant)
  [P1] RegIntel ROD: update EMA non-serious timeline_days 90 → 45 (administrative)

Tasks generated: 6
  [P1] Update Argus Safety EMA non-serious reporting rule
       → Owner: PV Operations | Deadline: 2026-08-06 | Steps: 5 | Tests: 2
  [P1] Validate Argus change in QA environment
       → Owner: QA | Deadline: 2026-08-20 | Steps: 3 | Tests: 3
  [P1] Update EudraVigilance export profile batch window
       → Owner: IT/Regulatory Systems | Deadline: 2026-08-06 | Steps: 4 | Tests: 2
  [P2] Update SOP-PV-004 §4.2 timeline reference
       → Owner: Regulatory Affairs | Deadline: 2026-08-01 | Steps: 4
  [P1] Update RegIntel ROD row
       → Owner: Praxigent Admin | Deadline: 2026-09-04 | Steps: 2
  [P2] Issue staff training bulletin on timeline change
       → Owner: PV Training | Deadline: 2026-09-01 | Steps: 3

Change control pack: CCR-CHG-20260607-EMA-001
  Impact: GxP critical — affects ICSR submission compliance for all EU-marketed products
  Validation: GAMP5 Category 4 (configured system) — UAT required
  Rollback: revert Argus rule to 90d if EV gateway rejects 45d submissions
```

---

## Integration targets

| System | Integration | Status |
|--------|-------------|--------|
| Oracle Argus Safety | API / DB change spec | Spec ready |
| EudraVigilance EVWEB | E2B gateway profile update | Spec ready |
| JIRA / ServiceNow | REST API ticket creation | Code ready |
| Slack / Teams | Webhook P1 alerts | Code ready |
| PostgreSQL ROD | Direct SQL update | Code ready |
| Email (SMTP) | Change pack delivery | Planned |

---

## Praxigent · RegIntel v1.0
Vensar Technology Inc. · praxigent.com
