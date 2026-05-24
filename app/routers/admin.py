from fastapi import APIRouter
from app.routers.admin_api import router as api_router
from app.routers.admin_views import (
    router as views_router,
    verify_admin,
    create_admin_csrf_token,
    verify_admin_csrf_token,
)
from app.utils.display import mask_secret

router = APIRouter()
router.include_router(api_router)
router.include_router(views_router)
