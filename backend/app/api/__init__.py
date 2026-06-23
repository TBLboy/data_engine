from fastapi import APIRouter

from app.api.routes.qc import router as qc_router

router = APIRouter()
router.include_router(qc_router)
