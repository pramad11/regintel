-- =============================================================
-- PRAXIGENT VIGILONE — GLOBAL REGULATORY INTELLIGENCE PLATFORM
-- Regulatory Obligation Database (ROD) — PostgreSQL Schema v2.0
-- =============================================================

-- ─── EXTENSIONS ───────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- fuzzy text search on MedDRA terms

-- ─── ENUMERATIONS ─────────────────────────────────────────────
CREATE TYPE product_type_enum AS ENUM (
  'drug_small_molecule', 'biologic', 'vaccine', 'medical_device',
  'in_vitro_diagnostic', 'combination_product', 'gene_therapy',
  'cell_therapy', 'radiopharmaceutical'
);

CREATE TYPE development_phase_enum AS ENUM (
  'preclinical', 'phase_1', 'phase_2', 'phase_3',
  'phase_4_marketed', 'post_approval_ct', 'named_patient', 'compassionate_use'
);

CREATE TYPE seriousness_criteria_enum AS ENUM (
  'fatal', 'life_threatening', 'hospitalization', 'disability_incapacity',
  'congenital_anomaly', 'other_medically_important', 'non_serious'
);

CREATE TYPE expectedness_enum AS ENUM (
  'expected_listed', 'unexpected_unlisted', 'not_determinable'
);

CREATE TYPE causality_enum AS ENUM (
  'related', 'possibly_related', 'unlikely_related', 'unrelated', 'not_assessable'
);

CREATE TYPE report_format_enum AS ENUM (
  'e2b_r3_xml', 'e2b_r2_xml', 'medwatch_3500a', 'cioms_i',
  'japan_j_icsr', 'china_e2b', 'india_sugam', 'brazil_notivisa',
  'who_vigiflow', 'narrative_only', 'national_form'
);

CREATE TYPE submission_route_enum AS ENUM (
  'eudravigilance_evweb', 'fda_faers_esm', 'fda_ind_email_paper',
  'pmda_gateway', 'mhra_yellow_card_api', 'health_canada_mceyes',
  'tga_daen', 'anvisa_notivisa', 'nmpa_adrs_portal', 'cdsco_sugam',
  'vigiflow_who', 'national_portal', 'paper_submission', 'e2b_via_gateway'
);

CREATE TYPE timeline_basis_enum AS ENUM (
  'calendar_days', 'working_days', 'business_days'
);

CREATE TYPE domestic_foreign_enum AS ENUM (
  'domestic', 'foreign', 'both', 'not_applicable'
);

-- ─── HEALTH AUTHORITIES ───────────────────────────────────────
CREATE TABLE health_authority (
  ha_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ha_code        VARCHAR(20)  NOT NULL UNIQUE,
  ha_name        VARCHAR(200) NOT NULL,
  country_code   CHAR(2)      NOT NULL,
  region         VARCHAR(50),
  ict_region     VARCHAR(20),
  portal_url     TEXT,
  e2b_version    VARCHAR(10),
  gateway_id     VARCHAR(100),
  active         BOOLEAN NOT NULL DEFAULT TRUE,
  last_updated   TIMESTAMPTZ DEFAULT NOW(),
  notes          TEXT
);

-- ─── REGULATORY FRAMEWORKS ────────────────────────────────────
CREATE TABLE regulatory_framework (
  framework_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ha_id             UUID NOT NULL REFERENCES health_authority(ha_id),
  regulation_code   VARCHAR(100) NOT NULL,
  regulation_name   TEXT NOT NULL,
  product_type      product_type_enum[],
  phase_scope       development_phase_enum[],
  effective_date    DATE,
  sunset_date       DATE,
  source_url        TEXT,
  full_text         TEXT,
  last_scraped      TIMESTAMPTZ,
  version           INTEGER NOT NULL DEFAULT 1
);

