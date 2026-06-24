"""
nexora_crawler/api.py
=====================
FastAPI wrapper + interactive CLI runner for Nexora crawler.

Usage:
  # FastAPI server mode
  uvicorn nexora_crawler.api:app --reload --port 8000

  # Interactive CLI mode (run directly)
  python -m nexora_crawler.api

  # Or via Scrapy command (existing)
  scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website"
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

# Ensure project settings are loaded
import nexora_crawler.settings  # noqa: F401


# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("nexora.api")


# ── Pydantic Models ────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    """User-facing crawl request."""
    url: HttpUrl = Field(..., description="Target website URL")
    strategy: Literal[
        "single-page",
        "linked-pages",
        "whole-website",
        "everything",
    ] = Field(default="single-page", description="Crawl depth strategy")
    max_pages: int = Field(default=1000, ge=1, le=50000, description="Safety cap on pages")

    class Config:
        json_schema_extra = {
            "example": {
                "url": "https://www.bbc.com",
                "strategy": "whole-website",
                "max_pages": 500,
            }
        }


class CrawlResponse(BaseModel):
    """Crawl execution response."""
    job_id: str
    status: str
    url: str
    strategy: str
    mode: str
    pages_crawled: int
    output_dir: str
    started_at: str
    completed_at: str | None = None
    message: str


# ── In-memory job store (replace with Redis/DB in production) ──────────────

_jobs: dict[str, CrawlResponse] = {}


# ── FastAPI App ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    log.info("🚀 Nexora API starting up...")
    yield
    log.info("🛑 Nexora API shutting down...")


app = FastAPI(
    title="Nexora Crawler API",
    description="Automated web crawling with depth strategy mapping and sitemap auto-detection",
    version="2.5.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "Nexora Crawler",
        "version": "2.5.0",
        "strategies": list(STRATEGY_DESCRIPTIONS.keys()),
    }


@app.get("/strategies")
async def list_strategies():
    """List available crawl strategies with descriptions."""
    return {
        "strategies": [
            {"id": k, "name": v["name"], "description": v["description"]}
            for k, v in STRATEGY_DESCRIPTIONS.items()
        ]
    }


@app.post("/crawl", response_model=CrawlResponse)
async def start_crawl(request: CrawlRequest):
    """Start a new crawl job."""
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(request):x}"
    url_str = str(request.url)

    # Validate URL is reachable
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.head(url_str, follow_redirects=True)
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=400,
                    detail=f"URL returned HTTP {resp.status_code}",
                )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=400, detail=f"URL unreachable: {exc}")

    # Resolve strategy to internal params
    strategy_cfg = STRATEGY_MAP.get(request.strategy, STRATEGY_MAP["single-page"])

    job = CrawlResponse(
        job_id=job_id,
        status="running",
        url=url_str,
        strategy=request.strategy,
        mode=strategy_cfg["mode"],
        pages_crawled=0,
        output_dir="output/",
        started_at=datetime.now().isoformat(),
        message=f"Crawl started with strategy '{request.strategy}'",
    )
    _jobs[job_id] = job

    # Run crawl in background (non-blocking)
    asyncio.create_task(_run_crawl(job_id, url_str, request.strategy, request.max_pages))

    return job


@app.get("/crawl/{job_id}", response_model=CrawlResponse)
async def get_job(job_id: str):
    """Get crawl job status."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/jobs")
async def list_jobs():
    """List all crawl jobs."""
    return {"jobs": list(_jobs.values())}


# ── Internal Crawl Runner ──────────────────────────────────────────────────

async def _run_crawl(job_id: str, url: str, strategy: str, max_pages: int):
    """Execute Scrapy crawl asynchronously."""
    job = _jobs[job_id]
    log.info("[%s] Starting crawl: %s | strategy=%s", job_id, url, strategy)

    try:
        # Build Scrapy settings
        settings = get_project_settings()
        settings.set("LOG_LEVEL", "INFO")

        process = CrawlerProcess(settings)
        process.crawl(
            "nexora",
            urls=url,
            strategy=strategy,
            max_pages=max_pages,
        )

        # Run in thread pool (Scrapy is synchronous internally)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, process.start, False)

        job.status = "completed"
        job.completed_at = datetime.now().isoformat()
        job.message = "Crawl completed successfully"
        log.info("[%s] Crawl completed", job_id)

    except Exception as exc:
        job.status = "failed"
        job.completed_at = datetime.now().isoformat()
        job.message = f"Crawl failed: {exc}"
        log.error("[%s] Crawl failed: %s", job_id, exc)


