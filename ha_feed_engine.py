"""
REGINTEL — HA FEED ENGINE
=========================
Monitors 187 Health Authority sources for regulatory changes.
Detects diffs, classifies changes via Claude API, updates ROD.

Architecture:
  Scheduler → SourceScraper → DiffDetector → ChangeClassifier → RODUpdater
                                                      ↓
                                              ChangeRecord (PostgreSQL)
                                                      ↓
                                              GapAnalyzer (next module)
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import anthropic
import httpx
import psycopg2
from psycopg2.extras import Json, RealDictCursor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger("ha_feed_engine")

# ─────────────────────────────────────────────────────────────────
# DATA MODELS
# ─────────────────────────────────────────────────────────────────

@dataclass
class HASource:
    ha_code: str
    ha_name: str
    region: str
    urls: list[dict]          # [{url, label, type: guidance|news|regulation}]
    scrape_interval_hours: int = 24
    priority: str = "standard"  # critical | high | standard


@dataclass
class RawChange:
    ha_code: str
    source_url: str
    content_hash: str
    raw_text: str
    detected_at: datetime
    previous_hash: Optional[str] = None
    diff_summary: Optional[str] = None


@dataclass
class ClassifiedChange:
    ha_code: str
    change_type: str           # timeline_change | new_report_type | format_change |
                               # new_ha_requirement | guidance_update | ha_added |
                               # deadline_change | system_requirement
    title: str
    description: str
    regulation_ref: str        # e.g. "GVP Module VI Rev 3 §VI.B.6.2"
    affected_product_types: list[str]
    affected_phases: list[str]
    urgency: str               # critical | high | medium | low
    effective_date: Optional[str]
    implementation_deadline: Optional[str]
    rod_rows_affected: list[str]   # ROD obligation IDs or descriptions
    raw_change_id: str
    confidence: str            # high | medium | low
    requires_human_review: bool
    source_url: str
    detected_at: str


# ─────────────────────────────────────────────────────────────────
# HA SOURCE REGISTRY
# ─────────────────────────────────────────────────────────────────

HA_SOURCES = [

    HASource(
        ha_code="FDA",
        ha_name="U.S. Food and Drug Administration",
        region="North America",
        priority="critical",
        urls=[
            {"url": "https://www.fda.gov/safety/medwatch-fda-safety-information-and-adverse-event-reporting-program",
             "label": "MedWatch", "type": "guidance"},
            {"url": "https://www.fda.gov/regulatory-information/search-fda-guidance-documents",
             "label": "Guidance search", "type": "guidance"},
            {"url": "https://www.federalregister.gov/agencies/food-and-drug-administration",
             "label": "Federal Register", "type": "regulation"},
            {"url": "https://www.fda.gov/drugs/development-approval-process-drugs/ind-application-reporting-requirements",
             "label": "IND reporting", "type": "regulation"},
        ]
    ),

    HASource(
        ha_code="EMA",
        ha_name="European Medicines Agency",
        region="Europe",
        priority="critical",
        urls=[
            {"url": "https://www.ema.europa.eu/en/human-regulatory-overview/pharmacovigilance",
             "label": "PhV overview", "type": "guidance"},
            {"url": "https://www.ema.europa.eu/en/human-regulatory-overview/post-authorisation/pharmacovigilance-post-authorisation/good-pharmacovigilance-practices",
             "label": "GVP guidelines", "type": "regulation"},
            {"url": "https://www.ema.europa.eu/en/news-events/news",
             "label": "EMA News", "type": "news"},
            {"url": "https://www.ema.europa.eu/en/human-regulatory-overview/post-authorisation/pharmacovigilance-post-authorisation/eudravigilance",
             "label": "EudraVigilance", "type": "guidance"},
        ]
    ),

    HASource(
        ha_code="MHRA",
        ha_name="Medicines and Healthcare products Regulatory Agency",
        region="Europe",
        priority="high",
        urls=[
            {"url": "https://www.gov.uk/guidance/pharmacovigilance",
             "label": "PhV guidance", "type": "guidance"},
            {"url": "https://www.gov.uk/government/collections/pharmacovigilance",
             "label": "PhV collection", "type": "guidance"},
            {"url": "https://www.gov.uk/government/publications/guidance-on-submitting-information-to-the-yellow-card-scheme",
             "label": "Yellow Card", "type": "guidance"},
        ]
    ),

    HASource(
        ha_code="PMDA",
        ha_name="Pharmaceuticals and Medical Devices Agency",
        region="APAC",
        priority="high",
        urls=[
            {"url": "https://www.pmda.go.jp/english/safety/info-services/drugs/0001.html",
             "label": "Drug safety info", "type": "guidance"},
            {"url": "https://www.pmda.go.jp/english/safety/0001.html",
             "label": "Safety notifications", "type": "news"},
        ]
    ),

    HASource(
        ha_code="HC",
        ha_name="Health Canada",
        region="North America",
        priority="high",
        urls=[
            {"url": "https://www.canada.ca/en/health-canada/services/drugs-health-products/medeffect-canada/adverse-reaction-reporting.html",
             "label": "MedEffect reporting", "type": "guidance"},
            {"url": "https://www.canada.ca/en/health-canada/services/drugs-health-products/drug-products/fact-sheets/post-market-surveillance.html",
             "label": "Post-market surveillance", "type": "guidance"},
        ]
    ),

    HASource(
        ha_code="TGA",
        ha_name="Therapeutic Goods Administration",
        region="APAC",
        priority="standard",
        urls=[
            {"url": "https://www.tga.gov.au/resources/publication/publications/reporting-adverse-events",
             "label": "AE reporting", "type": "guidance"},
            {"url": "https://www.tga.gov.au/pharmacovigilance",
             "label": "PhV", "type": "guidance"},
        ]
    ),

    # Additional HAs — add URLs as needed
    HASource(ha_code="SWISSMEDIC", ha_name="Swissmedic", region="Europe", priority="standard",
             urls=[{"url": "https://www.swissmedic.ch/swissmedic/en/home/humanarzneimittel/pharmacovigilance.html", "label": "PhV", "type": "guidance"}]),
    HASource(ha_code="ANVISA", ha_name="ANVISA Brazil", region="Latin America", priority="standard",
             urls=[{"url": "https://www.gov.br/anvisa/pt-br/assuntos/farmacovigilancia", "label": "PhV", "type": "guidance"}]),
    HASource(ha_code="CDSCO", ha_name="CDSCO India", region="APAC", priority="standard",
             urls=[{"url": "https://cdsco.gov.in/opencms/opencms/en/Pharmacovigilance/", "label": "PhV", "type": "guidance"}]),
]


# ─────────────────────────────────────────────────────────────────
# SCRAPER
# ─────────────────────────────────────────────────────────────────

class SourceScraper:
    """Fetches HA source URLs and extracts meaningful text content."""

    HEADERS = {
        "User-Agent": "RegIntel/1.0 (Praxigent PV Regulatory Intelligence; regulatory-monitoring-bot)",
        "Accept": "text/html,application/xhtml+xml,text/plain",
    }
    TIMEOUT = 30

    async def fetch(self, url: str) -> Optional[str]:
        try:
            async with httpx.AsyncClient(headers=self.HEADERS, timeout=self.TIMEOUT,
                                          follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return self._extract_text(resp.text, url)
        except Exception as e:
            log.warning(f"Fetch failed {url}: {e}")
            return None

    def _extract_text(self, html: str, url: str) -> str:
        """Extract meaningful text — strip nav, footer, ads."""
        # Remove scripts, styles, nav elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        # Extract text
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        # Limit to first 8000 chars for change detection
        return text[:8000]

    def compute_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()


# ─────────────────────────────────────────────────────────────────
# DIFF DETECTOR
# ─────────────────────────────────────────────────────────────────

class DiffDetector:
    """Compares current content against stored hash to detect changes."""

    def __init__(self, db_conn):
        self.db = db_conn

    def get_previous_hash(self, ha_code: str, url: str) -> Optional[str]:
        with self.db.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT raw_content_hash FROM ha_feed_log
                WHERE ha_code = %s AND source_url = %s
                ORDER BY scraped_at DESC LIMIT 1
            """, (ha_code, url))
            row = cur.fetchone()
            return row["raw_content_hash"] if row else None

    def has_changed(self, current_hash: str, previous_hash: Optional[str]) -> bool:
        if previous_hash is None:
            return True   # First time seeing this URL — treat as new
        return current_hash != previous_hash

    def compute_diff_summary(self, old_text: str, new_text: str) -> str:
        """Simple sentence-level diff — find new sentences."""
        if not old_text:
            return "New source — baseline captured"
        old_sentences = set(s.strip() for s in old_text.split('.') if len(s.strip()) > 30)
        new_sentences = set(s.strip() for s in new_text.split('.') if len(s.strip()) > 30)
        added = new_sentences - old_sentences
        removed = old_sentences - new_sentences
        parts = []
        if added:
            sample = list(added)[:3]
            parts.append(f"New content: {'; '.join(sample[:2])}")
        if removed:
            parts.append(f"Removed: {len(removed)} sentences")
        return " | ".join(parts) if parts else "Minor formatting change"

    def store_feed_log(self, ha_code: str, url: str, content_hash: str,
                       change_detected: bool, diff_summary: str):
        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO ha_feed_log
                    (ha_code, source_url, raw_content_hash, change_detected,
                     change_summary, scraped_at, processed)
                VALUES (%s, %s, %s, %s, %s, %s, false)
            """, (ha_code, url, content_hash, change_detected,
                  diff_summary, datetime.now(timezone.utc)))
        self.db.commit()


# ─────────────────────────────────────────────────────────────────
# CHANGE CLASSIFIER (Claude API)
# ─────────────────────────────────────────────────────────────────

CLASSIFIER_SYSTEM = """You are an expert pharmacovigilance regulatory intelligence analyst.
Your job is to analyze regulatory text changes detected on Health Authority websites
and classify them in terms of their impact on pharmacovigilance operations.

