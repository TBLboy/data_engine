from fastapi import APIRouter

from app.api.routes.qc import router as qc_router
from app.api.routes.annotations import router as annotation_router

router = APIRouter()
router.include_router(qc_router)
router.include_router(annotation_router)
