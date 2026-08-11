"""Host and nginx status endpoint (read-only)."""
from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models import User
from app.services import system_service

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/status")
def system_status(_: User = Depends(get_current_user)) -> dict:
    """Live nginx state, host identity and load for the dashboard.

    Read-only and safe to poll; the UI refreshes it every 20 seconds while
    the tab is visible.
    """
    return system_service.status()