You must be precise, cite specific regulation articles, and identify exactly which
operational systems and processes need to change. Think like a senior PV consultant
who understands both the regulatory requirement and what it means for Argus Safety,
E2B submissions, SOPs, and the RegIntel ROD database."""

CLASSIFIER_PROMPT = """
A regulatory change has been detected on a Health Authority website.
Analyze this change and classify it for our pharmacovigilance compliance system.

HA: {ha_code} — {ha_name}
Source URL: {url}
Detected: {detected_at}

CONTENT THAT CHANGED:
{diff_summary}

FULL CURRENT PAGE TEXT (first 4000 chars):
{page_text}

Return ONLY a valid JSON object with this exact structure:
{{
  "change_type": "one of: timeline_change | new_report_type | format_change | new_ha_requirement | guidance_update | ha_added | deadline_change | system_requirement | no_pv_impact",
  "title": "concise 1-line title describing the change",
  "description": "2-3 sentences describing exactly what changed and why it matters for PV",
  "regulation_ref": "exact regulation article if identifiable, e.g. GVP Module VI §VI.B.6.2",
  "affected_product_types": ["array: drug_small_molecule|biologic|vaccine|gene_therapy|medical_device|all"],
  "affected_phases": ["array: phase_1|phase_2|phase_3|marketed|compassionate|all"],
  "urgency": "critical|high|medium|low",
  "effective_date": "YYYY-MM-DD or null if not specified",
  "implementation_deadline": "YYYY-MM-DD (effective_date minus 30 days for change control) or null",
  "rod_rows_affected": ["list of RegIntel ROD rows affected, e.g. 'EMA post-mkt non-serious ICSR'"],
  "systems_requiring_change": [
    {{
      "system": "system name e.g. Oracle Argus Safety | EudraVigilance | SOP | RegIntel ROD",
      "change_description": "exactly what needs to change in this system",
      "priority": "P1|P2|P3"
    }}
  ],
  "confidence": "high|medium|low",
  "requires_human_review": true or false,
  "pv_impact_summary": "one sentence: what this means for a PV operations team today"
}}

