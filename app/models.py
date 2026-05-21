"""Database models."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Proxy(Base):
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True, index=True)
    domain = Column(String(255), unique=True, nullable=False, index=True)
    target_host = Column(String(255), nullable=False)  # e.g. 127.0.0.1
    target_port = Column(Integer, nullable=False)      # e.g. 3000
    target_scheme = Column(String(8), default="http")  # http or https
    ssl_enabled = Column(Boolean, default=False)
    websocket = Column(Boolean, default=True)
    host_header_override = Column(String(255), default="")  # for external HTTPS backends
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UpdateLog(Base):
    __tablename__ = "update_logs"

    id = Column(Integer, primary_key=True, index=True)
    from_version = Column(String(32))
    to_version = Column(String(32))
    status = Column(String(32))  # success, failed, in_progress
    message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
