"""
GitHub-based update system.

Checks remote VERSION file at GitHub raw, compares to local,
and (when triggered) runs update.sh which pulls latest code and
restarts the systemd service.
"""
import subprocess
import logging
from pathlib import Path
from typing import Optional

import requests

from app.config import settings

logger = logging.getLogger(__name__)


def get_local_version() -> str:
    vf = settings.INSTALL_DIR / "VERSION"
    if vf.exists():
        return vf.read_text().strip()
    # Dev fallback - VERSION at repo root next to /app
    fallback = Path(__file__).resolve().parent.parent.parent / "VERSION"
    if fallback.exists():
        return fallback.read_text().strip()
    return "0.0.0"


def get_remote_version() -> Optional[str]:
    """Fetch VERSION from the configured GitHub repo/branch."""
    url = (
        f"https://raw.githubusercontent.com/"
        f"{settings.GITHUB_REPO}/{settings.GITHUB_BRANCH}/VERSION"
    )
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return r.text.strip()
        logger.warning("Remote VERSION fetch returned %s", r.status_code)
        return None
    except Exception as e:
        logger.error("Remote VERSION fetch failed: %s", e)
        return None


def _parse(v: str) -> tuple:
    """Best-effort semver tuple parser; falls back to string compare."""
    try:
        return tuple(int(p) for p in v.strip().split("."))
    except ValueError:
        return (0, 0, 0)


def is_update_available() -> tuple[bool, str, Optional[str]]:
    local = get_local_version()
    remote = get_remote_version()
    if remote is None:
        return False, local, None
    return _parse(remote) > _parse(local), local, remote


def run_update() -> tuple[bool, str]:
    """
    Run update.sh from the install directory.
    The script pulls latest code, installs deps, and restarts the systemd
    service - which means this process will be killed mid-execution. We
    return success based on the spawn, not the eventual restart.
    """
    script = settings.INSTALL_DIR / "scripts" / "update.sh"
    if not script.exists():
        return False, f"update.sh not found at {script}"

    try:
        # nohup + detach so the parent (us) can return before systemd kills it
        subprocess.Popen(
            ["/bin/bash", str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, "Update started. The service will restart shortly."
    except Exception as e:
        return False, f"Failed to start update: {e}"
