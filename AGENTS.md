# Robot QC V1 — Agent Guide

## Project

Data QC platform for robot data collection (Linker Open TeleDex). QC pipeline: manual review → batch adjudication → dataset export.

## Layout

```
backend/      FastAPI + SQLAlchemy + Alembic + APScheduler
frontend/     Vue 3 + Element Plus + Chart.js + Pinia + vue-router
deploy/       Docker Compose production stack (composition file not at root)
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

# Backend compile check
cd backend && python -m compileall -q app/
```

## Deployment Quirks

- **Migration order matters**: `alembic upgrade head` **before** restarting backend. Code reading missing columns → 500 on every endpoint.
- **Frontend dist model**: `Dockerfile` `COPY dist/` — must run `npm run build` locally first, **then** `docker compose build frontend`. Buildx may silently fail; use `docker compose build --no-cache frontend` + `docker compose up -d frontend` in two steps.
- **Hard refresh**: JS chunk hashes change every build; tell users `Ctrl+Shift+R`.
- **Alembic baseline drift**: `audit_events.id` model says `String(128)` but baseline migration `20260623_0001` still says `64` — new deployments need a fix.
- MinIO creds via env vars only, never hardcoded.

## Architecture

- **MinIO** = raw object storage only. **PostgreSQL** = single source of truth.
- Frontend never talks to MinIO directly — media via presigned URLs, structured data via backend API.
- Backend entry: `backend/main.py` (FastAPI app). API routes in `backend/app/api/routes/`.
- ORM models in `backend/app/models/`. Alembic migrations in `backend/migrations/versions/`.
- L3 QC engine in `backend/app/services/l3_v2/`. Scanner in `backend/app/services/scanner.py`.

## Business Logic Sources

- `.project-log/business-logic/main.md` — canonical business rules (batch adjudication, task pool, asset rollups, constraints)
- `.project-log/business-logic/decision-records.md` — architecture decisions (Route C', Route T2, scan v3)
- `.project-log/business-logic/constraints.md` — frozen design constraints
- `.project-log/debugging/known-issues.md` — past bugs worth not repeating
- `docs/scan-architecture-final-plan-v3.md` — canonical scanner upgrade plan (not yet implemented)

## Key Conventions

- **Asset rollups**: `batch_asset_rollups` → `task_asset_rollups` two-layer cascade. Never scan `episodes` at request time for aggregates.
- **Active scope**: All asset counts use `active_list_active_batch_indexed_episodes`. Summary, batch list, and task list must share identical scope.
- **Failure rate**: `N_fail_manual / N_sampled` (NOT batch total).
- **Task pool**: reviewer current = `is_active=1 + assignee=self + status in (assigned,in_review)`. History = revision records, not `QcTask.status='done'`.
- **Admin claim done** = reopen + ownership transfer (reset episode QC state, keep old revision).
- **Scan v3** not yet implemented — current scanner is `threading.Thread` with known stability issues. Do not implement from superseded v2.
- `task_types.total_batches` / `total_episodes` in deprecation — use task rollup instead.
