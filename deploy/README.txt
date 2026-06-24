# Robot QC internal deployment

This compose stack is for internal LAN deployment of the Robot QC V1 manual QC platform.

## What this guide covers
- One-machine production deployment for a shared internal web service
- First-time initialization on a new host
- Re-deploying on an existing host with a persistent PostgreSQL volume
- MinIO wiring for real data ingestion and manual QC playback
- Common failure modes and how to recover

## Baseline assumptions
- `frontend` is a static nginx container on port `8080`
- `backend` is a FastAPI service on port `8000` inside the compose network
- `db` is PostgreSQL 17 with a persistent Docker volume
- Raw and processed data live in MinIO, not on local disk
- Users access the app from a browser on the LAN; they do not need local backend installs

## What you need before deployment
- Docker Engine and Docker Compose
- A MinIO endpoint, access key, secret key, and bucket name
- A PostgreSQL password for the `robot_qc` database role
- A random `SECRET_KEY` for session signing
- A host path or network mount for any local collection data used by the scanner

## Recommended secret generation
Generate these values once per deployment host. Do not commit them to git.

```bash
SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 16)
```

If you want to store them locally for later restarts, create a private env file in this directory:

```bash
cd /home/tbl/Project/data_collect/software/deploy
cat > .env <<EOF
APP_ENV=production
SECRET_KEY=${SECRET_KEY}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
MINIO_ENDPOINT=192.168.21.95:9190
MINIO_ACCESS_KEY=dexminioadmin
MINIO_SECRET_KEY=replace-with-real-secret
MINIO_DEFAULT_BUCKET=yaocao
FRONTEND_ORIGIN=http://localhost:8080
SESSION_COOKIE_SECURE=false
EOF
chmod 600 .env
```

If you are only testing in the current shell, you can export the same variables instead of writing `.env`.

## Deployment flow
Run the following from `software/deploy` unless noted otherwise.

### 1) Build the frontend assets
The frontend image packages the built `dist` output. Build it on the host first:

```bash
npm run build --prefix ../frontend
```

### 2) Start PostgreSQL
If this is the first time on the host:

```bash
docker compose -f docker-compose.yml up --build -d db
```

Wait for the database health check to pass.

### 3) Initialize schema and first admin
On a fresh database, run the bootstrap once to apply Alembic migrations and create the first admin user:

```bash
docker compose -f docker-compose.yml run --rm \
  -e APP_ENV=development \
  backend python -m app.services.bootstrap \
  --admin-username admin \
  --admin-password '<set-a-real-password>' \
  --admin-name '系统管理员' \
  --admin-role admin
```

If you only need schema creation without creating the admin yet:

```bash
docker compose -f docker-compose.yml run --rm \
  -e APP_ENV=development \
  backend python -m app.services.bootstrap --ensure-schema-only
```

### 4) Start backend and frontend

```bash
docker compose -f docker-compose.yml up --build -d backend frontend
```

The compose file already waits for PostgreSQL and backend health before starting the frontend, which avoids the transient 502 window during boot.

## Existing database volume
If the PostgreSQL volume already exists and you want to change `POSTGRES_PASSWORD`, update the database role once before restarting the stack:

```bash
docker exec -u postgres robot-qc-db psql -U postgres -d postgres \
  -c "ALTER USER robot_qc WITH PASSWORD 'new-password-here';"
```

Then restart the stack with the same `POSTGRES_PASSWORD` value in your env file or shell exports.

## Environment variables used by the compose stack
Required:
- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `MINIO_ENDPOINT`
- `MINIO_ACCESS_KEY`
- `MINIO_SECRET_KEY`

Recommended:
- `MINIO_DEFAULT_BUCKET=yaocao`
- `FRONTEND_ORIGIN=http://localhost:8080` or your LAN URL
- `SESSION_COOKIE_SECURE=false` for plain HTTP, `true` behind HTTPS
- `APP_ENV=production`

Notes:
- MinIO credentials must come from environment variables or a private env file
- Keep secrets out of the compose file itself
- The app defaults to bucket `yaocao` if you do not override it

## Verify the deployment
After the stack is up, check these endpoints:

```bash
curl http://127.0.0.1:8080/api/health
curl http://127.0.0.1:8080/api/auth/session
```

Expected:
- `api/health` returns `{"status":"ok"}`
- unauthenticated session returns `{"detail":"Not authenticated"}`

Then log in with the first admin account and confirm the browser can load the app:

- UI: `http://<your-lan-host>:8080`
- Health: `http://<your-lan-host>:8080/api/health`

## Real MinIO test checklist
For an actual data test on a new host:
1. Confirm the MinIO endpoint is reachable from the backend container.
2. Confirm the bucket name is correct, usually `yaocao`.
3. Run a scan from the database page or the scan API.
4. Wait for the scan to reach `done`.
5. Open manual QC and verify that video playback shows real media.
6. Use refresh on a media item and confirm the presigned URL updates.
7. Submit a review and confirm the task state updates in the history view.

## Stop

```bash
docker compose -f docker-compose.yml down
```

## Common failure modes
- Blank env vars: Compose prints warnings and the backend cannot connect to MinIO or PostgreSQL.
- Wrong `SECRET_KEY`: login/session cookies break after restart.
- Wrong `POSTGRES_PASSWORD`: backend startup fails with PostgreSQL authentication errors.
- Missing frontend build: the frontend image starts without the latest compiled assets.
- Wrong MinIO bucket or endpoint: scan succeeds partially or returns no data.
- HTTPS deployment with `SESSION_COOKIE_SECURE=false`: cookies will not behave correctly behind a secure reverse proxy.

## Recovery tips
- If the backend is healthy but login fails, check `SECRET_KEY` and the browser cookie domain/origin.
- If scans hang for a long time, confirm the MinIO endpoint and that nginx proxy timeouts are still 300s.
- If you changed the database password on an existing volume, make sure the PostgreSQL role password was updated inside the container too.
- If you migrated to another machine, copy only the repo and your private env file; do not copy local database volumes unless you explicitly want the data.

## For migrations to another machine
The minimal migration package is:
- this repository
- a private env file with the deployment values
- the MinIO endpoint and credentials
- access to the PostgreSQL persistent volume or a fresh database

Suggested order on the new host:
1. Install Docker and Docker Compose.
2. Prepare the private env file.
3. Build the frontend.
4. Start `db`.
5. Run bootstrap.
6. Start `backend` and `frontend`.
7. Verify login and one real MinIO scan.

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
