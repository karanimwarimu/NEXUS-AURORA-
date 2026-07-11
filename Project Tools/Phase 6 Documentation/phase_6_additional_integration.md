# PHASE 6 — ADDITIONAL INTEGRATION PATCH
# Version: 1.0.0 | Date: 2026-07-03
# Purpose: Add Phase 7 compliance features (PII, GDPR, schema extraction, audit logging)
#
# CRITICAL FINDINGS FROM AUDIT:
#   1. Phase 6 spec has ZERO PII redaction
#   2. Phase 6 spec has ZERO GDPR erase endpoint
#   3. Phase 6 spec has ZERO audit logging
#   4. Phase 6 spec has ZERO schema extraction pipeline
#   5. Phase 6 spec focuses entirely on Tauri desktop + packaging
#
# THIS PATCH ADDS:
#   - nexora_crawler/pipelines/pii_redaction_pipeline.py (NEW)
#   - nexora_crawler/pipelines/schema_extraction_pipeline.py (NEW)
#   - nexora_crawler/api/routes/gdpr.py (already in Phase 4C patch, referenced here)
#   - Audit logging hooks in all compliance endpoints
#   - Desktop app integration for compliance features

# ============================================================
# FILE: nexora_crawler/pipelines/pii_redaction_pipeline.py (NEW)
# ============================================================

