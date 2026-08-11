"""
Host and nginx status for the dashboard.

Deliberately dependency-free: everything here comes from the standard library
or /proc, so the panel gains live status without adding anything to
requirements.txt.
"""
import logging
import shutil
import socket
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def _systemctl_state(unit: str) -> tuple[bool, str]:
    """Return (is_active, state_word) for a systemd unit."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", unit],
            capture_output=True, text=True, timeout=5,
        )
        # `is-active` prints one word on success. Anything multi-line is an
        # environment error (no systemd, no bus) — collapse it rather than
        # leaking a stack of prose into the UI.
        state = result.stdout.strip()
        if not state or "\n" in state or len(state) > 24:
            state = "unavailable"
        return result.returncode == 0, state
    except FileNotFoundError:
        return False, "unavailable"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except Exception as e:  # noqa: BLE001
        logger.debug("systemctl is-active %s failed: %s", unit, e)
        return False, "unknown"


def _uptime_seconds() -> int:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:  # noqa: BLE001
        return 0


def _loadavg() -> tuple[float, float, float]:
    try:
        parts = Path("/proc/loadavg").read_text().split()
        return round(float(parts[0]), 2), round(float(parts[1]), 2), round(float(parts[2]), 2)
    except Exception:  # noqa: BLE001
        return 0.0, 0.0, 0.0


def _meminfo() -> tuple[int, int, float]:
    """Return (total_bytes, used_bytes, percent) from /proc/meminfo."""
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            values[key] = int(rest.strip().split()[0]) * 1024  # kB -> bytes
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(total - available, 0)
        pct = round(used / total * 100, 1) if total else 0.0
        return total, used, pct
    except Exception:  # noqa: BLE001
        return 0, 0, 0.0


def nginx_config_ok() -> tuple[bool, str]:
    """Run `nginx -t`. Cheap enough for an on-demand status call."""
    try:
        result = subprocess.run(
            ["nginx", "-t"], capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except FileNotFoundError:
        return False, "nginx binary not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "nginx -t timed out"
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def status() -> dict:
    """Everything the dashboard needs to describe the host in one call."""
    nginx_running, nginx_state = _systemctl_state("nginx")
    config_ok, config_message = nginx_config_ok()
    mem_total, mem_used, mem_pct = _meminfo()
    load_1, load_5, load_15 = _loadavg()

    return {
        "hostname": socket.gethostname(),
        "uptime_seconds": _uptime_seconds(),
        "nginx_running": nginx_running,
        "nginx_state": nginx_state,
        "nginx_config_ok": config_ok,
        "nginx_message": config_message[:500],
        "certbot_available": shutil.which("certbot") is not None,
        "load_1": load_1,
        "load_5": load_5,
        "load_15": load_15,
        "memory_total": mem_total,
        "memory_used": mem_used,
        "memory_percent": mem_pct,
    }
