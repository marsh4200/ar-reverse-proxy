/* ══════════════════════════════════════════════════════════════════════════
   AR Reverse Proxy — dashboard
   Cookie auth (httpOnly) handles itself; we just fetch with credentials.
   ══════════════════════════════════════════════════════════════════════════ */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

let ROUTES = [];          // last-loaded proxy list
let SEARCH = "";
let PENDING_DELETE = null;

/* ── Icons (inline so there's no icon-font dependency) ─────────────────── */
const ICON = {
  check: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 6 9 17l-5-5"/></svg>',
  cross: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/></svg>',
  warn:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
  info:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>',
  x:     '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  lock:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
  edit:  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/></svg>',
  trash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>',
  ext:   '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="ext"><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>',
};

/* ── Toasts ────────────────────────────────────────────────────────────── */
function toast(title, message = "", kind = "info", ms = 4500) {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `
    ${kind === "success" ? ICON.check : kind === "error" ? ICON.cross : kind === "warn" ? ICON.warn : ICON.info}
    <div style="min-width:0;flex:1">
      <div class="toast-title">${esc(title)}</div>
      ${message ? `<div class="toast-msg">${esc(message)}</div>` : ""}
    </div>
    <button class="toast-close" aria-label="Dismiss">${ICON.x}</button>`;

  const remove = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 180);
  };
  el.querySelector(".toast-close").addEventListener("click", remove);
  $("#toasts").appendChild(el);
  setTimeout(remove, ms);
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/* Extract a readable message from a FastAPI error body. */
async function errorText(res) {
  try {
    const body = await res.json();
    const d = body.detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return d.map((e) => e.msg || JSON.stringify(e)).join("\n");
    if (d) return JSON.stringify(d);
  } catch { /* not JSON */ }
  return `Request failed (${res.status})`;
}