If this change has no pharmacovigilance relevance (website redesign, non-PV content),
set change_type to "no_pv_impact" and keep other fields minimal.
"""


class ChangeClassifier:
    """Uses Claude API to classify regulatory changes."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def classify(self, ha: HASource, raw_change: RawChange) -> ClassifiedChange:
        prompt = CLASSIFIER_PROMPT.format(
            ha_code=ha.ha_code,
            ha_name=ha.ha_name,
            url=raw_change.source_url,
            detected_at=raw_change.detected_at.isoformat(),
            diff_summary=raw_change.diff_summary or "First-time capture",
            page_text=raw_change.raw_text[:4000]
        )

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=CLASSIFIER_SYSTEM,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        # Strip markdown fences
        text = re.sub(r'^```json?\n?', '', text)
        text = re.sub(r'\n?```$', '', text)

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            log.error(f"JSON parse error in classifier response: {e}\nText: {text[:500]}")
            data = {"change_type": "no_pv_impact", "confidence": "low",
                    "requires_human_review": True, "title": "Parse error — manual review needed"}

        return ClassifiedChange(
            ha_code=ha.ha_code,
            change_type=data.get("change_type", "guidance_update"),
            title=data.get("title", "Regulatory update detected"),
            description=data.get("description", ""),
            regulation_ref=data.get("regulation_ref", ""),
            affected_product_types=data.get("affected_product_types", ["all"]),
            affected_phases=data.get("affected_phases", ["all"]),
            urgency=data.get("urgency", "medium"),
            effective_date=data.get("effective_date"),
            implementation_deadline=data.get("implementation_deadline"),
            rod_rows_affected=data.get("rod_rows_affected", []),
            raw_change_id=raw_change.content_hash,
            confidence=data.get("confidence", "medium"),
            requires_human_review=data.get("requires_human_review", True),
            source_url=raw_change.source_url,
            detected_at=raw_change.detected_at.isoformat(),
        ), data.get("systems_requiring_change", [])


