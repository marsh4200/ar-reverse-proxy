"""
Application configuration.
Reads from environment variables with sensible defaults.
The install script writes /etc/ar-reverse-proxy/env which systemd loads.
"""
import os
import secrets
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AR Reverse Proxy"
    HOST: str = "0.0.0.0"
    PORT: int = 9914

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    DATA_DIR: Path = Path(os.getenv("ARRP_DATA_DIR", "/var/lib/ar-reverse-proxy"))
    NGINX_SITES_DIR: Path = Path("/etc/nginx/sites-available")
    NGINX_ENABLED_DIR: Path = Path("/etc/nginx/sites-enabled")

    # Database
    DB_PATH: Path = DATA_DIR / "arrp.db"

    # Auth
    SECRET_KEY: str = os.getenv("ARRP_SECRET_KEY", secrets.token_urlsafe(48))
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 12  # 12 hours

    # Update system
    GITHUB_REPO: str = os.getenv("ARRP_GITHUB_REPO", "marsh4200/ar-reverse-proxy")
    GITHUB_BRANCH: str = os.getenv("ARRP_GITHUB_BRANCH", "main")
    INSTALL_DIR: Path = Path(os.getenv("ARRP_INSTALL_DIR", "/opt/ar-reverse-proxy"))

    # Admin (used for first-run bootstrap only)
    DEFAULT_ADMIN_USER: str = os.getenv("ARRP_ADMIN_USER", "admin")
    DEFAULT_ADMIN_PASS: str = os.getenv("ARRP_ADMIN_PASS", "admin")

    class Config:
        case_sensitive = True


settings = Settings()
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