# ── Strategy Definitions ───────────────────────────────────────────────────

STRATEGY_MAP = {
    "single-page":   {"depth": 0, "mode": "single-page", "auto_sitemap": False, "domain_lock": False},
    "linked-pages":  {"depth": 1, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": False},
    "whole-website": {"depth": 3, "mode": "auto",        "auto_sitemap": True,  "domain_lock": False},
    "everything":    {"depth": 5, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": True},
}

STRATEGY_DESCRIPTIONS = {
    "single-page": {
        "name": "Just this page",
        "description": "Process only the exact seed URL. Fastest, lowest impact.",
    },
    "linked-pages": {
        "name": "This page + linked pages",
        "description": "Process seed URL plus all pages it directly links to.",
    },
    "whole-website": {
        "name": "The whole website",
        "description": "Auto-detect sitemap and crawl all URLs. Falls back to depth-3 link crawl.",
    },
    "everything": {
        "name": "Everything connected",
        "description": "Deep domain crawl (depth=5) locked to the seed domain. Most thorough.",
    },
}


# ── Interactive CLI ────────────────────────────────────────────────────────

def _print_banner():
    print(r"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║   ███╗   ██╗███████╗██╗  ██╗ ██████╗ ██████╗  █████╗        ║
    ║   ████╗  ██║██╔════╝╚██╗██╔╝██╔═══██╗██╔══██╗██╔══██╗       ║
    ║   ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║██████╔╝███████║       ║
    ║   ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║██╔══██╗██╔══██║       ║
    ║   ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝██║  ██║██║  ██║       ║
    ║   ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝       ║
    ║                                                               ║
    ║              Automated Web Crawler — Phase 2.5                ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)


def _prompt_url() -> str:
    while True:
        url = input("🌐 Enter target URL (e.g. https://example.com): ").strip()
        if url.startswith(("http://", "https://")):
            return url
        print("❌ Invalid URL. Must start with http:// or https://")


def _prompt_strategy() -> str:
    print("\n📊 Select crawl strategy:")
    for i, (key, val) in enumerate(STRATEGY_DESCRIPTIONS.items(), 1):
        print(f"   {i}. {val['name']}")
        print(f"      → {val['description']}")
    print()

    choices = list(STRATEGY_DESCRIPTIONS.keys())
    while True:
        choice = input("Enter choice (1-4): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= 4:
            return choices[int(choice) - 1]
        print("❌ Invalid choice. Enter 1, 2, 3, or 4.")


def _prompt_max_pages() -> int:
    default = 1000
    user = input(f"\n🔢 Max pages cap [{default}]: ").strip()
    if not user:
        return default
    try:
        val = int(user)
        if val < 1:
            print("❌ Must be at least 1. Using default.")
            return default
        return val
    except ValueError:
        print("❌ Invalid number. Using default.")
        return default


def run_cli():
    """Interactive CLI entrypoint."""
    _print_banner()

    url = _prompt_url()
    strategy = _prompt_strategy()
    max_pages = _prompt_max_pages()

    print(f"\n⚙️  Configuration:")
    print(f"   URL      : {url}")
    print(f"   Strategy : {STRATEGY_DESCRIPTIONS[strategy]['name']}")
    print(f"   Max pages: {max_pages}")
    print(f"\n🚀 Starting crawl...\n")

    # Run Scrapy via CrawlerProcess
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "INFO")

    process = CrawlerProcess(settings)
    process.crawl(
        "nexora",
        urls=url,
        strategy=strategy,
        max_pages=max_pages,
    )
    process.start()

    print("\n✅ Crawl finished. Check output/ directory for results.")


# ── Entrypoint ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # If --server flag passed, run FastAPI; otherwise run interactive CLI
    if len(sys.argv) > 1 and sys.argv[1] == "--server":
        uvicorn.run("nexora_crawler.api:app", host="0.0.0.0", port=8000, reload=True)
    else:
        run_cli()
