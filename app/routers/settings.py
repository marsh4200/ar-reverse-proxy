"""Settings endpoints: password change, user info."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, hash_password, verify_password
from app.database import get_db
from app.models import User

router = APIRouter(prefix="/api/settings", tags=["settings"])


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    """Return basic info about the current user. Used by the UI to show
    whether the user is still on the default password (which is a security risk)."""
    # We can't tell if it's literally "admin" without doing a verify, which
    # we do here. False negatives are fine - just means we don't show the nag.
    is_default = verify_password("admin", user.password_hash) if user.username == "admin" else False
    return {
        "username": user.username,
        "is_admin": user.is_admin,
        "using_default_password": is_default,
    }


@router.post("/password")
def change_password(
    payload: PasswordChange,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")

    if payload.current_password == payload.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different from current")

    user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True, "message": "Password updated. Existing sessions remain valid."}
