-- ═══════════════════════════════════════════════════════════════════
-- REGINTEL CHANGE MANAGEMENT PLATFORM — COMPLETE DATABASE SCHEMA
-- Extends the core RegIntel ROD schema with change management tables
-- ═══════════════════════════════════════════════════════════════════

-- ─── EXTENSIONS (if not already present from ROD schema) ─────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ─── REGULATORY CHANGES ──────────────────────────────────────────
-- One record per detected regulatory change on an HA website
CREATE TABLE IF NOT EXISTS regulatory_changes (
    change_id                   VARCHAR(60) PRIMARY KEY,
    ha_code                     VARCHAR(20) NOT NULL,
    change_type                 VARCHAR(50) NOT NULL,
    -- timeline_change | new_report_type | format_change | new_ha_requirement
    -- guidance_update | ha_added | deadline_change | system_requirement
    title                       TEXT NOT NULL,
    description                 TEXT,
    regulation_ref              TEXT,         -- e.g. 'GVP Module VI Rev 3 §VI.B.6.2'
    affected_product_types      JSONB DEFAULT '["all"]',
    affected_phases             JSONB DEFAULT '["all"]',
    urgency                     VARCHAR(20) DEFAULT 'medium',
    -- critical (implement immediately) | high (< 2 wks) | medium | low
    effective_date              DATE,         -- When regulation takes effect
    implementation_deadline     DATE,         -- Effective date minus lead time
    rod_rows_affected           JSONB DEFAULT '[]',
    systems_requiring_change    JSONB DEFAULT '[]',
    -- [{system, change_description, priority}]
    confidence                  VARCHAR(20) DEFAULT 'medium',
    requires_human_review       BOOLEAN DEFAULT TRUE,
    source_url                  TEXT,
    detected_at                 TIMESTAMPTZ,
    status                      VARCHAR(50) DEFAULT 'pending_gap_analysis',
    -- pending_gap_analysis → pending_task_generation → tasks_generated
    -- → in_progress → completed → closed
    tasks_generated_at          TIMESTAMPTZ,
    closed_at                   TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_changes_ha          ON regulatory_changes(ha_code);
CREATE INDEX idx_changes_urgency     ON regulatory_changes(urgency);
CREATE INDEX idx_changes_status      ON regulatory_changes(status);
CREATE INDEX idx_changes_effective   ON regulatory_changes(effective_date);
CREATE INDEX idx_changes_deadline    ON regulatory_changes(implementation_deadline);
CREATE INDEX idx_changes_type        ON regulatory_changes(change_type);

-- ─── SYSTEM CONFIGURATION SNAPSHOT ──────────────────────────────
-- Stores current PV system configuration for gap analysis
CREATE TABLE IF NOT EXISTS sponsor_system_config (
    config_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sponsor_id          VARCHAR(100) NOT NULL,
    config_type         VARCHAR(50) NOT NULL,
    -- argus_rule | ev_profile | sop | rod | gateway | training
    ha_code             VARCHAR(20),
    system_name         VARCHAR(200),
    config_key          VARCHAR(200),    -- e.g. 'EMA_NONSER_POST_MKT'
    current_value       JSONB,           -- The current configured value
    regulation_ref      TEXT,            -- What regulation this config implements
    last_validated_date DATE,
    is_active           BOOLEAN DEFAULT TRUE,
    notes               TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_config_sponsor ON sponsor_system_config(sponsor_id);
CREATE INDEX idx_config_ha      ON sponsor_system_config(ha_code);
CREATE INDEX idx_config_type    ON sponsor_system_config(config_type);

-- ─── ARGUS REPORTING RULES (referenced by gap analyzer) ──────────
CREATE TABLE IF NOT EXISTS argus_reporting_rules (
    rule_id                 VARCHAR(100) PRIMARY KEY,
    sponsor_id              VARCHAR(100) NOT NULL,
    ha_code                 VARCHAR(20) NOT NULL,
    report_type             VARCHAR(50) NOT NULL,
    product_type            VARCHAR(50) DEFAULT 'all',
    phase                   VARCHAR(50) DEFAULT 'all',
    seriousness             VARCHAR(50),
    timeline_days           INTEGER NOT NULL,
    timeline_basis          VARCHAR(30) DEFAULT 'calendar_days',
    format                  VARCHAR(50) DEFAULT 'E2B_R3',
    gateway_profile         VARCHAR(100),
    is_active               BOOLEAN DEFAULT TRUE,
    last_validated_date     DATE,
    argus_config_path       TEXT,   -- Menu path in Argus to find this rule
    notes                   TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_argus_sponsor ON argus_reporting_rules(sponsor_id);
CREATE INDEX idx_argus_ha      ON argus_reporting_rules(ha_code);

-- Sample data: Verastem Oncology Argus configuration
INSERT INTO argus_reporting_rules VALUES
('FDA_IND_7DAY',    'verastem', 'FDA',  'expedited_fatal_lt', 'all', 'phase_1,phase_2,phase_3', 'fatal,life_threatening', 7,  'calendar_days', 'E2B_R3',   'FDA_ESM_PROD',  true, '2024-06-01', 'Configuration > Reporting Rules > FDA', 'IND 7-day fatal/LT SUSAR'),
('FDA_IND_15DAY',   'verastem', 'FDA',  'expedited_serious',  'all', 'phase_1,phase_2,phase_3', 'serious',                15, 'calendar_days', 'E2B_R3',   'FDA_ESM_PROD',  true, '2024-06-01', 'Configuration > Reporting Rules > FDA', 'IND 15-day serious SUSAR'),
('EMA_SUSAR_7DAY',  'verastem', 'EMA',  'susar_fatal_lt',     'all', 'phase_1,phase_2,phase_3', 'fatal,life_threatening', 7,  'calendar_days', 'E2B_R3',   'CTIS_EVCTM',    true, '2024-01-15', 'Configuration > Reporting Rules > EMA', 'CT Reg 536/2014 Art.42(2)'),
('EMA_SUSAR_15DAY', 'verastem', 'EMA',  'susar_serious',      'all', 'phase_1,phase_2,phase_3', 'serious',                15, 'calendar_days', 'E2B_R3',   'CTIS_EVCTM',    true, '2024-01-15', 'Configuration > Reporting Rules > EMA', 'CT Reg 536/2014 Art.42(3)'),
('EMA_NONSER_90D',  'verastem', 'EMA',  'non_serious_postmkt','all', 'marketed',                'non_serious',            90, 'calendar_days', 'E2B_R3',   'EV_EVWEB_PROD', true, '2024-01-15', 'Configuration > Reporting Rules > EMA', 'GVP Module VI Rev 2 §VI.B.6.3 — NEEDS UPDATE TO 45D'),
('PMDA_SAER_7DAY',  'verastem', 'PMDA', 'expedited_fatal_lt', 'all', 'phase_1,phase_2,phase_3', 'fatal,life_threatening', 7,  'calendar_days', 'J_ICSR_R3','PMDA_ESG_PROD', true, '2024-03-01', 'Configuration > Reporting Rules > PMDA', 'GCP Ordinance Art.20'),
('HC_SAE_7DAY',     'verastem', 'HC',   'expedited_fatal_lt', 'all', 'phase_1,phase_2,phase_3', 'fatal,life_threatening', 7,  'calendar_days', 'E2B_R3',   'HC_MEDEFFECT',  true, '2024-03-01', 'Configuration > Reporting Rules > HC', 'FDR C.05.012(1)(a)')
ON CONFLICT (rule_id) DO NOTHING;

-- ─── PV SOPs ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS pv_sops (
    sop_id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sponsor_id          VARCHAR(100) NOT NULL,
    sop_number          VARCHAR(50) NOT NULL,
    title               TEXT NOT NULL,
    version             VARCHAR(20) NOT NULL,
    effective_date      DATE,
    review_due_date     DATE,
    ha_codes_covered    JSONB DEFAULT '[]',
    content_summary     TEXT,           -- AI-summarized key provisions
    key_timelines       JSONB DEFAULT '{}', -- {ha_code: timeline_days}
    regulation_refs     JSONB DEFAULT '[]',
    status              VARCHAR(30) DEFAULT 'active',
    document_url        TEXT,
    owner_role          VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sops_sponsor ON pv_sops(sponsor_id);
CREATE INDEX idx_sops_status  ON pv_sops(status);

-- Sample SOPs
INSERT INTO pv_sops (sponsor_id, sop_number, title, version, effective_date,
                     review_due_date, ha_codes_covered, content_summary, status) VALUES
('verastem', 'SOP-PV-001', 'Adverse Event Receipt and Initial Processing', '4.0',
 '2024-01-01', '2025-12-31', '["FDA","EMA","PMDA","MHRA","HC"]',
 'Defines receipt, triage and initial processing of adverse event reports', 'active'),
('verastem', 'SOP-PV-004', 'ICSR Reporting Timelines', '3.1',
 '2024-03-01', '2026-12-01', '["FDA","EMA","PMDA","MHRA","HC","TGA"]',
 'Defines expedited (7/15-day) and periodic (90-day) reporting timelines per HA. §4.2: EMA non-serious = 90 calendar days. NEEDS UPDATE TO 45D.',
 'active'),
('verastem', 'SOP-PV-007', 'E2B R3 Submission and Gateway Management', '2.0',
 '2023-06-01', '2025-05-31', '["FDA","EMA","MHRA","HC","PMDA"]',
 'Covers E2B R3 XML generation, gateway configuration, acknowledgement handling', 'active'),
('verastem', 'SOP-PV-010', 'SUSAR Identification and Reporting', '5.2',
 '2024-06-01', '2026-05-31', '["FDA","EMA","MHRA","HC","TGA","PMDA"]',
 'SUSAR determination per ICH E2A: serious + unexpected + causally related in CT', 'active')
ON CONFLICT DO NOTHING;

-- ─── COMPLIANCE GAPS ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_gaps (
    gap_id                      VARCHAR(80) PRIMARY KEY,
    change_id                   VARCHAR(60) REFERENCES regulatory_changes(change_id),
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
    affected_products           JSONB DEFAULT '["all"]',
    affected_phases             JSONB DEFAULT '["all"]',
    specific_change_instruction TEXT,
    status                      VARCHAR(30) DEFAULT 'open',
    task_id                     VARCHAR(80),
    closed_at                   TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_gaps_change   ON compliance_gaps(change_id);
CREATE INDEX idx_gaps_priority ON compliance_gaps(priority);
CREATE INDEX idx_gaps_status   ON compliance_gaps(status);
CREATE INDEX idx_gaps_system   ON compliance_gaps(system);

-- ─── COMPLIANCE TASKS ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS compliance_tasks (
    task_id                     VARCHAR(80) PRIMARY KEY,
    gap_id                      VARCHAR(80) REFERENCES compliance_gaps(gap_id),
    change_id                   VARCHAR(60) REFERENCES regulatory_changes(change_id),
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

CREATE INDEX idx_tasks_gap      ON compliance_tasks(gap_id);
CREATE INDEX idx_tasks_change   ON compliance_tasks(change_id);
CREATE INDEX idx_tasks_priority ON compliance_tasks(priority);
CREATE INDEX idx_tasks_deadline ON compliance_tasks(deadline);
CREATE INDEX idx_tasks_owner    ON compliance_tasks(owner_role);
CREATE INDEX idx_tasks_status   ON compliance_tasks(status);
CREATE INDEX idx_tasks_jira     ON compliance_tasks(jira_ticket_id);

-- ─── CHANGE CONTROL PACKS ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS change_control_packs (
    pack_id                     VARCHAR(80) PRIMARY KEY,
    change_id                   VARCHAR(60) REFERENCES regulatory_changes(change_id),
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
    -- draft | pending_review | approved | in_progress | completed | closed
    approved_by                 VARCHAR(100),
    approved_at                 TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_ccr_change ON change_control_packs(change_id);
CREATE INDEX idx_ccr_status ON change_control_packs(status);

-- ─── TASK COMPLETION AUDIT LOG ────────────────────────────────────
CREATE TABLE IF NOT EXISTS task_audit_log (
    log_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         VARCHAR(80) REFERENCES compliance_tasks(task_id),
    action          VARCHAR(50) NOT NULL,  -- 'created'|'assigned'|'started'|'completed'|'rejected'|'closed'
    performed_by    VARCHAR(100),
    notes           TEXT,
    evidence_url    TEXT,
    logged_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ─── DASHBOARD VIEW: OPEN COMPLIANCE ITEMS ────────────────────────
CREATE OR REPLACE VIEW v_open_compliance_dashboard AS
SELECT
    ct.task_id,
    ct.change_id,
    rc.ha_code,
    rc.title AS change_title,
    ct.title AS task_title,
    ct.system,
    ct.priority,
    ct.owner_role,
    ct.deadline,
    CURRENT_DATE - ct.deadline AS days_overdue,
    ct.gxp_impact,
    ct.validation_required,
    ct.jira_ticket_id,
    ct.status,
    rc.effective_date,
    rc.urgency
FROM compliance_tasks ct
JOIN regulatory_changes rc ON rc.change_id = ct.change_id
WHERE ct.status IN ('open', 'in_progress')
ORDER BY ct.priority, ct.deadline NULLS LAST;

-- ─── USEFUL QUERIES ───────────────────────────────────────────────
COMMENT ON TABLE regulatory_changes IS
  'One record per regulatory change detected by the HA feed engine';
COMMENT ON TABLE compliance_gaps IS
  'One record per gap between current config and new regulation';
COMMENT ON TABLE compliance_tasks IS
  'One actionable task per gap — specific, system-assigned, deadline-bound';
COMMENT ON TABLE change_control_packs IS
  'GxP change control package bundling all tasks for one regulatory change';
COMMENT ON VIEW v_open_compliance_dashboard IS
  'All open tasks ordered by priority and deadline — primary dashboard view';
