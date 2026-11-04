from fastapi import APIRouter

from app.core.config import APP_VERSION

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz():
    return {"status": "ok", "version": APP_VERSION}