# ─────────────────────────────────────────────────────────────────
# ROD UPDATER
# ─────────────────────────────────────────────────────────────────

class RODUpdater:
    """Updates the RegIntel ROD when regulations change."""

    def __init__(self, db_conn, api_key: str):
        self.db = db_conn
        self.client = anthropic.Anthropic(api_key=api_key)

    def store_change_record(self, change: ClassifiedChange,
                            systems_to_change: list) -> str:
        """Store classified change in regulatory_changes table."""
        change_id = f"CHG-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{change.ha_code}"

        with self.db.cursor() as cur:
            cur.execute("""
                INSERT INTO regulatory_changes (
                    change_id, ha_code, change_type, title, description,
                    regulation_ref, affected_product_types, affected_phases,
                    urgency, effective_date, implementation_deadline,
                    rod_rows_affected, systems_requiring_change,
                    confidence, requires_human_review, source_url,
                    detected_at, status, created_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, 'pending_task_generation', NOW()
                )
            """, (
                change_id, change.ha_code, change.change_type, change.title,
                change.description, change.regulation_ref,
                Json(change.affected_product_types), Json(change.affected_phases),
                change.urgency, change.effective_date, change.implementation_deadline,
                Json(change.rod_rows_affected), Json(systems_to_change),
                change.confidence, change.requires_human_review,
                change.source_url, change.detected_at
            ))
        self.db.commit()
        log.info(f"Stored change record: {change_id} — {change.title}")
        return change_id

    def update_rod_row(self, ha_code: str, obligation_description: str,
                       field_to_update: str, new_value, regulation_ref: str):
        """Update a specific ROD obligation row when a regulation changes."""
        with self.db.cursor() as cur:
            cur.execute(f"""
                UPDATE reporting_obligation
                SET {field_to_update} = %s,
                    last_updated = NOW(),
                    regulation_change_ref = %s
                WHERE ha_id = (SELECT ha_id FROM health_authority WHERE ha_code = %s)
                AND report_name ILIKE %s
            """, (new_value, regulation_ref, ha_code, f"%{obligation_description}%"))
            rows = cur.rowcount
        self.db.commit()
        log.info(f"Updated ROD: {ha_code} / {obligation_description} — {field_to_update}={new_value} ({rows} rows)")


# ─────────────────────────────────────────────────────────────────
# MAIN FEED ENGINE ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────

