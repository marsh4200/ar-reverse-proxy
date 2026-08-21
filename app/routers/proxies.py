"""Proxy CRUD endpoints."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Proxy, User
from app.schemas import ProxyCreate, ProxyOut, ProxyUpdate
from app.services import nginx_service

router = APIRouter(prefix="/api/proxies", tags=["proxies"])


@router.get("", response_model=list[ProxyOut])
def list_proxies(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return db.query(Proxy).order_by(Proxy.domain).all()


@router.post("", response_model=ProxyOut, status_code=status.HTTP_201_CREATED)
def create_proxy(
    payload: ProxyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    existing = db.query(Proxy).filter(Proxy.domain == payload.domain).first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Domain already exists")

    proxy = Proxy(**payload.model_dump())
    db.add(proxy)
    db.commit()
    db.refresh(proxy)

    ok, msg = nginx_service.apply_proxy(proxy, request_ssl=payload.ssl_enabled)
    if not ok:
        # Roll back DB row to keep state consistent with nginx
        db.delete(proxy)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)

    return proxy


@router.get("/{proxy_id}", response_model=ProxyOut)
def get_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy not found")
    return proxy


@router.put("/{proxy_id}", response_model=ProxyOut)
def update_proxy(
    proxy_id: int,
    payload: ProxyUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy not found")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(proxy, k, v)
    db.commit()
    db.refresh(proxy)

    ok, msg = nginx_service.apply_proxy(proxy, request_ssl=proxy.ssl_enabled)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    return proxy


@router.delete("/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy not found")

    domain = proxy.domain
    db.delete(proxy)
    db.commit()

    ok, msg = nginx_service.remove_proxy(domain)
    if not ok:
        # We've already removed from DB - log but don't restore.
        # nginx is the source of pain here, admin should investigate.
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, msg)


@router.post("/{proxy_id}/toggle", response_model=ProxyOut)
def toggle_proxy(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """
    Flip a route between live and paused.

    Paused routes keep their DB row and nginx config file untouched - only
    the sites-enabled symlink is removed - so resuming is instant and the
    route's HTTPS certificate (if any) is never re-requested.
    """
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy not found")

    proxy.enabled = not proxy.enabled
    db.commit()
    db.refresh(proxy)

    ok, msg = nginx_service.apply_proxy(proxy, request_ssl=False)
    if not ok:
        # Roll back the DB flag so it still matches what nginx is actually doing.
        proxy.enabled = not proxy.enabled
        db.commit()
        db.refresh(proxy)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)

    return proxy


@router.post("/{proxy_id}/ssl")
def issue_ssl(
    proxy_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    proxy = db.query(Proxy).filter(Proxy.id == proxy_id).first()
    if not proxy:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proxy not found")
    ok, msg = nginx_service.issue_ssl(proxy.domain)
    if ok:
        proxy.ssl_enabled = True
        db.commit()
    return {"ok": ok, "message": msg}
