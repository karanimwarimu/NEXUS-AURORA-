"""
nexora_crawler/api/__init__.py
================================
FastAPI wrapper + interactive CLI runner for Nexora crawler.

This module doubles as:
  - The FastAPI application (imported by uvicorn)
  - The CLI entrypoint (executed via `python -m nexora_crawler.api`)

Usage:
  # FastAPI server mode (runs indefinitely, press Ctrl+C to stop)
  python -m nexora_crawler.api --server
  uvicorn nexora_crawler.api:app --reload --port 8000

  # Interactive CLI mode (prompts for input, runs once, exits)
  python -m nexora_crawler.api

  # Direct command (no prompts, for scripting)
  python -m nexora_crawler.api --url "https://example.com" --strategy whole-website

  # Or via Scrapy command (existing)
  scrapy crawl nexora -a urls="https://example.com" -a strategy="whole-website"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

# Ensure the project root is on sys.path for `python api.py` direct execution
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Ensure project settings are loaded
import nexora_crawler.settings  # noqa: F401


# ── Logging ────────────────────────────────────────────────────────────────
# Avoid duplicate handlers when Scrapy/uvicorn configure logging.
log = logging.getLogger("nexora.api")
log.propagate = False  # Prevent duplicate log entries from root logger
if not log.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    log.addHandler(handler)
log.setLevel(logging.INFO)


# ── Enrichment mode helper ─────────────────────────────────────────────────
# Mirrors the gate in settings.py: "eager" runs enrichment inline during the
# crawl; "on_demand" defers it to the offline `enrich.py` command.
_VALID_ENRICH_MODES = ("eager", "on_demand")


def _normalize_enrich_mode(mode) -> str | None:
    """Return a valid enrichment mode string, or None to use the default."""
    if mode and str(mode).lower() in _VALID_ENRICH_MODES:
        return str(mode).lower()
    return None


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
    max_pages: int = Field(default=100, ge=1, le=50000, description="Safety cap on pages")
    enrich_mode: Literal["eager", "on_demand"] | None = Field(
        default=None,
        description=(
            "When AI enrichment (summary/tags/vectors) runs. "
            "'eager' = inline during the crawl; 'on_demand' = deferred to the "
            "offline `enrich.py` command. Omit to use the server default."
        ),
    )
    workspace_id: str = Field(
        default="default",
        description="Workspace identifier for multi-tenancy",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://www.bbc.com",
                "strategy": "whole-website",
                "max_pages": 500,
            }
        }
    )


class CrawlResponse(BaseModel):
    """Crawl execution response."""
    job_id: str
    status: str
    url: str
    strategy: str
    mode: str
    enrich_mode: str | None = None
    pages_crawled: int
    output_dir: str
    started_at: str
    completed_at: str | None = None
    message: str
    workspace_id: str = "default"


# ── In-memory job store (replace with Redis/DB in production) ──────────────

_jobs: dict[str, CrawlResponse] = {}


# ── FastAPI App ────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    log.info("🚀 Nexora API starting up...")
    # Ensure the live metadata database is migrated to the current schema.
    # This is a no-op on fresh databases and safe to call on every boot.
    try:
        from nexora_crawler.storage.local_sqlite import MetadataStore
        MetadataStore()
        log.info("✅ Database schema migration verified")
    except Exception as exc:
        log.error("❌ Database migration failed: %s", exc)
    yield
    log.info("🛑 Nexora API shutting down...")


app = FastAPI(
    title="Nexora Crawler API",
    description="Automated web crawling with depth strategy mapping and sitemap auto-detection",
    version="4.5.0",
    lifespan=lifespan,
)

# CORS — allow origins from settings (NEXORA_CORS_ORIGINS) or fall back to local dev defaults
import json as _json
_cors_origins = _json.loads(os.getenv("NEXORA_CORS_ORIGINS", '["http://localhost:3000", "http://localhost:1420", "http://localhost:8000"]'))
if isinstance(_cors_origins, str):
    _cors_origins = [_cors_origins]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 4C routers
from nexora_crawler.api.routes import search, webhooks, jobs, gdpr, extract, health, auth  # noqa: E402
app.include_router(search.router)
app.include_router(webhooks.router)
app.include_router(jobs.router)
app.include_router(gdpr.router)
app.include_router(extract.router)
app.include_router(health.router)
app.include_router(auth.router)


@app.get("/")
async def root():
    return {
        "service": "Nexora Crawler",
        "version": "4.5.0",
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
        enrich_mode=request.enrich_mode,
        pages_crawled=0,
        output_dir="output/",
        started_at=datetime.now().isoformat(),
        message=f"Crawl started with strategy '{request.strategy}'",
        workspace_id=request.workspace_id,
    )
    _jobs[job_id] = job

    # Run crawl in background (non-blocking)
    asyncio.create_task(
        _run_crawl(job_id, url_str, request.strategy, request.max_pages, request.enrich_mode, request.workspace_id)
    )

    return job


@app.get("/crawl/{job_id}", response_model=CrawlResponse)
async def get_job(job_id: str):
    """Get crawl job status."""
    if job_id not in _jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return _jobs[job_id]


@app.get("/jobs")
async def list_jobs(workspace_id: str = "default"):
    """List crawl jobs, optionally filtered by workspace."""
    if workspace_id == "default":
        return {"jobs": list(_jobs.values())}
    return {"jobs": [j for j in _jobs.values() if j.workspace_id == workspace_id]}
    return {"jobs": [j for j in _jobs.values() if getattr(j, "workspace_id", "default") == workspace_id]}


# ── Internal Crawl Runner ──────────────────────────────────────────────────

async def _run_crawl(job_id: str, url: str, strategy: str, max_pages: int,
                    enrich_mode: str | None = None, workspace_id: str = "default"):
    """Execute a Scrapy crawl as an isolated subprocess.

    Runs each job in its own process so:
      - a crash in one crawl can't take down the API server,
      - repeated jobs work (Twisted's reactor can only start once per process),
      - logs stream live to the server console.

    The api package is invoked via `python -m nexora_crawler.api` with
    _PROJECT_ROOT on PYTHONPATH so the nexora_crawler package resolves from
    any working directory.
    """
    import subprocess
    import sys

    job = _jobs[job_id]
    log.info("[%s] Starting crawl: %s | strategy=%s | enrich_mode=%s | workspace=%s",
             job_id, url, strategy, enrich_mode, workspace_id)

    api_script = os.path.join(_PROJECT_ROOT, "nexora_crawler", "__main__.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    # Forward the chosen enrichment mode into the child process. The child
    # re-imports settings.py, which reads NEXORA_ENRICH_MODE at import time.
    _norm = _normalize_enrich_mode(enrich_mode)
    if _norm:
        env["NEXORA_ENRICH_MODE"] = _norm
    env["NEXORA_WORKSPACE_ID"] = workspace_id

    cmd = [
        sys.executable, api_script,
        "--url", url, "--strategy", strategy, "--max-pages", str(max_pages),
        "--workspace-id", workspace_id,
    ]
    if _norm:
        cmd += ["--enrich-mode", _norm]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        job.completed_at = datetime.now().isoformat()
        if proc.returncode == 0:
            job.status = "completed"
            job.message = "Crawl completed successfully"
        else:
            job.status = "failed"
            job.message = f"Crawl exited with code {proc.returncode}"
        log.info("[%s] Crawl finished (code=%s)", job_id, proc.returncode)

    except Exception as exc:
        job.status = "failed"
        job.completed_at = datetime.now().isoformat()
        job.message = f"Crawl failed: {exc}"
        log.error("[%s] Crawl failed: %s", job_id, exc)


# ── Strategy Definitions ───────────────────────────────────────────────────

STRATEGY_MAP = {
    "single-page":   {"depth": 0, "mode": "single-page", "auto_sitemap": False, "domain_lock": False},
    "linked-pages":  {"depth": 1, "mode": "multi-page",  "auto_sitemap": False, "domain_lock": False},
    "whole-website": {"depth": 3, "mode": "auto",        "auto_sitemap": True,  "domain_lock": True},
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
        "name": "Whole website",
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
    +---------------------------------------------------------------+
    |                                                               |
    |   Automated Web Crawler — Phase 2.6                          |
    |                                                               |
    +---------------------------------------------------------------+
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


def _run_crawl_subprocess(url: str, strategy: str, max_pages: int,
                           enrich_mode: str | None = None, workspace_id: str = "default") -> int:
    """
    Run a single crawl in a *separate process* (fresh Twisted reactor each time).

    Why a subprocess: Scrapy's Twisted reactor can only be started once per
    process, and a crash inside an in-process crawl would kill this loop/server.
    Isolating each crawl means a finished or failed task never terminates the
    parent, and repeated runs work cleanly.

    Path handling: we run the api.py script directly and inject _PROJECT_ROOT
    into PYTHONPATH so the nexora_crawler package is importable regardless of
    the current working directory the parent was launched from.
    """
    import subprocess
    import sys

    api_script = os.path.join(_PROJECT_ROOT, "nexora_crawler", "__main__.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = _PROJECT_ROOT + os.pathsep + env.get("PYTHONPATH", "")
    # Forward the chosen enrichment mode. The child re-imports settings.py,
    # which reads NEXORA_ENRICH_MODE at import time.
    _norm = _normalize_enrich_mode(enrich_mode)
    if _norm:
        env["NEXORA_ENRICH_MODE"] = _norm
    env["NEXORA_WORKSPACE_ID"] = workspace_id

    cmd = [
        sys.executable, api_script,
        "--url", url, "--strategy", strategy, "--max-pages", str(max_pages),
        "--workspace-id", workspace_id,
    ]
    if _norm:
        cmd += ["--enrich-mode", _norm]
    log.info("[cli] spawning crawl subprocess: %s (enrich_mode=%s, workspace=%s)", " ".join(cmd), _norm, workspace_id)
    result = subprocess.run(cmd, check=False, env=env)
    return result.returncode


def _prompt_enrich_mode() -> str | None:
    """Prompt for enrichment timing; Enter = use server default."""
    print("\n🧠 Enrichment mode (when AI summary/tags/vectors run):")
    print("   1. on_demand (default) — fast crawl, enrich later via `enrich.py`")
    print("   2. eager — enrich inline during the crawl (slower)")
    choice = input("Enter choice [1/2, blank=default]: ").strip()
    if choice == "2":
        return "eager"
    if choice == "1":
        return "on_demand"
    return None


def _prompt_workspace_id() -> str:
    """Prompt for workspace ID; Enter = default."""
    default = "default"
    user = input(f"\n🏢 Workspace ID [{default}]: ").strip()
    return user if user else default


def run_cli_interactive():
    """Interactive CLI REPL — prompt, crawl, then ask to run another.

    Each crawl runs in its own subprocess (see _run_crawl_subprocess), so a
    finished or failed task never terminates this loop. Ctrl+C to quit.
    """
    _print_banner()
    print("Interactive crawl loop — Ctrl+C to quit.\n")

    while True:
        try:
            url = _prompt_url()
            strategy = _prompt_strategy()
            max_pages = _prompt_max_pages()
            enrich_mode = _prompt_enrich_mode()
            workspace_id = _prompt_workspace_id()

            print(f"\n⚙️  Configuration:")
            print(f"   URL      : {url}")
            print(f"   Strategy : {STRATEGY_DESCRIPTIONS[strategy]['name']}")
            print(f"   Max pages: {max_pages}")
            print(f"   Workspace: {workspace_id}")
            print(f"   Enrich   : {enrich_mode or 'default (on_demand)'}")
            print(f"\n🚀 Starting crawl...\n")

            code = _run_crawl_subprocess(url, strategy, max_pages, enrich_mode, workspace_id)
            if code == 0:
                print("\n✅ Crawl finished. Check output/ directory for results.")
            else:
                print(f"\n❌ Crawl exited with errors (code {code}). See log above.")

        except KeyboardInterrupt:
            print("\n👋 Exiting Nexora.")
            break
        except Exception as exc:
            log.error("[cli] unexpected error: %s", exc)
            print(f"\n❌ Error: {exc}")

        again = input("\n🔁 Run another crawl? [y/N]: ").strip().lower()
        if again not in ("y", "yes"):
            print("👋 Goodbye.")
            break


def run_cli_direct(url: str, strategy: str, max_pages: int, enrich_mode: str | None = None, workspace_id: str = "default"):
    """Direct CLI entrypoint (no prompts, for scripting)."""
    # settings.py is imported at module load (before argparse reads --enrich-mode),
    # so re-evaluate it now that the env var is known. The subprocess paths don't
    # need this because the child re-imports settings with the inherited env.
    _norm = _normalize_enrich_mode(enrich_mode)
    if _norm:
        import importlib
        import nexora_crawler.settings as _settings_mod
        os.environ["NEXORA_ENRICH_MODE"] = _norm
        importlib.reload(_settings_mod)

    print(f"🚀 Starting crawl: {url}")
    print(f"   Strategy : {STRATEGY_DESCRIPTIONS[strategy]['name']}")
    print(f"   Max pages: {max_pages}")
    print(f"   Workspace: {workspace_id}")
    print(f"   Enrich   : {_norm or 'default (on_demand)'}\n")

    _run_crawl_sync(url, strategy, max_pages, workspace_id)

    print("\n✅ Crawl finished. Check output/ directory for results.")


def _run_crawl_sync(url: str, strategy: str, max_pages: int, workspace_id: str = "default"):
    """Synchronous crawl execution for CLI modes."""
    settings = get_project_settings()
    settings.set("LOG_LEVEL", "INFO")

    crawl_id = uuid.uuid4().hex
    process = CrawlerProcess(settings)
    process.crawl(
        "nexora",
        urls=url,
        strategy=strategy,
        max_pages=max_pages,
        crawl_id=crawl_id,
        workspace_id=workspace_id,
    )
    process.start()


# ── Entrypoint ─────────────────────────────────────────────────────────────

def main():
    """Main entrypoint — parses arguments and dispatches to correct mode."""
    parser = argparse.ArgumentParser(
        description="Nexora Crawler — CLI and API runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive CLI (prompts for input)
  python -m nexora_crawler.api

  # Direct CLI (no prompts)
  python -m nexora_crawler.api --url https://example.com --strategy whole-website

  # FastAPI server mode
  python -m nexora_crawler.api --server
  python -m nexora_crawler.api --server --host 0.0.0.0 --port 8080
        """,
    )

    parser.add_argument(
        "--server", action="store_true",
        help="Run as FastAPI server (default: interactive CLI)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0",
        help="Server host (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Server port (default: 8000)"
    )
    parser.add_argument(
        "--url",
        help="Target URL (direct CLI mode, skips prompts)"
    )
    parser.add_argument(
        "--strategy", default="single-page",
        choices=list(STRATEGY_MAP.keys()),
        help="Crawl strategy (default: single-page)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=1000,
        help="Max pages cap (default: 1000)"
    )
    parser.add_argument(
        "--enrich-mode", default=None, choices=list(_VALID_ENRICH_MODES),
        help="When AI enrichment runs: 'eager' inline, 'on_demand' deferred "
             "to enrich.py (default: server setting -> on_demand)"
    )
    parser.add_argument(
        "--workspace-id", default="default",
        help="Workspace identifier for multi-tenancy (default: default)"
    )

    args = parser.parse_args()

    # ── Mode 1: FastAPI Server ────────────────────────────────────────────
    if args.server:
        from nexora_crawler.settings import NEXORA_API_WORKERS
        print(f"""
    +---------------------------------------------------------------+
    |                                                               |
    |              Nexora Crawler API Server                        |
    |                                                               |
    |   Server: http://{args.host}:{args.port}                    |
    |   Docs:   http://{args.host}:{args.port}/docs               |
    |                                                               |
    |   Press Ctrl+C to stop                                        |
    +---------------------------------------------------------------+
        """)
        uvicorn.run(
            "nexora_crawler.api:app",
            host=args.host,
            port=args.port,
            workers=int(os.getenv("NEXORA_API_WORKERS", NEXORA_API_WORKERS)),
            reload=False,  # Disable reload for stability
            log_level="info",
        )
        return

    # ── Mode 2: Direct CLI (no prompts) ──────────────────────────────────
    if args.url:
        run_cli_direct(args.url, args.strategy, args.max_pages, args.enrich_mode, args.workspace_id)
        return

    # ── Mode 3: Interactive CLI (default) ────────────────────────────────
    run_cli_interactive()