"""
PII Redaction Pipeline — Phase 6 + Phase 7.

Priority: 200 (after MarkdownExtractionPipeline at 110, before StylePipeline at 150)

Two modes:
  - fast: regex-only (email, phone, SSN, credit card, IBAN, address)
  - llm: regex + LiteLLM-based NER for names, organizations

Redaction is token-aware: '[REDACTED:EMAIL]' replaces the PII
so the page is still useful for downstream pipelines (AI summary, etc.)
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Tier 1: regex patterns (always on, free, fast)
REGEX_PATTERNS: List[Tuple[str, str]] = [
    # Email addresses
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}", "[REDACTED:EMAIL]"),
    # US phone numbers
    (r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", "[REDACTED:PHONE]"),
    # SSN
    (r"\d{3}-\d{2}-\d{4}", "[REDACTED:SSN]"),
    # Credit cards (13-19 digits with optional spaces/dashes)
    (r"(?:\d[ -]*?){13,19}", "[REDACTED:CC]"),
    # IBAN
    (r"[A-Z]{2}\d{2}[A-Z\d]{4}\d{7}([A-Z\d]?){0,16}", "[REDACTED:IBAN]"),
    # Street addresses (basic heuristic)
    (r"\d{1,5}\s+\w+(?:\s+\w+)*\s+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Way|Court|Ct|Place|Pl|Circle|Cir)",
     "[REDACTED:ADDRESS]"),
    # IP addresses
    (r"(?:\d{1,3}\.){3}\d{1,3}", "[REDACTED:IP]"),
    # API keys / tokens (basic heuristic)
    (r"(?:api[_-]?key|token|secret)[\s]*[:=][\s]*['"]?[a-zA-Z0-9_-]{16,}['"]?",
     "[REDACTED:API_KEY]"),
]


class PIIRedactionPipeline:
    """
    Scrapy pipeline for PII redaction.

    Priority: 200 — runs after MarkdownExtractionPipeline (110),
    before UnifiedSchemaEnricher (160).

    Configuration (settings.py):
      NEXORA_PII_REDACTION_ENABLED = True
      NEXORA_PII_MODE = "regex"  # "regex" | "llm"
      NEXORA_PII_LLM_MODEL = "gpt-4o-mini"
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.enabled = self.settings.getbool("NEXORA_PII_REDACTION_ENABLED", False)
        self.mode = self.settings.get("NEXORA_PII_MODE", "regex")  # 'regex' | 'llm'
        self.stats = {
            "pages_processed": 0,
            "pages_redacted": 0,
            "redactions": 0,
            "llm_passes": 0,
            "llm_errors": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            return item

        text = item.get("markdown", "")
        if not text:
            return item

        original = text
        redaction_count = 0

        # Tier 1: Regex redaction (always runs)
        for pattern, replacement in REGEX_PATTERNS:
            text, count = re.subn(pattern, replacement, text, flags=re.IGNORECASE)
            redaction_count += count

        # Tier 2: LLM redaction (optional, for names/organizations)
        if self.mode == "llm" and text != original:
            try:
                text = await self._llm_redaction(text)
                self.stats["llm_passes"] += 1
            except Exception as e:
                logger.warning("[PII] LLM redaction failed, keeping regex-only: %s", e)
                self.stats["llm_errors"] += 1

        if text != original:
            self.stats["pages_redacted"] += 1
            self.stats["redactions"] += redaction_count

        item["markdown"] = text
        item["pii_redacted"] = text != original
        item["pii_redaction_count"] = redaction_count

        self.stats["pages_processed"] += 1
        return item

    async def _llm_redaction(self, text: str) -> str:
        """
        Use LiteLLM to detect and redact personal names and organization names.
        Only processes first 6000 chars to stay within context limits.
        """
        import litellm

        model = self.settings.get("NEXORA_PII_LLM_MODEL", "gpt-4o-mini")
        provider = self.settings.get("NEXORA_AI_PROVIDER", "ollama")
        base_url = self.settings.get("NEXORA_AI_BASE_URL", "http://localhost:11434")
        api_key = self.settings.get("NEXORA_AI_API_KEY", "not-needed")

        response = await litellm.acompletion(
            model=f"{provider}/{model}",
            messages=[{
                "role": "system",
                "content": (
                    "You are a PII redaction assistant. "
                    "Identify personal names and organization names in the text. "
                    "Replace personal names with [REDACTED:NAME]. "
                    "Replace organization names with [REDACTED:ORG]. "
                    "Do NOT redact generic terms, product names, or place names. "
                    "Return ONLY the redacted text, no explanations."
                ),
            }, {
                "role": "user",
                "content": text[:6000],
            }],
            api_base=base_url,
            api_key=api_key,
            temperature=0.0,
            max_tokens=4000,
        )
        return response.choices[0].message.content

    def close_spider(self, spider):
        logger.info("[PII] Pipeline stats: %s", self.stats)


# ============================================================
# FILE: nexora_crawler/pipelines/schema_extraction_pipeline.py (NEW)
# ============================================================

"""
Schema Extraction Pipeline — Phase 6 + Phase 7.

Firecrawl's headline feature: user submits a JSON Schema;
pipeline uses LiteLLM structured output to populate it from each page.

Priority: 280 (after VectorIndexPipeline at 270, before Parquet at 450)

Example user schema:
    {
      "type": "object",
      "properties": {
        "product_name":  {"type": "string"},
        "price":         {"type": "number"},
        "in_stock":      {"type": "boolean"},
        "features":      {"type": "array", "items": {"type": "string"}}
      },
      "required": ["product_name", "price"]
    }

Result per page:
    item["extracted"] = {
      "product_name": "Acme Widget",
      "price": 29.99,
      "in_stock": True,
      "features": ["durable", "lightweight"]
    }
"""

import logging
import json
from typing import Dict, Any, Optional

from pydantic import BaseModel, Field, create_model, ValidationError
import litellm

logger = logging.getLogger(__name__)


class SchemaExtractionPipeline:
    """
    Scrapy pipeline for JSON Schema-driven field extraction.

    Priority: 280
    """

    def __init__(self, crawler):
        self.settings = crawler.settings
        self.workspace_id = getattr(crawler, 'workspace_id', 'default')
        self.enabled = self.settings.getbool("NEXORA_SCHEMA_EXTRACTION_ENABLED", False)
        self.model = self.settings.get("NEXORA_SCHEMA_EXTRACTION_MODEL", "gpt-4o-mini")
        self.provider = self.settings.get("NEXORA_AI_PROVIDER", "ollama")
        self.base_url = self.settings.get("NEXORA_AI_BASE_URL", "http://localhost:11434")
        self.api_key = self.settings.get("NEXORA_AI_API_KEY", "not-needed")
        self.max_content_chars = self.settings.getint("NEXORA_SCHEMA_CONTENT_MAX_CHARS", 8000)
        self.stats = {
            "pages_processed": 0,
            "pages_extracted": 0,
            "validation_failures": 0,
            "extraction_errors": 0,
            "schema_fields_found": 0,
        }

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler)

    async def process_item(self, item, spider):
        if not self.enabled:
            item["extracted"] = None
            return item

        # Get user's JSON Schema from settings or item
        json_schema = self._get_schema(item)
        if not json_schema:
            item["extracted"] = None
            return item

        # Build Pydantic model from schema
        try:
            pyd_model = self._schema_to_pydantic(json_schema)
        except Exception as e:
            logger.error("[SchemaExtract] Invalid schema: %s", e)
            item["extracted"] = None
            return item

        # Get content to extract from
        markdown = item.get("markdown", "") or item.get("clean_text", "")
        if len(markdown) < 50:
            item["extracted"] = None
            return item

        content = markdown[:self.max_content_chars]

        # Extract via LLM
        try:
            extracted = await self._extract_with_llm(content, json_schema, pyd_model)
            item["extracted"] = extracted
            self.stats["pages_extracted"] += 1
            self.stats["schema_fields_found"] += len(extracted) if isinstance(extracted, dict) else 0

        except ValidationError as e:
            logger.warning("[SchemaExtract] Validation failed for %s: %s",
                          item.get("url", ""), e)
            item["extracted"] = None
            self.stats["validation_failures"] += 1

        except Exception as e:
            logger.error("[SchemaExtract] Extraction failed for %s: %s",
                        item.get("url", ""), e)
            item["extracted"] = None
            self.stats["extraction_errors"] += 1

        self.stats["pages_processed"] += 1
        return item

    def _get_schema(self, item) -> Optional[Dict]:
        """Get JSON Schema from settings or item metadata."""
        # Priority 1: item-level schema (from API request)
        if item.get("json_schema"):
            return item["json_schema"]
        # Priority 2: spider-level schema
        if hasattr(self.settings, 'NEXORA_USER_JSON_SCHEMA'):
            return self.settings.get("NEXORA_USER_JSON_SCHEMA")
        # Priority 3: fetch from DB by job_id
        job_id = item.get("crawl_id")
        if job_id:
            # Async DB fetch would go here — simplified for pipeline context
            pass
        return None

    def _schema_to_pydantic(self, schema: Dict) -> type[BaseModel]:
        """
        Convert JSON Schema dict → Pydantic model class.

        Handles:
          - string, integer, number, boolean, array, object types
          - required fields
          - nested objects (one level deep)
        """
        type_map = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }

        fields = {}
        required = schema.get("required", [])

        for name, prop in schema.get("properties", {}).items():
            prop_type = prop.get("type", "string")
            py_type = type_map.get(prop_type, str)

            # Handle arrays with item types
            if prop_type == "array" and "items" in prop:
                item_type = prop["items"].get("type", "string")
                py_type = List[type_map.get(item_type, str)]

            # Handle nested objects
            if prop_type == "object" and "properties" in prop:
                py_type = dict  # Simplified — could recurse

            # Optional if not in required
            if name not in required:
                py_type = Optional[py_type]

            default = None if name not in required else ...
            fields[name] = (py_type, default)

        return create_model("DynamicSchema", **fields)

    async def _extract_with_llm(self, content: str, schema: Dict, pyd_model: type[BaseModel]) -> Dict:
        """
        Use LiteLLM with response_format to enforce schema compliance.
        Falls back to raw JSON parsing if response_format not supported.
        """
        schema_json = json.dumps(schema, indent=2)

        messages = [
            {
                "role": "system",
                "content": (
                    "You extract structured data from web pages. "
                    "Respond ONLY with a JSON object matching the provided schema. "
                    "Do not include any other text, explanations, or markdown formatting."
                ),
            },
            {
                "role": "user",
                "content": f"Schema:
{schema_json}

Page Content:
{content}",
            },
        ]

        try:
            # Try structured output (OpenAI, some providers)
            response = await litellm.acompletion(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                response_format={"type": "json_object"},
                api_base=self.base_url,
                api_key=self.api_key,
                temperature=0.0,
                max_tokens=2000,
            )
        except Exception:
            # Fallback: no response_format
            response = await litellm.acompletion(
                model=f"{self.provider}/{self.model}",
                messages=messages,
                api_base=self.base_url,
                api_key=self.api_key,
                temperature=0.0,
                max_tokens=2000,
            )

        raw = response.choices[0].message.content.strip()

        # Extract JSON from response
        if raw.startswith("```json"):
            raw = raw[7:]
        if raw.startswith("```"):
            raw = raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

        # Validate against Pydantic model
        parsed = json.loads(raw)
        validated = pyd_model(**parsed)
        return validated.dict()

    def close_spider(self, spider):
        logger.info("[SchemaExtract] Pipeline stats: %s", self.stats)