/* Toggle a button between idle and busy without the width jumping. */
function busy(btn, on, busyLabel) {
  const label = btn.querySelector(".btn-label");
  if (on) {
    btn.dataset.label = label ? label.textContent : "";
    btn.classList.add("is-busy");
    btn.disabled = true;
    if (label && busyLabel) label.textContent = busyLabel;
  } else {
    btn.classList.remove("is-busy");
    btn.disabled = false;
    if (label && btn.dataset.label) label.textContent = btn.dataset.label;
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   ROUTES
   ══════════════════════════════════════════════════════════════════════════ */

async function loadRoutes() {
  try {
    const r = await fetch("/api/proxies");
    if (!r.ok) throw new Error(await errorText(r));
    ROUTES = await r.json();
    renderRoutes();
    renderStats();
  } catch (e) {
    toast("Could not load routes", e.message, "error");
  }
}

function matchesSearch(p) {
  if (!SEARCH) return true;
  const q = SEARCH.toLowerCase();
  return [p.domain, p.target_host, p.host_header_override, p.notes]
    .filter(Boolean)
    .some((v) => String(v).toLowerCase().includes(q));
}

function renderRoutes() {
  const list = $("#route-list");
  const shown = ROUTES.filter(matchesSearch);

  $("#route-count").textContent = ROUTES.length === 0
    ? ""
    : `${shown.length}${shown.length !== ROUTES.length ? ` of ${ROUTES.length}` : ""} ${ROUTES.length === 1 ? "route" : "routes"}`;

  $("#empty-none").classList.toggle("hidden", ROUTES.length !== 0);
  $("#empty-search").classList.toggle("hidden", !(ROUTES.length > 0 && shown.length === 0));
  if (ROUTES.length > 0 && shown.length === 0) {
    $("#empty-search-text").textContent = `Nothing matches "${SEARCH}".`;
  }

  list.innerHTML = shown.map(routeRow).join("");

  $$("[data-edit]", list).forEach((b) =>
    b.addEventListener("click", () => openRouteModal(byId(b.dataset.edit))));
  $$("[data-del]", list).forEach((b) =>
    b.addEventListener("click", () => openDelete(byId(b.dataset.del))));
  $$("[data-ssl]", list).forEach((b) =>
    b.addEventListener("click", () => issueSSL(b.dataset.ssl, b)));
  $$("[data-toggle]", list).forEach((el) =>
    el.addEventListener("change", () => toggleProxy(el.dataset.toggle, el)));
}

const byId = (id) => ROUTES.find((p) => String(p.id) === String(id));

/* The signature row: origin ──wire──> upstream */
function routeRow(p) {
  const isExternal = p.target_scheme === "https";
  const scheme = p.ssl_enabled ? "https" : "http";
  const port = isExternal && p.target_port === 443 ? "" : `:${p.target_port}`;
  const enabled = p.enabled !== false;

  const tags = [
    enabled ? "" : '<span class="tag tag-paused">paused</span>',
    p.ssl_enabled
      ? '<span class="tag tag-tls">tls</span>'
      : '<span class="tag tag-off">no tls</span>',
    p.websocket ? '<span class="tag tag-ws">ws</span>' : "",
    isExternal ? '<span class="tag tag-ext">ext</span>' : "",
  ].filter(Boolean).join("");

  return `
  <div class="route${enabled ? "" : " is-paused"}">
    <div class="route-origin">
      <div class="route-domain">
        <a href="${scheme}://${esc(p.domain)}" target="_blank" rel="noopener noreferrer"
           title="Open ${esc(p.domain)}">
          <span class="truncate">${esc(p.domain)}</span>${ICON.ext}
        </a>
      </div>
      ${p.notes ? `<div class="route-note">${esc(p.notes)}</div>` : ""}
    </div>

    <div class="route-link" aria-hidden="true">
      <div class="route-wire"><i></i></div>
      <div class="route-tags">${tags}</div>
    </div>

    <div class="route-target">
      <div class="route-upstream" title="${esc(p.target_scheme)}://${esc(p.target_host)}:${p.target_port}">
        <span class="scheme">${esc(p.target_scheme)}://</span><span class="host">${esc(p.target_host)}</span><span class="port">${port}</span>
      </div>
      ${p.host_header_override
        ? `<div class="route-hostheader">Host: <code>${esc(p.host_header_override)}</code></div>`
        : ""}
    </div>

    <div class="route-actions">
      <label class="switch" title="${enabled ? "Pause this route" : "Resume this route"}">
        <input type="checkbox" data-toggle="${p.id}" ${enabled ? "checked" : ""}
               aria-label="${enabled ? "Pause" : "Resume"} ${esc(p.domain)}">
        <span class="switch-track"><span class="switch-thumb"></span></span>
      </label>
      ${!p.ssl_enabled ? `
        <button class="btn btn-xs btn-outline" data-ssl="${p.id}" title="Request a Let's Encrypt certificate">
          ${ICON.lock}<span class="btn-label">Secure</span>
        </button>` : ""}
      <button class="btn btn-icon-sm btn-ghost" data-edit="${p.id}" aria-label="Edit ${esc(p.domain)}" title="Edit">
        ${ICON.edit}
      </button>
      <button class="btn btn-icon-sm btn-ghost" data-del="${p.id}" aria-label="Delete ${esc(p.domain)}" title="Delete">
        ${ICON.trash}
      </button>
    </div>
  </div>`;
}

/* ── Pause / resume ────────────────────────────────────────────────────── */

async function toggleProxy(id, input) {
  const proxy = byId(id);
  if (!proxy) return;
  const wasEnabled = proxy.enabled !== false;

  input.disabled = true;
  try {
    const res = await fetch(`/api/proxies/${id}/toggle`, { method: "POST" });
    if (!res.ok) {
      input.checked = wasEnabled;
      toast("Could not change route state", await errorText(res), "error");
      return;
    }
    const updated = await res.json();
    const idx = ROUTES.findIndex((r) => String(r.id) === String(updated.id));
    if (idx !== -1) ROUTES[idx] = updated;

    renderRoutes();
    toast(
      updated.enabled ? "Route resumed" : "Route paused",
      updated.enabled
        ? `${updated.domain} is routed again.`
        : `${updated.domain} is paused. Its nginx config is kept, just not linked in.`,
      "success",
    );
  } catch (e) {
    input.checked = wasEnabled;
    toast("Could not change route state", e.message, "error");
  } finally {
    input.disabled = false;
  }
}

function renderStats() {
  const total = ROUTES.length;
  const ssl = ROUTES.filter((p) => p.ssl_enabled).length;
  const ws = ROUTES.filter((p) => p.websocket).length;

  $("#stat-total").textContent = total;
  $("#stat-total-hint").textContent = total === 1 ? "Domain served" : "Domains served";

  $("#stat-ssl").textContent = ssl;
  $("#stat-ssl-hint").textContent = total === 0
    ? "No routes yet"
    : ssl === total ? "Every route is secured" : `${total - ssl} still on plain HTTP`;
  $("#stat-ssl-icon").className = "stat-icon " + (total > 0 && ssl < total ? "warn" : "ok");

  $("#stat-ws").textContent = ws;
}

/* ══════════════════════════════════════════════════════════════════════════
   ROUTE MODAL — create and edit share one form
   ══════════════════════════════════════════════════════════════════════════ */

function openRouteModal(proxy) {
  const form = $("#route-form");
  form.reset();
  $("#route-error").classList.add("hidden");

  const editing = !!proxy;
  $("#route-modal-title").textContent = editing ? `Edit ${proxy.domain}` : "New route";
  $("#route-modal-desc").textContent = editing
    ? "The domain is fixed once a route exists. Delete and recreate to change it."
    : "Point a domain at a service. The nginx config is written and reloaded when you save.";
  $("#btn-save-route").querySelector(".btn-label").textContent =
    editing ? "Save changes" : "Create route";

  form.id.value = editing ? proxy.id : "";
  $("#f-domain").value = editing ? proxy.domain : "";
  $("#f-domain").disabled = editing;
  $("#f-scheme").value = editing ? proxy.target_scheme : "http";
  $("#f-host").value = editing ? proxy.target_host : "127.0.0.1";
  $("#f-port").value = editing ? proxy.target_port : "";
  $("#f-hostheader").value = editing ? (proxy.host_header_override || "") : "";
  $("#f-ws").checked = editing ? !!proxy.websocket : true;

  // Certificates are requested from the row action, not re-requested on edit.
  const sslRow = $("#f-ssl").closest(".check");
  $("#f-ssl").checked = false;
  sslRow.classList.toggle("hidden", editing);

  syncSchemeUI();
  showModal("#route-overlay", "#route-modal");
  setTimeout(() => (editing ? $("#f-host") : $("#f-domain")).focus(), 60);
}

/* The Host header field only matters for HTTPS upstreams, so only show it then. */
function syncSchemeUI() {
  const external = $("#f-scheme").value === "https";
  $("#f-hostheader-wrap").classList.toggle("hidden", !external);

  const port = $("#f-port");
  const host = $("#f-host");

  if (external) {
    // An HTTPS upstream is almost always a hosted platform, so the loopback
    // default is wrong. Clear it rather than letting it be submitted.
    if (host.value.trim() === "127.0.0.1") host.value = "";
    if (!port.value) port.value = 443;
    host.placeholder = "myapp.base44.app";
  } else {
    if (!host.value.trim()) host.value = "127.0.0.1";
    if (port.value === "443") port.value = "";
    host.placeholder = "127.0.0.1";
  }
}

async function saveRoute() {
  const btn = $("#btn-save-route");
  const form = $("#route-form");
  const id = form.id.value;
  const editing = !!id;

  if (!form.reportValidity()) return;

  const errBox = $("#route-error");
  errBox.classList.add("hidden");

  const payload = {
    target_host: $("#f-host").value.trim(),
    target_port: parseInt($("#f-port").value, 10),
    target_scheme: $("#f-scheme").value,
    host_header_override: $("#f-scheme").value === "https"
      ? $("#f-hostheader").value.trim()
      : "",
    websocket: $("#f-ws").checked,
  };
  if (!editing) {
    payload.domain = $("#f-domain").value.trim();
    payload.ssl_enabled = $("#f-ssl").checked;
    payload.notes = "";
  }

  busy(btn, true, editing ? "Saving" : "Creating");
  try {
    const res = await fetch(editing ? `/api/proxies/${id}` : "/api/proxies", {
      method: editing ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      $("#route-error-title").textContent = editing
        ? "Could not save the route"
        : "Could not create the route";
      $("#route-error-body").textContent = await errorText(res);
      errBox.classList.remove("hidden");
      errBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }

    const saved = await res.json();
    closeModal("#route-overlay", "#route-modal");
    toast(
      editing ? "Route updated" : "Route created",
      `${saved.domain} is live and nginx has been reloaded.`,
      "success",
    );
    loadRoutes();
    loadSystem();
  } catch (e) {
    $("#route-error-body").textContent = e.message;
    errBox.classList.remove("hidden");
  } finally {
    busy(btn, false);
  }
}

/* ── Delete ────────────────────────────────────────────────────────────── */

function openDelete(proxy) {
  PENDING_DELETE = proxy;
  $("#del-title").textContent = `Delete ${proxy.domain}?`;
  $("#del-desc").textContent = `Visitors to ${proxy.domain} will stop reaching ${proxy.target_host}. This cannot be undone.`;
  showModal("#del-overlay", "#del-modal");
}

async function confirmDelete() {
  if (!PENDING_DELETE) return;
  const btn = $("#btn-confirm-delete");
  const { id, domain } = PENDING_DELETE;

  busy(btn, true, "Deleting");
  try {
    const res = await fetch(`/api/proxies/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) {
      toast("Could not delete the route", await errorText(res), "error", 8000);
      return;
    }
    closeModal("#del-overlay", "#del-modal");
    toast("Route deleted", `${domain} is no longer served.`, "success");
    loadRoutes();
  } catch (e) {
    toast("Could not delete the route", e.message, "error");
  } finally {
    busy(btn, false);
    PENDING_DELETE = null;
  }
}

/* ── SSL ───────────────────────────────────────────────────────────────── */

async function issueSSL(id, btn) {
  const proxy = byId(id);
  busy(btn, true, "Working");
  toast(
    "Requesting certificate",
    `certbot is verifying ${proxy.domain}. This usually takes under a minute.`,
    "info",
    9000,
  );
  try {
    const res = await fetch(`/api/proxies/${id}/ssl`, { method: "POST" });
    const data = await res.json();
    if (data.ok) {
      toast("HTTPS is on", `${proxy.domain} now has a certificate and redirects to HTTPS.`, "success");
      loadRoutes();
    } else {
      toast("Certificate request failed", data.message || "certbot reported an error.", "error", 12000);
    }
  } catch (e) {
    toast("Certificate request failed", e.message, "error");
  } finally {
    busy(btn, false);
  }
}

/* ══════════════════════════════════════════════════════════════════════════
   SYSTEM STATUS  (optional endpoint — degrade quietly if absent)
   ══════════════════════════════════════════════════════════════════════════ */

let SYSTEM_SUPPORTED = true;

async function loadSystem() {
  if (!SYSTEM_SUPPORTED) return;
  try {
    const r = await fetch("/api/system/status");
    if (r.status === 404) { SYSTEM_SUPPORTED = false; markNginxUnknown(); return; }
    if (!r.ok) return;
    const s = await r.json();

    const running = !!s.nginx_running;
    const configOk = s.nginx_config_ok !== false;

    $("#nginx-dot").className = "dot " + (running ? (configOk ? "ok pulse" : "warn") : "crit");
    $("#nginx-label").textContent = running
      ? (configOk ? "nginx running" : "nginx config error")
      : "nginx stopped";

    $("#stat-nginx").textContent = running ? "Running" : "Stopped";
    $("#stat-nginx-hint").textContent = configOk
      ? (s.nginx_state || "active")
      : "Configuration test failed";
    $("#stat-nginx-icon").className = "stat-icon " + (running ? (configOk ? "ok" : "warn") : "crit");

    $("#about-host").textContent = s.hostname || "—";
    $("#about-uptime").textContent = s.uptime_seconds ? uptime(s.uptime_seconds) : "—";
    $("#about-nginx").textContent = running ? (s.nginx_state || "running") : "stopped";
    $("#about-certbot").textContent = s.certbot_available ? "installed" : "not installed";
  } catch {
    markNginxUnknown();
  }
}

function markNginxUnknown() {
  $("#nginx-pill").classList.add("hidden");
  $("#stat-nginx").textContent = "—";
  $("#stat-nginx-hint").textContent = "Status needs a newer backend";
}

function uptime(sec) {
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d) return `${d}d ${h}h`;
  if (h) return `${h}h ${m}m`;
  return `${m}m`;
}

/* ══════════════════════════════════════════════════════════════════════════
   PASSWORD
   ══════════════════════════════════════════════════════════════════════════ */

async function changePassword(e) {
  e.preventDefault();
  const btn = $("#btn-save-pw");
  const errBox = $("#pw-error");
  const current = $("#pw-current").value;
  const next = $("#pw-new").value;
  const confirm = $("#pw-confirm").value;

  errBox.classList.add("hidden");

  if (next !== confirm) {
    $("#pw-error-text").textContent = "The new password and its confirmation do not match.";
    errBox.classList.remove("hidden");
    return;
  }

  busy(btn, true, "Saving");
  try {
    const res = await fetch("/api/settings/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: current, new_password: next }),
    });
    if (!res.ok) {
      $("#pw-error-text").textContent = await errorText(res);
      errBox.classList.remove("hidden");
      return;
    }
    $("#pw-form").reset();
    $("#pw-warning").classList.add("hidden");
    toast("Password updated", "Existing sessions stay signed in.", "success");
  } catch (e2) {
    $("#pw-error-text").textContent = e2.message;
    errBox.classList.remove("hidden");
  } finally {
    busy(btn, false);
  }
}

async function checkDefaultPassword() {
  try {
    const r = await fetch("/api/settings/me");
    if (!r.ok) return;
    const data = await r.json();
    $("#pw-warning").classList.toggle("hidden", !data.using_default_password);
  } catch { /* non-critical */ }
}

/* ══════════════════════════════════════════════════════════════════════════
   UPDATES
   ══════════════════════════════════════════════════════════════════════════ */

async function checkUpdate(announce = false) {
  const btn = $("#btn-check-update");
  const status = $("#update-status");
  if (announce) busy(btn, true, "Checking");
  status.innerHTML = `<div class="faint" style="font-size:11px">Checking GitHub…</div>`;

  try {
    const r = await fetch("/api/update/status");
    if (!r.ok) throw new Error(await errorText(r));
    const d = await r.json();

    $("#local-version").textContent = d.local_version;

    const remoteEl = $("#remote-version");
    const runBtn = $("#btn-run-update");
    const pill = $("#update-pill");

    if (d.remote_version) {
      remoteEl.innerHTML = `<span style="color:${d.update_available ? "var(--signal-300)" : "var(--ink)"}">v${esc(d.remote_version)}</span>`;
    } else {
      remoteEl.innerHTML = `<span class="ghost">unreachable</span>`;
    }
    $("#remote-well").style.borderColor = d.update_available ? "rgba(14,165,233,.3)" : "";
    $("#remote-well").style.background = d.update_available ? "rgba(14,165,233,.08)" : "";

    if (d.update_available) {
      status.innerHTML = `
        <div class="alert alert-signal">
          ${ICON.info}
          <div style="min-width:0">
            <div class="alert-title">Version ${esc(d.remote_version)} is available</div>
            <div class="alert-body">The service restarts during the update. It takes about a minute.</div>
          </div>
        </div>`;
      runBtn.classList.remove("hidden");
      $("#pill-version").textContent = d.remote_version;
      pill.classList.remove("hidden");
      if (announce) toast("Update available", `Version ${d.remote_version} is ready to install.`, "info");
    } else if (d.remote_version) {
      status.innerHTML = `
        <div class="alert alert-ok">
          ${ICON.check}
          <div class="alert-body" style="margin-top:0">You're running the latest version.</div>
        </div>`;
      runBtn.classList.add("hidden");
      pill.classList.add("hidden");
      if (announce) toast("Up to date", "You're on the latest version.", "success");
    } else {
      status.innerHTML = `
        <div class="alert alert-warn">
          ${ICON.warn}
          <div class="alert-body" style="margin-top:0">
            Could not reach GitHub. Check this server's outbound connection.
          </div>
        </div>`;
      runBtn.classList.add("hidden");
      pill.classList.add("hidden");
      if (announce) toast("Could not check for updates", "GitHub was unreachable.", "warn");
    }
  } catch (e) {
    status.innerHTML = `<div class="alert alert-warn">${ICON.warn}<div class="alert-body" style="margin-top:0">${esc(e.message)}</div></div>`;
    if (announce) toast("Update check failed", e.message, "error");
  } finally {
    if (announce) busy(btn, false);
  }
}

async function runUpdate() {
  const btn = $("#btn-run-update");
  const log = $("#update-log");

  busy(btn, true, "Updating");
  log.classList.remove("hidden");
  log.textContent = "";
  logLine(log, "Starting update…");

  try {
    const r = await fetch("/api/update/run", { method: "POST" });
    const data = await r.json();
    logLine(log, data.message || "Update triggered.");

    if (data.ok) {
      logLine(log, "Service is restarting. Waiting for it to come back…");
      const back = await waitForRestart(log);
      if (back) {
        logLine(log, "Back online. Reloading the page…");
        setTimeout(() => location.reload(), 1200);
      }
    } else {
      logLine(log, "Update failed. The previous version is still installed.");
      toast("Update failed", data.message || "See the log for details.", "error", 10000);
      busy(btn, false);
    }
  } catch {
    // The connection dropping mid-update is expected — the service is restarting.
    logLine(log, "Connection dropped (expected during restart). Waiting…");
    const back = await waitForRestart(log);
    if (back) {
      logLine(log, "Back online. Reloading the page…");
      setTimeout(() => location.reload(), 1200);
    } else {
      busy(btn, false);
    }
  }
}

function logLine(box, text) {
  box.textContent += (box.textContent ? "\n" : "") + "→ " + text;
  box.scrollTop = box.scrollHeight;
}

async function waitForRestart(log) {
  for (let i = 0; i < 45; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    try {
      const r = await fetch("/healthz", { cache: "no-store" });
      if (r.ok) return true;
    } catch { /* still down */ }
    if (i % 3 === 0 && i > 0) logLine(log, `still waiting (${(i + 1) * 2}s)`);
  }
  logLine(log, "Timed out. Check: journalctl -u ar-reverse-proxy");
  toast("Update timed out", "The service did not come back. Check the server logs.", "error", 12000);
  return false;
}

/* ══════════════════════════════════════════════════════════════════════════
   OVERLAYS
   ══════════════════════════════════════════════════════════════════════════ */

function showModal(overlaySel, modalSel) {
  $(overlaySel).classList.remove("hidden");
  $(modalSel).classList.remove("hidden");
  document.body.style.overflow = "hidden";
}

function closeModal(overlaySel, modalSel) {
  $(overlaySel).classList.add("hidden");
  $(modalSel).classList.add("hidden");
  if (!anyOverlayOpen()) document.body.style.overflow = "";
}

function anyOverlayOpen() {
  return !$("#route-modal").classList.contains("hidden")
      || !$("#del-modal").classList.contains("hidden")
      || $("#settings-drawer").classList.contains("open");
}

function openSettings() {
  $("#settings-overlay").classList.remove("hidden");
  requestAnimationFrame(() => $("#settings-drawer").classList.add("open"));
  document.body.style.overflow = "hidden";
  closeAccountMenu();
  checkUpdate();
}

function closeSettings() {
  $("#settings-drawer").classList.remove("open");
  setTimeout(() => {
    $("#settings-overlay").classList.add("hidden");
    if (!anyOverlayOpen()) document.body.style.overflow = "";
  }, 280);
}

function closeAccountMenu() {
  $("#account-menu").classList.add("hidden");
  $("#menu-trigger").setAttribute("aria-expanded", "false");
}

/* ══════════════════════════════════════════════════════════════════════════
   BOOT
   ══════════════════════════════════════════════════════════════════════════ */

document.addEventListener("DOMContentLoaded", () => {
  // Routes
  $("#btn-new").addEventListener("click", () => openRouteModal(null));
  $("#btn-new-empty").addEventListener("click", () => openRouteModal(null));
  $("#btn-refresh").addEventListener("click", async (e) => {
    busy(e.currentTarget, true, "Refreshing");
    await Promise.all([loadRoutes(), loadSystem()]);
    busy(e.currentTarget, false);
  });
  $("#btn-save-route").addEventListener("click", saveRoute);
  $("#route-form").addEventListener("submit", (e) => { e.preventDefault(); saveRoute(); });
  $("#f-scheme").addEventListener("change", syncSchemeUI);
  $$("[data-close-route]").forEach((b) =>
    b.addEventListener("click", () => closeModal("#route-overlay", "#route-modal")));
  $("#route-overlay").addEventListener("click", () => closeModal("#route-overlay", "#route-modal"));

  // Delete
  $("#btn-confirm-delete").addEventListener("click", confirmDelete);
  $$("[data-close-del]").forEach((b) =>
    b.addEventListener("click", () => closeModal("#del-overlay", "#del-modal")));
  $("#del-overlay").addEventListener("click", () => closeModal("#del-overlay", "#del-modal"));

  // Search
  $("#search").addEventListener("input", (e) => { SEARCH = e.target.value.trim(); renderRoutes(); });
  $("#btn-clear-search").addEventListener("click", () => {
    SEARCH = ""; $("#search").value = ""; renderRoutes();
  });

  // Account menu
  $("#menu-trigger").addEventListener("click", (e) => {
    e.stopPropagation();
    const menu = $("#account-menu");
    const open = menu.classList.toggle("hidden");
    $("#menu-trigger").setAttribute("aria-expanded", String(!open));
  });
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".menu-wrap")) closeAccountMenu();
  });

  // Settings
  $("#menu-settings").addEventListener("click", openSettings);
  $("#update-pill").addEventListener("click", openSettings);
  $("#btn-fix-password").addEventListener("click", () => {
    openSettings();
    setTimeout(() => $("#pw-current").focus(), 340);
  });
  $("#btn-close-settings").addEventListener("click", closeSettings);
  $("#settings-overlay").addEventListener("click", closeSettings);
  $("#pw-form").addEventListener("submit", changePassword);
  $("#btn-check-update").addEventListener("click", () => checkUpdate(true));
  $("#btn-run-update").addEventListener("click", runUpdate);

  // Escape closes the topmost layer
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!$("#del-modal").classList.contains("hidden")) closeModal("#del-overlay", "#del-modal");
    else if (!$("#route-modal").classList.contains("hidden")) closeModal("#route-overlay", "#route-modal");
    else if ($("#settings-drawer").classList.contains("open")) closeSettings();
    else closeAccountMenu();
  });

  // Initial load
  loadRoutes();
  loadSystem();
  checkUpdate();
  checkDefaultPassword();

  // Keep nginx state fresh while the tab is visible
  setInterval(() => { if (document.visibilityState === "visible") loadSystem(); }, 20000);
});
