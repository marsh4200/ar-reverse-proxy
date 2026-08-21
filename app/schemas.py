"""Pydantic schemas for API I/O."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


def _clean_hostname(v: str) -> str:
    """
    Normalize a hostname value.

    Users tend to paste full URLs ('https://example.com/') into fields that
    want just a hostname. Strip the scheme, any path, and trailing dots.
    This prevents the classic bug where the Host header ends up as
    `Host: https://example.com` and the upstream returns 400.
    """
    v = v.strip().lower()
    # Strip scheme
    for prefix in ("https://", "http://", "//"):
        if v.startswith(prefix):
            v = v[len(prefix):]
    # Strip path
    if "/" in v:
        v = v.split("/", 1)[0]
    # Strip trailing dot (FQDN form)
    v = v.rstrip(".")
    return v


class LoginRequest(BaseModel):
    username: str
    password: str


class ProxyCreate(BaseModel):
    domain: str = Field(..., min_length=3, max_length=255)
    target_host: str = Field(..., min_length=1, max_length=255)
    target_port: int = Field(..., ge=1, le=65535)
    target_scheme: str = Field("http", pattern="^(http|https)$")
    ssl_enabled: bool = False
    websocket: bool = True
    host_header_override: str = ""
    notes: str = ""

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = _clean_hostname(v)
        if " " in v:
            raise ValueError("Domain must not contain spaces")
        if not v:
            raise ValueError("Domain is required")
        return v

    @field_validator("target_host")
    @classmethod
    def validate_target_host(cls, v: str) -> str:
        v = _clean_hostname(v)
        if not v:
            raise ValueError("Target host is required")
        if " " in v:
            raise ValueError("Target host must not contain spaces")
        return v

    @field_validator("host_header_override")
    @classmethod
    def validate_host_header(cls, v: str) -> str:
        # Empty is fine - means "pass through visitor's Host header".
        if not v or not v.strip():
            return ""
        v = _clean_hostname(v)
        if " " in v:
            raise ValueError("Host header override must not contain spaces")
        return v


class ProxyUpdate(BaseModel):
    target_host: Optional[str] = None
    target_port: Optional[int] = Field(None, ge=1, le=65535)
    target_scheme: Optional[str] = Field(None, pattern="^(http|https)$")
    ssl_enabled: Optional[bool] = None
    websocket: Optional[bool] = None
    host_header_override: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("target_host")
    @classmethod
    def validate_target_host(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _clean_hostname(v)

    @field_validator("host_header_override")
    @classmethod
    def validate_host_header(cls, v: Optional[str]) -> Optional[str]:
        if v is None or not v.strip():
            return v
        return _clean_hostname(v)


class ProxyOut(BaseModel):
    id: int
    domain: str
    target_host: str
    target_port: int
    target_scheme: str
    ssl_enabled: bool
    websocket: bool
    enabled: bool
    host_header_override: str
    notes: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UpdateStatus(BaseModel):
    local_version: str
    remote_version: Optional[str] = None
    update_available: bool = False
    last_status: Optional[str] = None
    last_message: Optional[str] = None
    last_checked: Optional[datetime] = None
