# ar-reverse-proxy

A self-hosted reverse proxy manager for Ubuntu 24.04. FastAPI + SQLite + nginx + Let's Encrypt, with a GitHub-based in-app update system.

## Install

One line, on a fresh Ubuntu 24.04 box (run as root or with sudo):

```bash
curl -sSL https://raw.githubusercontent.com/marsh4200/ar-reverse-proxy/main/install.sh | sudo bash
```

The installer:

- Installs `nginx`, `certbot`, `python3-venv`, `git`, `ufw`
- Clones the repo to `/opt/ar-reverse-proxy`
- Creates a Python venv and installs requirements
- Writes `/etc/ar-reverse-proxy/env` with a freshly generated `SECRET_KEY`
- Registers and starts the `ar-reverse-proxy` systemd service
- Opens ports 80, 443, and 9913 via `ufw`

When it finishes, the dashboard is at `http://<server-ip>:9913` with the default login `admin` / `admin`. Change the password by editing `ARRP_ADMIN_PASS` in `/etc/ar-reverse-proxy/env` before first start, or by replacing the user row in SQLite afterward.

> **Before publishing your fork:** edit the `GITHUB_REPO` variable at the top of `install.sh` so the one-liner clones your repo.

## What it does

- Add a reverse proxy from the dashboard (domain → host:port) and the backend writes `/etc/nginx/sites-available/arrp_<domain>.conf`, symlinks it into `sites-enabled`, runs `nginx -t`, and reloads nginx. If `nginx -t` fails, the new config is rolled back automatically.
- Tick "Auto-SSL" to have `certbot --nginx` provision a Let's Encrypt certificate for the domain (the DNS must already point at the server).
- WebSocket support is on by default and adds the `Upgrade` / `Connection` headers to the generated config.

## Updates

Click **Check for updates** in the header. The backend fetches `VERSION` from `raw.githubusercontent.com/<repo>/<branch>/VERSION` and compares it to the local `VERSION` file.

If a newer version exists, the banner shows it and **Install update** triggers `scripts/update.sh`, which:

1. Detaches from the FastAPI process (so `systemctl restart` can't kill it mid-flight).
2. `git fetch && git reset --hard origin/<branch>`
3. Re-installs `requirements.txt` into the venv.
4. Re-installs the systemd unit if it changed.
5. Restarts the service.

The dashboard polls `/healthz` until the new process is up, then reloads itself. Update logs go to `/var/log/ar-reverse-proxy-update.log` and the `update_logs` SQLite table.

To cut a release, bump the number in `VERSION`, commit, and push to `main`.

## Project layout

```
ar-reverse-proxy/
├── VERSION                          # version string compared against GitHub
├── install.sh                       # one-line installer
├── requirements.txt
├── app/
│   ├── main.py                      # FastAPI entrypoint
│   ├── config.py                    # Settings (env-driven)
│   ├── database.py                  # SQLAlchemy engine/session
│   ├── models.py                    # User, Proxy, UpdateLog
│   ├── schemas.py                   # Pydantic I/O models
│   ├── auth.py                      # JWT + bcrypt + cookie helpers
│   ├── routers/
│   │   ├── auth.py                  # /login, /logout, /api/login
│   │   ├── proxies.py               # /api/proxies CRUD
│   │   └── update.py                # /api/update status + run
│   ├── services/
│   │   ├── nginx_service.py         # config generation, nginx -t, reload, certbot
│   │   └── update_service.py        # GitHub VERSION check + run update.sh
│   ├── templates/                   # Jinja2: base, login, dashboard
│   └── static/                      # Tailwind CDN + small CSS/JS
├── scripts/
│   └── update.sh                    # pulled + executed during in-app update
└── systemd/
    └── ar-reverse-proxy.service
```

## Stack

- **FastAPI** for the API and HTML rendering
- **SQLite** via SQLAlchemy at `/var/lib/ar-reverse-proxy/arrp.db`
- **JWT** (HS256) in an httpOnly cookie for session auth
- **TailwindCSS** via CDN (no build step)
- **systemd** unit running uvicorn on `:9913`

## Operations

| Action | Command |
|---|---|
| Status | `systemctl status ar-reverse-proxy` |
| Logs | `journalctl -u ar-reverse-proxy -f` |
| Restart | `systemctl restart ar-reverse-proxy` |
| Update log | `tail -f /var/log/ar-reverse-proxy-update.log` |
| Manual update | `sudo /opt/ar-reverse-proxy/scripts/update.sh` |
| Config | `/etc/ar-reverse-proxy/env` |
| DB | `/var/lib/ar-reverse-proxy/arrp.db` |
| Generated nginx | `/etc/nginx/sites-available/arrp_*.conf` |

## Security notes

- Runs as **root** because it needs to write nginx config, reload nginx, and invoke certbot. Don't expose port 9913 to the public internet — put the dashboard itself behind an nginx vhost with SSL + IP allow-list, or bind it to `127.0.0.1` and tunnel.
- The default `admin`/`admin` credentials exist purely for first-run bootstrap. Change them.
- `SECRET_KEY` is generated once by the installer and persisted in `/etc/ar-reverse-proxy/env`. Rotating it invalidates all sessions.