class HAFeedEngine:
    """Main orchestrator for the feed engine pipeline."""

    def __init__(self, db_conn, api_key: str):
        self.db = db_conn
        self.scraper = SourceScraper()
        self.diff_detector = DiffDetector(db_conn)
        self.classifier = ChangeClassifier(api_key)
        self.rod_updater = RODUpdater(db_conn, api_key)
        self.changes_detected: list[tuple[ClassifiedChange, list]] = []

    async def run_source(self, ha: HASource, source: dict) -> Optional[tuple]:
        """Process a single HA source URL."""
        url = source["url"]
        log.info(f"Scraping {ha.ha_code} — {source['label']}")

        # Fetch current content
        text = await self.scraper.fetch(url)
        if not text:
            return None

        current_hash = self.scraper.compute_hash(text)
        previous_hash = self.diff_detector.get_previous_hash(ha.ha_code, url)
        has_changed = self.diff_detector.has_changed(current_hash, previous_hash)

        # Always store feed log
        self.diff_detector.store_feed_log(
            ha.ha_code, url, current_hash, has_changed,
            "Change detected" if has_changed else "No change"
        )

        if not has_changed:
            log.info(f"  No change: {ha.ha_code} / {source['label']}")
            return None

        log.info(f"  CHANGE DETECTED: {ha.ha_code} / {source['label']}")

        # Build raw change object
        raw_change = RawChange(
            ha_code=ha.ha_code,
            source_url=url,
            content_hash=current_hash,
            raw_text=text,
            detected_at=datetime.now(timezone.utc),
            previous_hash=previous_hash,
            diff_summary=f"Content changed at {source['label']}"
        )

        # Classify with Claude
        classified_change, systems = self.classifier.classify(ha, raw_change)

        # Skip if no PV impact
        if classified_change.change_type == "no_pv_impact":
            log.info(f"  No PV impact — skipping task generation")
            return None

        # Store change record
        change_id = self.rod_updater.store_change_record(classified_change, systems)
        classified_change.raw_change_id = change_id

        return classified_change, systems

    async def run_all(self, ha_codes: Optional[list[str]] = None):
        """Run feed engine for all (or specified) HAs."""
        sources_to_run = HA_SOURCES
        if ha_codes:
            sources_to_run = [ha for ha in HA_SOURCES if ha.ha_code in ha_codes]

        all_tasks = []
        for ha in sources_to_run:
            for source in ha.urls:
                all_tasks.append(self.run_source(ha, source))

        results = await asyncio.gather(*all_tasks, return_exceptions=True)

        self.changes_detected = [
            r for r in results
            if r is not None and not isinstance(r, Exception)
        ]

        log.info(f"Feed run complete: {len(self.changes_detected)} PV-relevant changes detected")
        return self.changes_detected


# ─────────────────────────────────────────────────────────────────
# POSTGRESQL SCHEMA FOR CHANGES TABLE
# ─────────────────────────────────────────────────────────────────

CHANGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS regulatory_changes (
    change_id               VARCHAR(50) PRIMARY KEY,
    ha_code                 VARCHAR(20) NOT NULL,
    change_type             VARCHAR(50) NOT NULL,
    title                   TEXT NOT NULL,
    description             TEXT,
    regulation_ref          TEXT,
    affected_product_types  JSONB,
    affected_phases         JSONB,
    urgency                 VARCHAR(20) DEFAULT 'medium',
    effective_date          DATE,
    implementation_deadline DATE,
    rod_rows_affected       JSONB,
    systems_requiring_change JSONB,
    confidence              VARCHAR(20),
    requires_human_review   BOOLEAN DEFAULT TRUE,
    source_url              TEXT,
    detected_at             TIMESTAMPTZ,
    status                  VARCHAR(50) DEFAULT 'pending_task_generation',
    tasks_generated_at      TIMESTAMPTZ,
    closed_at               TIMESTAMPTZ,
    created_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_changes_ha     ON regulatory_changes(ha_code);
CREATE INDEX IF NOT EXISTS idx_changes_urgency ON regulatory_changes(urgency);
CREATE INDEX IF NOT EXISTS idx_changes_status  ON regulatory_changes(status);
CREATE INDEX IF NOT EXISTS idx_changes_deadline ON regulatory_changes(implementation_deadline);
"""


if __name__ == "__main__":
    import os

    # Example usage
    DB_URL = os.getenv("DATABASE_URL", "postgresql://localhost/regintel")
    API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

    conn = psycopg2.connect(DB_URL)

    # Create changes table if needed
    with conn.cursor() as cur:
        cur.execute(CHANGES_TABLE_SQL)
    conn.commit()

    engine = HAFeedEngine(conn, API_KEY)

    # Run for specific HAs or all
    changes = asyncio.run(engine.run_all(ha_codes=["FDA", "EMA", "MHRA"]))

    print(f"\n{'='*60}")
    print(f"Changes detected: {len(changes)}")
    for change, systems in changes:
        print(f"\n  [{change.urgency.upper()}] {change.ha_code}: {change.title}")
        print(f"  Regulation: {change.regulation_ref}")
        print(f"  Systems affected: {len(systems)}")
        print(f"  Deadline: {change.implementation_deadline}")
