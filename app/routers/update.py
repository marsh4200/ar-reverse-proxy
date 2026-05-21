"""Update system endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import UpdateLog, User
from app.services import update_service

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/status")
def update_status(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    available, local, remote = update_service.is_update_available()
    last = db.query(UpdateLog).order_by(UpdateLog.id.desc()).first()
    return {
        "local_version": local,
        "remote_version": remote,
        "update_available": available,
        "last_status": last.status if last else None,
        "last_message": last.message if last else None,
        "last_checked": last.created_at.isoformat() if last else None,
    }


@router.post("/run")
def update_run(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    available, local, remote = update_service.is_update_available()

    log = UpdateLog(
        from_version=local,
        to_version=remote or "unknown",
        status="in_progress",
        message="Update triggered from GUI.",
    )
    db.add(log)
    db.commit()

    ok, msg = update_service.run_update()
    log.status = "success" if ok else "failed"
    log.message = msg
    db.commit()

    return {
        "ok": ok,
        "message": msg,
        "from_version": local,
        "to_version": remote,
    }
