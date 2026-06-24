# Firecrawl Repository Overview

## Project structure

Firecrawl is a monorepo centered around the main API service, with several supporting apps and libraries.

### Top-level
- `apps/` — all runnable services, SDKs, test tools, and helper packages
- `examples/` — deployment / usage examples
- `docker-compose.yaml` — local self-hosted stack
- `README.md` — product overview and API examples
- `SELF_HOST.md` — self-hosting guide
- `.github/` — CI, deployment workflows, issue templates

### Main components under `apps/`
- `apps/api/` — the core Firecrawl backend API
- `apps/playwright-service-ts/` — browser automation / dynamic-page scraping service
- `apps/redis/` — Redis service used for queues/rate limiting
- `apps/nuq-postgres/` — Postgres service used by the queue system
- `apps/go-html-to-md-service/` or shared HTML→Markdown tooling
- `apps/js-sdk/` — JavaScript SDK
- `apps/python-sdk/` — Python SDK
- `apps/rust-sdk/` — Rust SDK
- `apps/test-suite/` — test and benchmark tooling
- `apps/test-site/` — test target site for crawling/scraping
- `apps/ui/` — internal UI pieces such as ingestion UI

## What they have achieved

Firecrawl is a web-crawling and scraping platform that:
- takes a URL and turns it into clean markdown or structured data
- crawls subpages without needing a sitemap
- supports scraping, crawling, mapping, searching, and extraction
- handles “hard” web targets with:
  - dynamic content / JavaScript rendering
  - proxies
  - anti-bot handling
  - batching
  - actions like click/scroll/input/wait
- exposes a public API plus hosted docs/playground
- provides SDKs for multiple languages and integrations with LLM/low-code ecosystems
- supports self-hosting via Docker Compose and Kubernetes examples

## Other tools that make up the whole thing

From the repo structure and package manifests, the system includes:

- **Core API service** (`apps/api`)
- **Playwright microservice** for browser-based scraping
- **Redis** for queues / rate limiting
- **Postgres** for queue/state storage
- **Rust native module** via `napi-rs` for performance-critical document handling
- **Go HTML→Markdown helper** (`sharedLibs/go-html-to-md`)
- **SDKs**:
  - JS
  - Python
  - Rust
- **Testing infrastructure**
  - end-to-end tests
  - snips/unit tests
  - benchmark notebooks
- **Deployment tooling**
  - Docker Compose
  - Kubernetes examples
  - GitHub Actions release/deploy workflows

## Shortcomings / limitations

### From the docs
- The repository is **still in development** and **not fully ready for self-hosted deployment yet**.
- Self-hosted instances **do not have access to Fire-engine**, so advanced anti-block / robot-detection features are missing.
- Some features require **manual `.env` configuration**.
- Supabase-based auth is described, but the self-host docs say it is **not fully configurable in self-hosted mode**.
- The stack is **operationally heavy**: multiple services and environment variables are needed.

### Architectural / repo-level
- Large dependency surface: Node, Rust, Go, Redis, Postgres, Playwright, AI providers.
- The API package has many runtime dependencies, which increases supply-chain and maintenance risk.
- Self-hosting depends on correct coordination of several services; one misconfigured env var can break the stack.
- The repo appears to mix product code, infrastructure code, SDKs, and experiments in one monorepo, which can make ownership and maintenance harder.

## What can be improved to be more robust

- **Stabilize self-hosting**
  - make the Docker Compose path closer to a “one command works” setup
  - reduce required env vars and provide validated defaults
  - document service dependencies more clearly

- **Improve fault tolerance**
  - add stronger retry/backoff behavior for Redis, Playwright, DB, and external APIs
  - add health checks and startup ordering checks
  - fail fast with clearer errors when required services are unavailable

- **Reduce coupling**
  - separate core API, workers, and optional services into clearer boundaries
  - isolate SDKs and shared libraries better
  - reduce cross-language complexity where possible

- **Strengthen observability**
  - more structured logs
  - clearer metrics per worker/service
  - better tracing around crawl/scrape jobs and queue processing

- **Improve configuration safety**
  - validate env vars at startup
  - provide a generated config example for production and self-host
  - enforce consistency between Docker Compose, docs, and actual code

- **Improve test coverage**
  - more integration tests for self-hosted flows
  - more regression tests for queue/worker startup and failure modes
  - more tests for native-module boundaries

- **Simplify deployment**
  - prebuilt images for the main services
  - versioned compose files
  - stronger CI checks for image/runtime compatibility

## Bottom line

Firecrawl is a fairly advanced website-crawling platform with a strong API story, multiple SDKs, and real production-oriented scraping capabilities. The main weakness is that the self-hosted stack is still relatively complex and not yet fully polished, so robustness can be improved by simplifying configuration, hardening service boundaries, and making startup/failure behavior more predictable.