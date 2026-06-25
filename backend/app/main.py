from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import router
from app.core.config import DEFAULT_SECRET_KEY, get_settings

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
app.include_router(router)


@app.exception_handler(PermissionError)
async def permission_error_handler(_request: Request, exc: PermissionError):
    return JSONResponse(status_code=403, content={'detail': str(exc)})