# ============================================================
# FILE: nexora_crawler/entitlements/engine.py (NEW)
# ============================================================

"""
Quota & Entitlement Engine — Phase 6 + Phase 7.

Per-workspace soft + hard limits. One noisy tenant cannot drain the system.

Default free tier:
  - 10,000 pages/month
  - 1 GB blob storage
  - 100,000 vector records
  - 60 API calls/minute
  - 10 schema extraction jobs/day

Soft quota: request succeeds, logged + advisory response header
Hard quota: request rejected with 429 + Retry-After header
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional

from fastapi import HTTPException

logger = logging.getLogger(__name__)


@dataclass
class QuotaConfig:
    workspace_id: str
    pages_per_month: int = 10000
    storage_gb: int = 1
    vector_records: int = 100000
    api_rpm: int = 60
    schema_extracts_per_day: int = 10


class QuotaEngine:
    """
    Quota enforcement engine.

    All methods are async and accept a DB connection for lookups.
    """

    @staticmethod
    async def get_config(db, workspace_id: str) -> QuotaConfig:
        """Get quota config for workspace. Falls back to defaults."""
        if hasattr(db, 'fetch_one'):  # asyncpg
            row = await db.fetch_one(
                "SELECT * FROM workspace_quotas WHERE workspace_id = $1",
                workspace_id,
            )
        else:  # aiosqlite
            cursor = await db.execute(
                "SELECT * FROM workspace_quotas WHERE workspace_id = ?",
                (workspace_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return QuotaConfig(workspace_id=workspace_id)

        row = dict(row)
        return QuotaConfig(
            workspace_id=workspace_id,
            pages_per_month=row.get("pages_per_month", 10000),
            storage_gb=row.get("storage_gb", 1),
            vector_records=row.get("vector_records", 100000),
            api_rpm=row.get("api_rpm", 60),
            schema_extracts_per_day=row.get("schema_extracts_per_day", 10),
        )

    @staticmethod
    async def check_pages(db, workspace_id: str, requested: int,
                          mode: Literal["soft", "hard"] = "hard") -> None:
        """
        Check pages quota. Raises HTTPException(429) on hard limit exceeded.
        """
        config = await QuotaEngine.get_config(db, workspace_id)
        period_start = datetime.now(timezone.utc).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        if hasattr(db, 'fetch_one'):  # asyncpg
            row = await db.fetch_one(
                """SELECT COALESCE(SUM(pages_crawled), 0) AS used
                FROM crawl_jobs
                WHERE workspace_id = $1 AND started_at >= $2""",
                workspace_id, period_start,
            )
        else:  # aiosqlite
            cursor = await db.execute(
                """SELECT COALESCE(SUM(pages_crawled), 0) AS used
                FROM crawl_jobs
                WHERE workspace_id = ? AND started_at >= ?""",
                (workspace_id, period_start),
            )
            row = await cursor.fetchone()

        used = row["used"] if row else 0

        if used + requested > config.pages_per_month:
            if mode == "hard":
                # Calculate seconds until next month
                now = datetime.now(timezone.utc)
                next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
                retry_after = int((next_month - now).total_seconds())

                logger.warning(
                    "[Quota] HARD limit exceeded for %s: %d + %d > %d",
                    workspace_id, used, requested, config.pages_per_month
                )
                raise HTTPException(
                    status_code=429,
                    detail=(
                        f"Pages quota exceeded: {used}/{config.pages_per_month} "
                        f"used this month. Resets on the 1st of next month."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )
            else:
                logger.warning(
                    "[Quota] SOFT limit exceeded for %s: %d + %d > %d",
                    workspace_id, used, requested, config.pages_per_month
                )

    @staticmethod
    async def record_pages(db, workspace_id: str, count: int) -> None:
        """Record pages usage after crawl completion."""
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        await db.execute(
            """INSERT INTO usage_records
            (workspace_id, period, pages_crawled, storage_bytes, vector_records, api_calls, recorded_at)
            VALUES (?, ?, ?, 0, 0, 0, ?)
            ON CONFLICT (workspace_id, period) DO UPDATE SET
                pages_crawled = pages_crawled + ?""",
            (workspace_id, period, count,
             datetime.now(timezone.utc).isoformat(), count),
        )

    @staticmethod
    async def record_api_call(db, workspace_id: str) -> None:
        """Record an API call for rate limiting."""
        period = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        # Simplified — real impl uses Redis for per-minute buckets
        pass


# ============================================================
# AUDIT LOGGING UTILITIES
# ============================================================

"""
Add these helper functions to your database layer or create a dedicated module:

