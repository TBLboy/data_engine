# Robot QC V1 — Agent Guide

## Project

Data QC platform for robot data collection (Linker Open TeleDex). QC pipeline: manual review → batch adjudication → dataset export.

## Layout

```
backend/      FastAPI + SQLAlchemy + Alembic + APScheduler
frontend/     Vue 3 + Element Plus + Chart.js + Pinia + vue-router
deploy/       Docker Compose production stack (composition file not at root)
scripts/      AI runtime check, Ollama service management
tests/        Standalone Python tests (no test runner config)
.project-log/ Project progress & business logic (main.md = single source of truth)
```

## Critical Commands

```bash
# All docker commands MUST use -f deploy/docker-compose.yml
docker compose -f deploy/docker-compose.yml up -d --build backend
docker compose -f deploy/docker-compose.yml exec backend alembic upgrade head

# Frontend build (must run BEFORE docker build — Dockerfile copies dist/)
cd frontend && npm run build                       # vue-tsc -b && vite build
cd frontend && npx vue-tsc --noEmit                 # typecheck only

# Backend compile check / typecheck
cd backend && python -m compileall -q app/

# Tests (run from project root, both use sys.path.insert to reach backend/)
python tests/test_data_assets.py
python tests/test_ai_qc_explain.py

# Data asset rollup recompute worker
cd backend && python -m app.services.data_assets_worker rebuild-all [batch|task|all]

# Frontend dev server (auto-proxies /api to http://127.0.0.1:8000)
cd frontend && npm run dev
```

## Deployment Quirks

- **Migration order matters**: `alembic upgrade head` **before** restarting backend. Code reading missing columns → 500 on every endpoint. `start.sh` auto-runs migrations on container start.
- **Frontend dist model**: `Dockerfile` `COPY dist/` — must run `npm run build` locally first, **then** `docker compose build frontend`. Buildx may silently fail; use `docker compose build --no-cache frontend` + `docker compose up -d frontend` in two steps.
- **Hard refresh**: JS chunk hashes change every build; tell users `Ctrl+Shift+R`.
- **Alembic baseline drift**: `audit_events.id` model says `String(128)` but baseline migration `20260623_0001` still says `64` — new deployments need a fix.
- MinIO creds via env vars only, never hardcoded.
- `deploy/.env` required for secrets; pydantic-settings also reads `.env` from project root for local dev.

## Architecture

- **MinIO** = raw object storage only. **PostgreSQL** = single source of truth.
- Frontend never talks to MinIO directly — media via presigned URLs, structured data via backend API.
- Backend entry: `backend/main.py` (re-exports `app` from `app/main.py`). API routes in `backend/app/api/routes/`.
- ORM models in `backend/app/models/`. Alembic migrations in `backend/migrations/versions/`.
- L3 QC engine in `backend/app/services/l3_v2/`. Legacy scanner in `backend/app/services/scanner.py` (replaced by v3). Scan v3 services: `scan_queue.py`, `scan_coordinator.py`, `scan_worker.py`, `namespace_discovery.py`, `list_snapshot.py`, `business_resolver.py`.
- AI QC module in `backend/app/ai_qc/` (LLM-based explainer + chat via Ollama, template fallback).
- Settings via pydantic-settings: env vars → `.env` → defaults in `app/core/config.py`.

## AI QC (AI-Assisted Quality Explain)

- Module: `backend/app/ai_qc/` — `AiQcService.explain()` with template fallback if LLM unreachable.
- Chat endpoint: `POST /api/ai-assistant/chat/stream` (SSE). Health: `GET /api/ai-assistant/health`.
- Model config stored in `GeneralConfig` (set via UI settings page), env vars as fallback.
- Scripts: `scripts/check_ai_runtime.py` (diagnostics), `scripts/start_ollama.sh` (service mgmt).
- Health check calls Ollama with 3s timeout — if it fails, frontend shows "unavailable".

## Business Logic Sources

- `.project-log/business-logic/main.md` — canonical business rules (batch adjudication, task pool, asset rollups, constraints)
- `.project-log/business-logic/decision-records.md` — architecture decisions (Route C', Route T2, scan v3)
- `.project-log/business-logic/constraints.md` — frozen design constraints
- `.project-log/debugging/known-issues.md` — past bugs worth not repeating
- `docs/scan-architecture-final-plan-v3.md` — canonical scanner upgrade plan (core + API implemented as of 2026-07-18)

## Key Conventions

- **Asset rollups**: `batch_asset_rollups` → `task_asset_rollups` two-layer cascade. Never scan `episodes` at request time for aggregates.
- **Active scope**: All asset counts use `active_list_active_batch_indexed_episodes`. Summary, batch list, and task list must share identical scope.
- **Failure rate**: `N_fail_manual / N_sampled` (NOT batch total).
- **Task pool**: reviewer current = `is_active=1 + assignee=self + status in (assigned,in_review)`. History = revision records, not `QcTask.status='done'`.
- **Admin claim done** = reopen + ownership transfer (reset episode QC state, keep old revision).
- **Scan v3** core services + API + frontend implemented (2026-07-18). Core: `scan_queue.py`, `scan_coordinator.py`, `scan_worker.py`, `namespace_discovery.py`, `list_snapshot.py`, `business_resolver.py`. API: `POST /database/scan`, `GET /database/scan/{id}`, cancel/retry. Frontend: mode selector, shard progress, auto-polling, cancel/retry buttons. Legacy `scanner.py` disabled. Remaining: offline tests, PostgreSQL/MinIO production validation.
- `task_types.total_batches` / `total_episodes` in deprecation — use task rollup instead.
