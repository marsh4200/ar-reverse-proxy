# Changelog

## v1.3.0 — 2026-08-11

A full redesign of the web interface. **No breaking changes** — every existing API
endpoint keeps its original contract, and the nginx generation, SSL and update logic
are untouched.

**Redesigned interface**

- New dark theme on layered navy surfaces with a cyan signal accent, matching the
  AR platform design language
- New AR Proxy brand mark, wordmark and favicon
- Routes are drawn as the hop they represent: public domain, connector carrying the
  TLS / WebSocket / external-host state, then upstream
- Stat cards for total routes, HTTPS coverage, WebSocket routes and live nginx state
- Search across domains and upstreams
- Create and edit share one modal; the Host header override only appears for HTTPS
  upstreams, where it applies
- Delete now uses a proper confirmation dialog instead of a browser `confirm()`
- Stacking toasts with titles, replacing the single-slot toast
- Settings moved into a drawer with account, password, updates and host details
- Responsive to 390px, keyboard accessible, honours `prefers-reduced-motion`

**Removed a runtime dependency**

- The panel no longer loads Tailwind from `cdn.tailwindcss.com`. Styling is now
  hand-written CSS served from the app itself, so the dashboard renders correctly on
  an isolated network and no longer flashes unstyled content while the CDN compiles.
  No build step was added — `install.sh` is unchanged and Node is still not required.

**Added**

- `GET /api/system/status` — live nginx service state, config validity, certbot
  availability, hostname, uptime and load. Standard-library only; nothing was added to
  `requirements.txt`. The UI degrades quietly when talking to an older backend.
- Editing an existing route from the UI, which uses the `PUT /api/proxies/{id}`
  endpoint that already existed but was never surfaced.

**Fixed**

- API validation errors now render inline in the route form instead of as raw JSON
