# Robot QC V1

Robot QC V1 is an internal manual quality-control platform for robotics data.

## Scope
- Real data ingestion from mounted collection directories
- Batch creation and task dispatch
- Manual QC review workflow with claim/lock protection
- QC history, reports, and JSON export
- Docker + PostgreSQL deployment baseline

## Repository Layout
- `backend/`: FastAPI backend, Alembic migrations, bootstrap/init flow
- `frontend/`: Vue 3 frontend for operators, managers, and admins
- `deploy/`: Docker Compose and deployment instructions
- `.project-log/`: project progress and delivery logs

## Quick Start
1. Build frontend assets:
   `npm run build --prefix frontend`
2. Start PostgreSQL:
   `docker compose -f deploy/docker-compose.yml up --build -d db`
3. Initialize schema and first admin:
   `docker compose -f deploy/docker-compose.yml run --rm -e APP_ENV=development backend python -m app.services.bootstrap --admin-username admin --admin-password '<set-a-real-password>' --admin-name '系统管理员' --admin-role admin`
4. Start app services:
   `docker compose -f deploy/docker-compose.yml up --build -d backend frontend`

See `deploy/README.txt` for full deployment details.
