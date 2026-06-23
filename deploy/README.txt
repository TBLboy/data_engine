# Robot QC internal deployment

This compose stack is for internal LAN deployment of the V1 manual QC platform.

## Current production baseline
- Backend startup no longer auto-creates schema or seeds demo data.
- Database schema is now managed by Alembic; new environments should use `alembic upgrade head` semantics through the bootstrap/init flow.
- You must initialize the database and create the first admin account explicitly before first login.
- Production deployment is expected to use PostgreSQL rather than SQLite.

## Services
- `frontend`: nginx static site on port `8080`, reverse proxies `/api` to backend
- `backend`: FastAPI service
- `db`: PostgreSQL business database with persistent Docker volume

## Data mounts
- PostgreSQL business data persists in volume `robot_qc_postgres`
- Raw/processed collection data is mounted from host path `/data/collection_data`

## Build frontend assets first
The frontend container packages the prebuilt local `dist` directory instead of installing npm dependencies inside Docker. Build it on the host before `docker compose up --build`:

```bash
npm run build --prefix software/frontend
```

## Start
```bash
docker compose -f software/deploy/docker-compose.yml up --build -d db
```

Wait for PostgreSQL to become ready, then initialize schema and the first admin account:

```bash
docker compose -f software/deploy/docker-compose.yml run --rm \
  -e APP_ENV=development \
  backend python -m app.services.bootstrap \
  --admin-username admin \
  --admin-password '<set-a-real-password>' \
  --admin-name '系统管理员' \
  --admin-role admin
```

This initialization path now runs the Alembic baseline automatically:
- empty database: applies `upgrade head`
- existing database with business tables but no `alembic_version`: runs legacy SQLite compatibility backfill if needed, then `stamp head`
- versioned database: runs `upgrade head`

If you need an explicit schema-only step before creating the first admin, run:

```bash
docker compose -f software/deploy/docker-compose.yml run --rm \
  -e APP_ENV=development \
  backend python -m app.services.bootstrap --ensure-schema-only
```

Then start the application services:

```bash
docker compose -f software/deploy/docker-compose.yml up --build -d backend frontend
```

## Required environment changes before real deployment
- Replace `SECRET_KEY=change-me-before-deploy`
- Replace the sample PostgreSQL password in `docker-compose.yml`
- Set `SESSION_COOKIE_SECURE=true` when serving over HTTPS
- Keep `APP_ENV=production` for deployed backend containers
- Treat `alembic upgrade head` as a required release step before backend rollout

## Open
- UI: `http://<your-lan-host>:8080`
- Health: `http://<your-lan-host>:8080/api/health`

## Stop
```bash
docker compose -f software/deploy/docker-compose.yml down
```

## Fallback local backend validation
Use this only when Docker daemon access is unavailable. It keeps backend dependencies inside `software/backend/.conda-env` and avoids modifying the ROS/system Python.

```bash
"$HOME/miniconda3/bin/conda" create -y -p software/backend/.conda-env python=3.10 pip
env -u PYTHONPATH PYTHONNOUSERSITE=1 software/backend/.conda-env/bin/python -m pip install -r software/backend/requirements.txt
env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m app.services.bootstrap --ensure-schema-only'
env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m app.services.bootstrap --admin-username admin --admin-password "<set-a-real-password>"'
env -u PYTHONPATH PYTHONNOUSERSITE=1 bash -lc 'cd software/backend && .conda-env/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8001'
```

Smoke test:

```bash
curl http://127.0.0.1:8001/api/health
```

Important:
- Keep `PYTHONNOUSERSITE=1` so user-site packages are ignored.
- Keep `env -u PYTHONPATH` so ROS `PYTHONPATH` does not leak into the backend runtime.
- This path validates the backend API only; frontend browser validation still needs either Docker or a separate frontend dev/build serve flow.

## Notes
- The old demo dataset bootstrap has been removed from default startup; an empty database will stay empty until you run explicit initialization/import steps.
- If your collection data lives elsewhere, change the host side of the bind mount in `software/deploy/docker-compose.yml`.
- The next production phase is to standardize follow-up Alembic revisions in release workflow; the baseline schema revision is already present as `20260623_0001`.
