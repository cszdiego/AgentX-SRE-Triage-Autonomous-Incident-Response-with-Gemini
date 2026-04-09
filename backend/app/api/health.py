from fastapi import APIRouter
from app.core.database import fetchone
from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
def health_check():
    db_ok = False
    try:
        fetchone("SELECT 1 as ok")
        db_ok = True
    except Exception:
        pass

    return {
        "status": "healthy" if db_ok else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": "connected" if db_ok else "unavailable",
        "model": settings.GEMINI_MODEL,
    }