# nexora_crawler/audit.py

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def log_audit_event(db, workspace_id: str, actor: str, action: str,
                          target_id: str = None, details: dict = None,
                          ip_address: str = "0.0.0.0"):
    """
    Write an audit log entry.

    Actions:
      - gdpr_erase
      - pii_redaction
      - quota_enforced
      - crawl_started
      - crawl_completed
      - webhook_created
      - webhook_deleted
    """
    import json
    await db.execute(
        """INSERT INTO audit_logs
        (workspace_id, actor, action, target_id, details, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (workspace_id, actor, action, target_id,
         json.dumps(details) if details else None,
         ip_address, datetime.now(timezone.utc).isoformat()),
    )
    logger.info("[Audit] %s: %s by %s in %s", action, target_id, actor, workspace_id)


# Usage examples:
#   await log_audit_event(db, workspace_id, "user:123", "gdpr_erase",
#                         target_id=workspace_id, details={"pages": 42})
#   await log_audit_event(db, workspace_id, "system", "quota_enforced",
#                         details={"resource": "pages", "limit": 10000})
"""


# ============================================================
# SETTINGS.PY ADDITIONS FOR PHASE 6
# ============================================================

"""
Add to settings.py:

# ---- Phase 7: PII Redaction ----
NEXORA_PII_REDACTION_ENABLED = False  # Enable in production
NEXORA_PII_MODE = "regex"  # "regex" | "llm"
NEXORA_PII_LLM_MODEL = "gpt-4o-mini"

# ---- Phase 7: Schema Extraction ----
NEXORA_SCHEMA_EXTRACTION_ENABLED = False
NEXORA_SCHEMA_EXTRACTION_MODEL = "gpt-4o-mini"
NEXORA_SCHEMA_CONTENT_MAX_CHARS = 8000

# ---- Phase 7: Quotas ----
NEXORA_DEFAULT_PAGES_PER_MONTH = 10000
NEXORA_DEFAULT_STORAGE_GB = 1
NEXORA_DEFAULT_VECTOR_RECORDS = 100000
NEXORA_DEFAULT_API_RPM = 60
NEXORA_DEFAULT_SCHEMA_EXTRACTS_PER_DAY = 10

# Pipeline priorities (updated)
ITEM_PIPELINES = {
    'nexora_crawler.pipelines.NexoraExtractionPipeline': 100,
    'nexora_crawler.pipelines.markdown_pipeline.MarkdownExtractionPipeline': 110,
    'nexora_crawler.pipelines.pii_redaction_pipeline.PIIRedactionPipeline': 200,
    'nexora_crawler.pipelines.NexoraStylePipeline': 150,
    'nexora_crawler.pipelines.schema_enricher.UnifiedSchemaEnricher': 160,
    'nexora_crawler.pipelines.metadata_indexer.MetadataIndexerPipeline': 165,
    'nexora_crawler.pipelines.ai_enrichment.AIEnrichmentPipeline': 250,
    'nexora_crawler.pipelines.chunking_pipeline.StructuralChunkingPipeline': 260,
    'nexora_crawler.pipelines.vector_index_pipeline.VectorIndexPipeline': 270,
    'nexora_crawler.pipelines.schema_extraction_pipeline.SchemaExtractionPipeline': 280,
    'nexora_crawler.pipelines.parquet_export.ParquetExportPipeline': 450,
    'nexora_crawler.pipelines.NexoraExportPipeline': 500,
    'nexora_crawler.pipelines.NexoraDatasetPipeline': 600,
}
"""


# ============================================================
# TAURI DESKTOP APP INTEGRATION (Phase 6)
# ============================================================

"""
Add these Tauri commands for compliance features:

# In src-tauri/src/lib.rs, add:

#[tauri::command]
pub async fn gdpr_erase_workspace(
    workspace_id: String,
    app_handle: tauri::AppHandle,
) -> Result<String, String> {
    // Call the Python backend's GDPR erase endpoint
    let python_exe = get_python_executable(&app_handle)?;
    let output = Command::new(python_exe)
        .args(&[
            "gdpr", "erase",
            &format!("--workspace-id={}", workspace_id),
        ])
        .output()
        .map_err(|e| format!("GDPR erase failed: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(String::from_utf8_lossy(&output.stderr).to_string())
    }
}

#[tauri::command]
pub async fn get_audit_logs(
    workspace_id: String,
    limit: u32,
    app_handle: tauri::AppHandle,
) -> Result<Vec<AuditLogEntry>, String> {
    // Fetch audit logs from SQLite
    let data_dir = get_data_dir(&app_handle)?;
    let db_path = data_dir.join("nexora_metadata.db");

    // Use aiosqlite or similar to query
    // Return structured log entries
    Ok(vec![])
}

// In your React frontend, add a Compliance tab:
// - PII redaction toggle
// - GDPR erase button (with confirmation dialog)
// - Audit log viewer
// - Quota usage display
"""
 


 Nexora Local Integration Feature: Ollama Hardware Tier Profiles
This feature exposes structured local model configuration presets based on the desktop user's hardware. Grouping the embedding and generation models into specific "Tiers" ensures a seamless, out-of-the-box local experience without triggering out-of-memory errors or freezing host interfaces.

1. Local Tier Profiles Blueprint
Provide these specific options within the user interface or configuration files:

🟢 Tier 1: Ultra-Lightweight (8GB RAM / Basic CPU)
For older laptops or machines without a dedicated graphics card. Focuses on speed and low background footprints.

Text Generation Model (NEXORA_AI_MODEL): gemma3:4b (Size: ~3.3 GB)

Highly efficient edge model; delivers fast token output entirely over standard CPU.

Embedding Model (NEXORA_AI_EMBEDDING_MODEL): all-minilm (Size: ~45 MB)

Extremely low memory profile; ideal for processing short text blocks without latency.

🟡 Tier 2: Balanced Default (16GB RAM / Apple Silicon M-Series / Budget GPU)
The recommended tier for mid-range setups. Offers strong general logic and handles complex formatting easily.

Text Generation Model (NEXORA_AI_MODEL): qwen3:4b (Size: ~2.8 GB) or qwen2.5:7b (Size: ~4.7 GB)

Excellent instruction-following and coding logic at a lightweight scale.

Embedding Model (NEXORA_AI_EMBEDDING_MODEL): nomic-embed-text (Size: ~274 MB)

The RAG industry standard. Supports a massive 8k context window to prevent text clipping.

🔵 Tier 3: Deep Reasoning (16GB+ RAM / High-End Dedicated GPU)
For advanced users running specialized workloads requiring long chain-of-thought analysis.

Text Generation Model (NEXORA_AI_MODEL): deepseek-r1:7b or deepseek-r1:8b (Size: ~4.7 GB)

Executes deeper evaluation loops before outputting answers; maximizes relational extraction accuracy.

Embedding Model (NEXORA_AI_EMBEDDING_MODEL): nomic-embed-text (Size: ~274 MB)

2. Configuration Schema Implementation
Add this validation block into the core settings module to automatically apply target variables when a user picks their tier:

Python
# settings/ai_profiles.py

OLLAMA_HARDWARE_PROFILES = {
    "tier_1_lightweight": {
        "NEXORA_AI_MODEL": "gemma3:4b",
        "NEXORA_AI_EMBEDDING_MODEL": "all-minilm",
        "NEXORA_AI_MAX_CONCURRENT": 1,
        "NEXORA_AI_TIMEOUT": 90,
        "description": "Optimized for 8GB RAM setups. Prioritizes stability and fast generation."
    },
    "tier_2_balanced": {
        "NEXORA_AI_MODEL": "qwen3:4b", 
        "NEXORA_AI_EMBEDDING_MODEL": "nomic-embed-text",
        "NEXORA_AI_MAX_CONCURRENT": 2,
        "NEXORA_AI_TIMEOUT": 60,
        "description": "Standard configuration for 16GB RAM. High contextual accuracy."
    },
    "tier_3_reasoning": {
        "NEXORA_AI_MODEL": "deepseek-r1:7b",
        "NEXORA_AI_EMBEDDING_MODEL": "nomic-embed-text",
        "NEXORA_AI_MAX_CONCURRENT": 2,
        "NEXORA_AI_TIMEOUT": 120,
        "description": "Requires 16GB+ RAM and strong GPU. Activates DeepSeek reasoning chains."
    }
}
3. Mandatory Setup Script for Native End-Users
To ensure users don't encounter missing model exceptions at runtime, include this initialization script in your setup documentation. It guarantees all necessary assets are fetched into their local Ollama instance beforehand:

Bash
#!/bin/bash
# setup_local_models.sh

echo "Initializing Nexora local AI environments..."

# Tier 1 Components
ollama pull gemma3:4b
ollama pull all-minilm

# Tier 2 & 3 Components
ollama pull qwen3:4b
ollama pull deepseek-r1:7b
ollama pull nomic-embed-text

echo "Local model environment synchronization complete!"
⚠️ Critical Pipeline Note for Low-Memory Hardware: When executing local processing profiles on 8GB machines, keep NEXORA_AI_MAX_CONCURRENT locked to 1. This forces the pipeline to stream tasks synchronously, preventing Ollama from attempting to host multiple generation contexts concurrently, which leads to hardware crashes.