-- ─── REPORTING OBLIGATIONS (Core ROD table) ───────────────────
-- This is the VigilOne rules engine — maps product/phase/AE attributes
-- to HA-specific reporting requirements across all 16 global HAs
CREATE TABLE reporting_obligation (
  obligation_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ha_id                UUID NOT NULL REFERENCES health_authority(ha_id),
  framework_id         UUID REFERENCES regulatory_framework(framework_id),
  -- Product scoping
  product_type         product_type_enum[],
  phase                development_phase_enum[],
  -- AE characteristics that trigger this obligation
  seriousness          seriousness_criteria_enum[],
  expectedness         expectedness_enum[],
  causality_required   causality_enum[],
  -- Domestic/foreign scoping
  domestic_foreign     domestic_foreign_enum NOT NULL DEFAULT 'both',
  -- Report details
  report_name          VARCHAR(200) NOT NULL,
  report_type          VARCHAR(50),
  report_format        report_format_enum[],
  submission_route     submission_route_enum[],
  -- Timeline
  timeline_days        INTEGER,
  timeline_basis       timeline_basis_enum NOT NULL DEFAULT 'calendar_days',
  clock_start          VARCHAR(200),
  follow_up_required   BOOLEAN DEFAULT FALSE,
  follow_up_days       INTEGER,
  -- Periodic
  is_periodic          BOOLEAN NOT NULL DEFAULT FALSE,
  periodic_frequency   VARCHAR(50),
  periodic_report_ref  VARCHAR(100),
  aggregate_report     BOOLEAN DEFAULT FALSE,
  -- Special conditions
  conditions_text      TEXT,
  exemptions_text      TEXT,
  -- Metadata
  active               BOOLEAN NOT NULL DEFAULT TRUE,
  effective_date       DATE,
  sunset_date          DATE,
  last_updated         TIMESTAMPTZ DEFAULT NOW(),
  created_by           VARCHAR(100) DEFAULT 'vigilone_system'
);

