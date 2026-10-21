from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/")
def health_check():
    """Return the service health status and current UTC timestamp."""
    return {
        "status": "HEALTHY",
        "current_time": datetime.now(timezone.utc).isoformat(),
    }
