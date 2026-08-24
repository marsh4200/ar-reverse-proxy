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
{resolver_block}
    location / {{
        proxy_pass {scheme}://{upstream};
        proxy_http_version 1.1;
        proxy_set_header Host {host_header};
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
{websocket_block}{ssl_backend_block}
        proxy_redirect off;
        proxy_read_timeout {read_timeout}s;
        proxy_send_timeout {send_timeout}s;
        proxy_connect_timeout {connect_timeout}s;
    }}
}}
"""

WEBSOCKET_BLOCK = """        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
"""

# When proxying to an HTTPS backend (especially a CDN/PaaS like base44, Vercel,
# Netlify, Cloudflare), we need SNI plus a DNS resolver so nginx can re-resolve
# the upstream hostname at request time.
SSL_BACKEND_BLOCK = """        proxy_ssl_server_name on;
        proxy_ssl_protocols TLSv1.2 TLSv1.3;
"""

RESOLVER_BLOCK = """
    resolver 1.1.1.1 8.8.8.8 valid=300s;
    resolver_timeout 5s;
"""

# Catch-all for any request whose Host header doesn't match one of our
# per-domain server blocks (bare IP hits, stale/typo'd domains, domains
# whose DNS hasn't propagated yet, curl without -H Host, etc).
#
# Without an explicit default_server, nginx silently designates ONE of the
# server blocks loaded from sites-enabled/* as the default - usually
# whichever config file sorts first alphabetically, or, worse, the
# distro-shipped /etc/nginx/sites-enabled/default (which explicitly sets
# default_server and therefore always wins). Either way, unmatched traffic
# gets silently routed to an unrelated site instead of erroring - which
# looks exactly like "my reverse proxy takes me to a completely different
# page no matter what domain I configure."
#
# This block makes "no matching route" an explicit, obvious outcome (HTTP
# 444 - connection closed, no response) instead of an accidental one.
DEFAULT_CATCHALL = """# Managed by ar-reverse-proxy - do not edit by hand
# Catch-all: closes the connection for any Host header that doesn't match
# a configured route, instead of silently falling through to another site.
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    return 444;
}
"""

DEFAULT_CATCHALL_FILENAME = "arrp_00_default_catchall.conf"

# The distro-shipped default site (Debian/Ubuntu nginx package) also marks
# itself default_server. Two default_server blocks on the same
# listen/address is a hard `nginx -t` failure, so it must be removed before
# ours can take effect.
STOCK_DEFAULT_NAMES = ("default",)


def default_catchall_path() -> Path:
    return settings.NGINX_SITES_DIR / DEFAULT_CATCHALL_FILENAME


def default_catchall_enabled_path() -> Path:
    return settings.NGINX_ENABLED_DIR / DEFAULT_CATCHALL_FILENAME


def ensure_default_catchall() -> tuple[bool, str]:
    """
    Idempotently install the default_server catch-all and disable any
    distro-shipped default site that would otherwise conflict with it.

    Safe to call on every startup - it's a no-op if already in place.
    """
    try:
        # Remove the stock default site's *enabled* symlink so it stops
        # competing for default_server. Leave sites-available alone in case
        # the admin wants it back.
        for name in STOCK_DEFAULT_NAMES:
            stock_link = settings.NGINX_ENABLED_DIR / name
            if stock_link.is_symlink() or (stock_link.exists() and stock_link != default_catchall_path()):
                stock_link.unlink()
                logger.info("Disabled distro default nginx site at %s", stock_link)

        path = default_catchall_path()
        path.write_text(DEFAULT_CATCHALL)
        link = default_catchall_enabled_path()
        if not link.exists():
            link.symlink_to(path)

        ok, out = test_nginx()
        if not ok:
            return False, f"nginx -t failed after installing default catch-all:\n{out}"
        return reload_nginx()
    except Exception as e:
        return False, str(e)


def config_path(domain: str) -> Path:
    return settings.NGINX_SITES_DIR / f"arrp_{domain}.conf"


def enabled_path(domain: str) -> Path:
    return settings.NGINX_ENABLED_DIR / f"arrp_{domain}.conf"


def render_config(proxy: Proxy) -> str:
    """
    Generate an nginx config for a proxy.

    Two cases the template handles differently:

    1. Local/LAN backend (default): proxy to host:port over HTTP, send the
       visitor's Host header through, short timeouts.

    2. External HTTPS backend (e.g. base44.app, foo.vercel.app): proxy to the
       hostname over HTTPS, override the Host header so the upstream platform
       knows which tenant to serve, enable SNI, longer timeouts, DNS resolver.

    The trigger for case 2 is `target_scheme == "https"`. When that's set we
    also assume the target_host is a hostname (no port suffix in upstream).
    """
    is_external_https = proxy.target_scheme == "https"

    if is_external_https:
        # CDN/PaaS backend - omit the :port unless it's non-standard
        if proxy.target_port == 443:
            upstream = proxy.target_host
        else:
            upstream = f"{proxy.target_host}:{proxy.target_port}"
        host_header = proxy.host_header_override or proxy.target_host
        ssl_backend_block = SSL_BACKEND_BLOCK
        resolver_block = RESOLVER_BLOCK
        read_timeout = send_timeout = connect_timeout = 300
    else:
        upstream = f"{proxy.target_host}:{proxy.target_port}"
        host_header = proxy.host_header_override or "$host"
        ssl_backend_block = ""
        resolver_block = ""
        read_timeout = send_timeout = 90
        connect_timeout = 60

    return HTTP_TEMPLATE.format(
        domain=proxy.domain,
        scheme=proxy.target_scheme,
        upstream=upstream,
        host_header=host_header,
        websocket_block=WEBSOCKET_BLOCK if proxy.websocket else "",
        ssl_backend_block=ssl_backend_block,
        resolver_block=resolver_block,
        read_timeout=read_timeout,
        send_timeout=send_timeout,
        connect_timeout=connect_timeout,
    )


def write_config(proxy: Proxy) -> Path:
    """
    Write the config file to sites-available, and sync the sites-enabled
    symlink to match proxy.enabled.

    Pausing a route (enabled=False) unlinks it from sites-enabled so nginx
    stops routing it, but leaves the rendered config sitting in
    sites-available so resuming is just re-linking it - no regeneration,
    no fresh SSL request, nothing lost.
    """
    path = config_path(proxy.domain)
    path.write_text(render_config(proxy))
    link = enabled_path(proxy.domain)
    if getattr(proxy, "enabled", True):
        if not link.exists():
            link.symlink_to(path)
    else:
        if link.is_symlink() or link.exists():
            link.unlink()
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