-- ─── MEDDRA REFERENCE ─────────────────────────────────────────
CREATE TABLE meddra_term (
  term_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  meddra_version  VARCHAR(10) NOT NULL,
  soc_code        INTEGER,
  soc_name        VARCHAR(200),
  hlgt_code       INTEGER,
  hlgt_name       VARCHAR(200),
  hlt_code        INTEGER,
  hlt_name        VARCHAR(200),
  pt_code         INTEGER NOT NULL UNIQUE,
  pt_name         VARCHAR(200) NOT NULL,
  llt_code        INTEGER,
  llt_name        VARCHAR(200),
  is_current      BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_meddra_pt_trgm ON meddra_term USING gin(pt_name gin_trgm_ops);

-- ─── PRODUCT PROFILES ─────────────────────────────────────────
CREATE TABLE product_profile (
  product_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  sponsor_id         UUID,
  product_name       VARCHAR(200) NOT NULL,
  inn_name           VARCHAR(200),
  product_type       product_type_enum NOT NULL,
  therapeutic_area   VARCHAR(100),
  indication         TEXT,
  current_phase      development_phase_enum NOT NULL,
  -- Regulatory identifiers
  ind_number         VARCHAR(50),
  nda_bla_number     VARCHAR(50),
  eudract_number     VARCHAR(30),
  ct_gov_nct         VARCHAR(20),
  eudra_ct_number    VARCHAR(30),
  isrctn_number      VARCHAR(20),
  -- Approval status
  approved_has       UUID[],
  -- Reference safety information
  ib_version         VARCHAR(20),
  ib_date            DATE,
  smpc_version       VARCHAR(20),
  smpc_date          DATE,
  uspi_version       VARCHAR(20),
  uspi_date          DATE,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- ─── TRIAL SITES / GEOGRAPHY ──────────────────────────────────
CREATE TABLE trial_site (
  site_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  product_id        UUID NOT NULL REFERENCES product_profile(product_id),
  country_code      CHAR(2) NOT NULL,
  ha_id             UUID NOT NULL REFERENCES health_authority(ha_id),
  site_name         VARCHAR(200),
  site_number       VARCHAR(50),
  pi_name           VARCHAR(200),
  site_status       VARCHAR(50),
  first_patient_in  DATE,
  last_patient_out  DATE,
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- ─── ADVERSE EVENT CASES ──────────────────────────────────────
CREATE TABLE ae_case (
  case_id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  product_id            UUID NOT NULL REFERENCES product_profile(product_id),
  internal_case_num     VARCHAR(50) UNIQUE NOT NULL,
  argus_case_num        VARCHAR(50),
  pt_code               INTEGER REFERENCES meddra_term(pt_code),
  pt_name               VARCHAR(200),
  seriousness           seriousness_criteria_enum[] NOT NULL,
  causality             causality_enum,
  expectedness          expectedness_enum,
  outcome               VARCHAR(100),
  initial_receipt_date  DATE NOT NULL,
  aware_date            DATE,
  country_of_occurrence CHAR(2),
  reporter_type         VARCHAR(50),
  is_domestic           BOOLEAN,
  case_status           VARCHAR(50) DEFAULT 'open',
  lock_date             DATE,
  created_at            TIMESTAMPTZ DEFAULT NOW(),
  updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ─── SUBMISSION TRACKER ───────────────────────────────────────
CREATE TABLE submission_record (
  submission_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  case_id             UUID REFERENCES ae_case(case_id),
  obligation_id       UUID NOT NULL REFERENCES reporting_obligation(obligation_id),
  ha_id               UUID NOT NULL REFERENCES health_authority(ha_id),
  report_type         VARCHAR(50) NOT NULL,
  due_date            DATE NOT NULL,
  submitted_date      DATE,
  submission_status   VARCHAR(30) DEFAULT 'pending',
  acknowledgement_num VARCHAR(100),
  e2b_message_id      VARCHAR(100),
  followup_due_date   DATE,
  followup_submitted  DATE,
  created_at          TIMESTAMPTZ DEFAULT NOW(),
  updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ─── REFERENCE SAFETY INFO ────────────────────────────────────
CREATE TABLE reference_safety_info (
  rsi_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  product_id       UUID NOT NULL REFERENCES product_profile(product_id),
  document_type    VARCHAR(50) NOT NULL,
  document_version VARCHAR(30),
  effective_date   DATE,
  listed_reactions INTEGER[],
  uploaded_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── HA FEED LOG (scraper audit) ──────────────────────────────
CREATE TABLE ha_feed_log (
  log_id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  ha_id              UUID NOT NULL REFERENCES health_authority(ha_id),
  feed_type          VARCHAR(50),
  source_url         TEXT,
  raw_content_hash   VARCHAR(64),
  change_detected    BOOLEAN DEFAULT FALSE,
  change_summary     TEXT,
  scraped_at         TIMESTAMPTZ DEFAULT NOW(),
  processed          BOOLEAN DEFAULT FALSE
);

-- ─── INDEXES ──────────────────────────────────────────────────
CREATE INDEX idx_obligation_ha         ON reporting_obligation(ha_id);
CREATE INDEX idx_obligation_phase      ON reporting_obligation USING gin(phase);
CREATE INDEX idx_obligation_seriousness ON reporting_obligation USING gin(seriousness);
CREATE INDEX idx_submission_case       ON submission_record(case_id);
CREATE INDEX idx_submission_status     ON submission_record(submission_status);
CREATE INDEX idx_submission_due        ON submission_record(due_date);
CREATE INDEX idx_trial_site_product    ON trial_site(product_id);
CREATE INDEX idx_ae_case_product       ON ae_case(product_id);
CREATE INDEX idx_ae_case_receipt       ON ae_case(initial_receipt_date);

-- ─── CORE OBLIGATION LOOKUP FUNCTION ──────────────────────────
-- Called by the VigilOne Obligation Agent to resolve all applicable HA obligations
CREATE OR REPLACE FUNCTION get_reporting_obligations(
  p_product_type  product_type_enum,
  p_phase         development_phase_enum,
  p_seriousness   seriousness_criteria_enum,
  p_expectedness  expectedness_enum,
  p_ha_ids        UUID[]
)
RETURNS TABLE (
  ha_code           VARCHAR,
  ha_name           VARCHAR,
  report_name       VARCHAR,
  report_type       VARCHAR,
  timeline_days     INTEGER,
  timeline_basis    timeline_basis_enum,
  domestic_foreign  domestic_foreign_enum,
  report_formats    report_format_enum[],
  submission_routes submission_route_enum[],
  is_periodic       BOOLEAN,
  periodic_ref      VARCHAR,
  conditions        TEXT
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    ha.ha_code,
    ha.ha_name,
    ro.report_name,
    ro.report_type,
    ro.timeline_days,
    ro.timeline_basis,
    ro.domestic_foreign,
    ro.report_format,
    ro.submission_route,
    ro.is_periodic,
    ro.periodic_report_ref,
    ro.conditions_text
  FROM reporting_obligation ro
  JOIN health_authority ha ON ha.ha_id = ro.ha_id
  WHERE
    ro.active = TRUE
    AND (p_ha_ids IS NULL OR ha.ha_id = ANY(p_ha_ids))
    AND p_product_type  = ANY(ro.product_type)
    AND p_phase         = ANY(ro.phase)
    AND p_seriousness   = ANY(ro.seriousness)
    AND (ro.expectedness IS NULL OR p_expectedness = ANY(ro.expectedness))
  ORDER BY ro.timeline_days ASC NULLS LAST;
END;
$$ LANGUAGE plpgsql;

-- ─── SEED: HEALTH AUTHORITIES ─────────────────────────────────
INSERT INTO health_authority (ha_code, ha_name, country_code, region, ict_region, portal_url, e2b_version) VALUES
  ('FDA',        'Food and Drug Administration',                               'US', 'North America', 'ICH',     'https://www.fda.gov',              'R3'),
  ('EMA',        'European Medicines Agency',                                  'EU', 'Europe',        'ICH',     'https://www.ema.europa.eu',         'R3'),
  ('MHRA',       'Medicines and Healthcare products Regulatory Agency',         'GB', 'Europe',        'ICH',     'https://www.gov.uk/mhra',           'R3'),
  ('PMDA',       'Pharmaceuticals and Medical Devices Agency',                 'JP', 'APAC',          'ICH',     'https://www.pmda.go.jp',            'R3'),
  ('HC',         'Health Canada',                                               'CA', 'North America', 'ICH',     'https://www.canada.ca/health',      'R3'),
  ('TGA',        'Therapeutic Goods Administration',                           'AU', 'APAC',          'ICH',     'https://www.tga.gov.au',            'R3'),
  ('ANVISA',     'Agência Nacional de Vigilância Sanitária',                   'BR', 'Latin America', 'non-ICH', 'https://www.gov.br/anvisa',         'R2'),
  ('NMPA',       'National Medical Products Administration',                   'CN', 'APAC',          'ICH',     'https://www.nmpa.gov.cn',           'R3'),
  ('CDSCO',      'Central Drugs Standard Control Organisation',                'IN', 'APAC',          'non-ICH', 'https://cdsco.gov.in',              'R2'),
  ('SFDA',       'Saudi Food and Drug Authority',                              'SA', 'Middle East',   'non-ICH', 'https://www.sfda.gov.sa',           'R2'),
  ('SWISSMEDIC', 'Swissmedic',                                                 'CH', 'Europe',        'ICH',     'https://www.swissmedic.ch',         'R3'),
  ('MFDS',       'Ministry of Food and Drug Safety',                          'KR', 'APAC',          'ICH',     'https://www.mfds.go.kr',            'R3'),
  ('MEDSAFE',    'Medsafe New Zealand',                                        'NZ', 'APAC',          'non-ICH', 'https://www.medsafe.govt.nz',       'R2'),
  ('COFEPRIS',   'Comisión Federal para la Protección contra Riesgos Sanitarios', 'MX', 'Latin America', 'non-ICH', 'https://www.gob.mx/cofepris', 'R2'),
  ('WHO',        'World Health Organization / UMC VigiBase',                  'CH', 'Global',        'Global',  'https://www.who-umc.org',           'R2'),
  ('AIFA',       'Agenzia Italiana del Farmaco',                               'IT', 'Europe',        'ICH',     'https://www.aifa.gov.it',           'R3'),
  ('BfArM',      'Bundesinstitut für Arzneimittel',                            'DE', 'Europe',        'ICH',     'https://www.bfarm.de',              'R3'),
  ('ANSM',       'Agence nationale de sécurité du médicament',                'FR', 'Europe',        'ICH',     'https://www.ansm.sante.fr',         'R3'),
  ('FIMEA',      'Finnish Medicines Agency',                                   'FI', 'Europe',        'ICH',     'https://www.fimea.fi',              'R3'),
  ('HSA',        'Health Sciences Authority Singapore',                        'SG', 'APAC',          'non-ICH', 'https://www.hsa.gov.sg',            'R3');

-- ─── COMMENTS ─────────────────────────────────────────────────
COMMENT ON TABLE reporting_obligation IS
  'VigilOne core rules engine: maps product/phase/AE attributes to HA-specific reporting requirements';
COMMENT ON TABLE ha_feed_log IS
  'Audit trail for automated HA website scraping — change detection for regulatory updates';
COMMENT ON FUNCTION get_reporting_obligations IS
  'Primary query function called by the VigilOne Obligation Agent to resolve applicable obligations';
