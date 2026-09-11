from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    settings = get_settings()
    return {"status": "ok", "version": settings.app_version}
