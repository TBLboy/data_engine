from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.core.config import DEFAULT_SECRET_KEY, get_settings
from app.middleware.audit_middleware import AuditMiddleware

settings = get_settings()

if settings.is_production and settings.secret_key == DEFAULT_SECRET_KEY:
    raise RuntimeError('SECRET_KEY must be set for production deployments')
if settings.is_production and settings.database_url.startswith('sqlite:///'):
    raise RuntimeError('Production deployments must use a non-SQLite DATABASE_URL')

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
app.add_middleware(AuditMiddleware)
app.include_router(router)


@app.on_event('startup')
async def _startup():
    from app.core.logging_config import setup_logging
    setup_logging()
    from app.services.scan_scheduler import start_scheduler
    try:
        start_scheduler()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('scan cron scheduler failed to start')


@app.on_event('shutdown')
async def _shutdown():
    from app.services.scan_scheduler import stop_scheduler
    try:
        stop_scheduler()
    except Exception:
        pass


@app.exception_handler(PermissionError)
async def permission_error_handler(_request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={'detail': str(exc)})
