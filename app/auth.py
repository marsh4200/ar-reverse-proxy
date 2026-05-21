"""Authentication: JWT tokens + bcrypt password hashing."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import HTTPException, Request, status, Depends
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "arrp_session"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


def get_token_from_request(request: Request) -> Optional[str]:
    # Cookie (browser) takes priority; Bearer header (API) as fallback.
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return None


def get_current_user(
    request: Request, db: Session = Depends(get_db)
) -> User:
    token = get_token_from_request(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    username = decode_token(token)
    if not username:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def get_current_user_or_redirect(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    """Soft auth used for HTML pages - returns None instead of raising."""
    token = get_token_from_request(request)
    if not token:
        return None
    username = decode_token(token)
    if not username:
        return None
    return db.query(User).filter(User.username == username).first()
