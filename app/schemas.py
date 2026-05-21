"""Pydantic schemas for API I/O."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


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
        v = v.strip().lower()
        if " " in v or "/" in v:
            raise ValueError("Domain must not contain spaces or slashes")
        return v


class ProxyUpdate(BaseModel):
    target_host: Optional[str] = None
    target_port: Optional[int] = Field(None, ge=1, le=65535)
    target_scheme: Optional[str] = Field(None, pattern="^(http|https)$")
    ssl_enabled: Optional[bool] = None
    websocket: Optional[bool] = None
    host_header_override: Optional[str] = None
    notes: Optional[str] = None


class ProxyOut(BaseModel):
    id: int
    domain: str
    target_host: str
    target_port: int
    target_scheme: str
    ssl_enabled: bool
    websocket: bool
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
