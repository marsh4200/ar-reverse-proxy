"""
ar-reverse-proxy: FastAPI entrypoint.

Mounts API routers, serves Jinja templates for /login and /dashboard,
and bootstraps the admin user + DB schema on startup.
"""
import logging
from pathlib import Path

from fastapi import FastAPI, Request, Depends, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth import get_current_user_or_redirect, hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import User
from app.routers import auth as auth_router
from app.routers import proxies as proxies_router
from app.routers import update as update_router
from app.services import update_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("arrp")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=settings.APP_NAME, version=update_service.get_local_version())

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.include_router(auth_router.router)
app.include_router(proxies_router.router)
app.include_router(update_router.router)


@app.on_event("startup")
def on_startup() -> None:
    """Create tables and bootstrap the default admin user."""
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.query(User).count() == 0:
            user = User(
                username=settings.DEFAULT_ADMIN_USER,
                password_hash=hash_password(settings.DEFAULT_ADMIN_PASS),
                is_admin=True,
            )
            db.add(user)
            db.commit()
            logger.warning(
                "Bootstrapped admin user '%s'. CHANGE THE DEFAULT PASSWORD.",
                settings.DEFAULT_ADMIN_USER,
            )
    finally:
        db.close()


@app.get("/", include_in_schema=False)
async def root(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_redirect(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)


@app.get("/login", include_in_schema=False)
async def login_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_redirect(request, db)
    if user:
        return RedirectResponse("/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@app.get("/dashboard", include_in_schema=False)
async def dashboard_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user_or_redirect(request, db)
    if not user:
        return RedirectResponse("/login", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "version": update_service.get_local_version(),
        },
    )


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok", "version": update_service.get_local_version()}
