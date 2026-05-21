"""
Nginx configuration generator and operator.

Writes per-domain config files into /etc/nginx/sites-available,
symlinks them into sites-enabled, validates with `nginx -t`,
and reloads via `systemctl reload nginx`. SSL is provisioned with certbot.
"""
import subprocess
import logging
from pathlib import Path

from app.config import settings
from app.models import Proxy

logger = logging.getLogger(__name__)


HTTP_TEMPLATE = """# Managed by ar-reverse-proxy - do not edit by hand
server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    access_log /var/log/nginx/{domain}.access.log;
    error_log  /var/log/nginx/{domain}.error.log;

    client_max_body_size 100M;

    location / {{
        proxy_pass {scheme}://{host}:{port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
{websocket_block}
        proxy_read_timeout 90s;
        proxy_send_timeout 90s;
    }}
}}
"""

WEBSOCKET_BLOCK = """        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
"""


def config_path(domain: str) -> Path:
    return settings.NGINX_SITES_DIR / f"arrp_{domain}.conf"


def enabled_path(domain: str) -> Path:
    return settings.NGINX_ENABLED_DIR / f"arrp_{domain}.conf"


def render_config(proxy: Proxy) -> str:
    return HTTP_TEMPLATE.format(
        domain=proxy.domain,
        scheme=proxy.target_scheme,
        host=proxy.target_host,
        port=proxy.target_port,
        websocket_block=WEBSOCKET_BLOCK if proxy.websocket else "",
    )


def write_config(proxy: Proxy) -> Path:
    """Write the config file and ensure it's enabled."""
    path = config_path(proxy.domain)
    path.write_text(render_config(proxy))
    link = enabled_path(proxy.domain)
    if not link.exists():
        link.symlink_to(path)
    return path


def remove_config(domain: str) -> None:
    """Remove enabled symlink + available file for a domain."""
    link = enabled_path(domain)
    if link.is_symlink() or link.exists():
        link.unlink()
    path = config_path(domain)
    if path.exists():
        path.unlink()


def test_nginx() -> tuple[bool, str]:
    """Run `nginx -t`. Returns (ok, combined_output)."""
    try:
        result = subprocess.run(
            ["nginx", "-t"], capture_output=True, text=True, timeout=15
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "nginx binary not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "nginx -t timed out"


def reload_nginx() -> tuple[bool, str]:
    """systemctl reload nginx."""
    try:
        result = subprocess.run(
            ["systemctl", "reload", "nginx"],
            capture_output=True, text=True, timeout=15,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output or "nginx reloaded"
    except Exception as e:
        return False, str(e)


def issue_ssl(domain: str, email: str = "admin@" + "localhost") -> tuple[bool, str]:
    """
    Request/install a Let's Encrypt cert using the nginx plugin.
    --non-interactive --agree-tos so it runs unattended.
    """
    try:
        cmd = [
            "certbot", "--nginx",
            "-d", domain,
            "--non-interactive",
            "--agree-tos",
            "--redirect",
            "-m", email,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except FileNotFoundError:
        return False, "certbot not installed"
    except subprocess.TimeoutExpired:
        return False, "certbot timed out"


def apply_proxy(proxy: Proxy, request_ssl: bool = False, ssl_email: str = "") -> tuple[bool, str]:
    """
    Full apply cycle: write config, test, reload, optionally issue SSL.
    Rolls back the config file on failure so nginx stays valid.
    """
    write_config(proxy)

    ok, out = test_nginx()
    if not ok:
        # Roll back so nginx keeps serving existing sites
        remove_config(proxy.domain)
        return False, f"nginx -t failed:\n{out}"

    ok, out = reload_nginx()
    if not ok:
        return False, f"nginx reload failed:\n{out}"

    if request_ssl:
        ok, ssl_out = issue_ssl(proxy.domain, ssl_email or f"admin@{proxy.domain}")
        if not ok:
            return False, f"Proxy created but SSL failed:\n{ssl_out}"
        return True, f"Proxy applied with SSL.\n{ssl_out}"

    return True, "Proxy applied successfully."


def remove_proxy(domain: str) -> tuple[bool, str]:
    remove_config(domain)
    ok, out = test_nginx()
    if not ok:
        return False, f"nginx -t failed after removal:\n{out}"
    return reload_nginx()
