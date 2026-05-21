// Dashboard logic for ar-reverse-proxy.
// Cookie auth (httpOnly) handles itself - we just fetch with credentials.

const $ = (sel) => document.querySelector(sel);

// ---------- Toast ----------
function toast(msg, kind = "info") {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.remove("hidden", "border-red-500/60", "border-green-500/60", "border-slate-700");
    if (kind === "error") el.classList.add("border-red-500/60");
    else if (kind === "success") el.classList.add("border-green-500/60");
    else el.classList.add("border-slate-700");
    setTimeout(() => el.classList.add("hidden"), 4500);
}

function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
}

// ============================================================
// PROXIES
// ============================================================
async function loadProxies() {
    const r = await fetch("/api/proxies");
    if (!r.ok) { toast("Failed to load proxies", "error"); return; }
    renderProxies(await r.json());
}

function renderProxies(items) {
    const list = $("#proxy-list");
    const empty = $("#empty-state");
    $("#proxy-count").textContent = `${items.length} ${items.length === 1 ? "entry" : "entries"}`;

    if (items.length === 0) {
        list.innerHTML = "";
        empty.classList.remove("hidden");
        return;
    }
    empty.classList.add("hidden");

    list.innerHTML = items.map((p) => `
        <div class="group border border-slate-800 hover:border-slate-700 bg-slate-900/30 transition-colors">
            <div class="grid grid-cols-12 items-center px-5 py-4 gap-4">
                <div class="col-span-12 md:col-span-5">
                    <div class="flex items-center gap-2 flex-wrap">
                        <span class="text-base text-slate-100">${escapeHtml(p.domain)}</span>
                        ${p.ssl_enabled
                            ? '<span class="text-[10px] uppercase tracking-widest text-green-400 border border-green-500/40 px-1.5 py-0.5">ssl</span>'
                            : '<span class="text-[10px] uppercase tracking-widest text-slate-500 border border-slate-700 px-1.5 py-0.5">http</span>'}
                        ${p.websocket
                            ? '<span class="text-[10px] uppercase tracking-widest text-cyan-400/80 border border-cyan-500/30 px-1.5 py-0.5">ws</span>'
                            : ''}
                        ${p.host_header_override
                            ? '<span class="text-[10px] uppercase tracking-widest text-purple-400/80 border border-purple-500/30 px-1.5 py-0.5">ext</span>'
                            : ''}
                    </div>
                    ${p.notes ? `<div class="text-xs text-slate-500 mt-1">${escapeHtml(p.notes)}</div>` : ""}
                </div>
                <div class="col-span-8 md:col-span-5 text-sm text-slate-400 truncate">
                    <span class="text-slate-600">→</span>
                    ${escapeHtml(p.target_scheme)}://${escapeHtml(p.target_host)}:${p.target_port}
                </div>
                <div class="col-span-4 md:col-span-2 flex justify-end gap-2">
                    ${!p.ssl_enabled ? `
                        <button data-ssl="${p.id}"
                                class="text-[10px] uppercase tracking-widest px-2 py-1 border border-slate-700 hover:border-green-500/60 hover:text-green-300 transition-colors">
                            ssl
                        </button>` : ""}
                    <button data-delete="${p.id}" data-domain="${escapeHtml(p.domain)}"
                            class="text-[10px] uppercase tracking-widest px-2 py-1 border border-slate-700 hover:border-red-500/60 hover:text-red-300 transition-colors">
                        delete
                    </button>
                </div>
            </div>
        </div>
    `).join("");

    list.querySelectorAll("[data-delete]").forEach((b) => {
        b.addEventListener("click", () => deleteProxy(b.dataset.delete, b.dataset.domain));
    });
    list.querySelectorAll("[data-ssl]").forEach((b) => {
        b.addEventListener("click", () => issueSSL(b.dataset.ssl));
    });
}

async function createProxy(e) {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const payload = {
        domain: fd.get("domain"),
        target_host: fd.get("target_host"),
        target_port: parseInt(fd.get("target_port"), 10),
        target_scheme: fd.get("target_scheme"),
        host_header_override: fd.get("host_header_override") || "",
        ssl_enabled: fd.get("ssl_enabled") === "on",
        websocket: fd.get("websocket") === "on",
        notes: "",
    };

    const errEl = $("#form-error");
    errEl.classList.add("hidden");

    const r = await fetch("/api/proxies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });

    if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: "Unknown error" }));
        errEl.textContent = typeof err.detail === "string" ? err.detail : JSON.stringify(err.detail);
        errEl.classList.remove("hidden");
        return;
    }
    form.reset();
    form.querySelector('[name="target_host"]').value = "127.0.0.1";
    form.querySelector('[name="websocket"]').checked = true;
    toast("Proxy created and nginx reloaded.", "success");
    loadProxies();
}

async function deleteProxy(id, domain) {
    if (!confirm(`Delete proxy for ${domain}? This removes its nginx config.`)) return;
    const r = await fetch(`/api/proxies/${id}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) {
        const err = await r.json().catch(() => ({}));
        toast(err.detail || "Delete failed", "error");
        return;
    }
    toast("Proxy removed.", "success");
    loadProxies();
}

async function issueSSL(id) {
    toast("Requesting Let's Encrypt certificate… this may take a moment.");
    const r = await fetch(`/api/proxies/${id}/ssl`, { method: "POST" });
    const data = await r.json();
    if (data.ok) {
        toast("SSL certificate installed.", "success");
        loadProxies();
    } else {
        toast(data.message || "SSL request failed", "error");
    }
}

// ============================================================
// SETTINGS PANEL
// ============================================================
function openSettings() {
    $("#settings-overlay").classList.remove("hidden");
    requestAnimationFrame(() => {
        $("#settings-panel").classList.remove("translate-x-full");
    });
    // Auto-refresh update status when panel opens
    checkUpdate();
}

function closeSettings() {
    $("#settings-panel").classList.add("translate-x-full");
    setTimeout(() => $("#settings-overlay").classList.add("hidden"), 200);
}

// ============================================================
// PASSWORD CHANGE
// ============================================================
async function changePassword(e) {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const current = fd.get("current_password");
    const next = fd.get("new_password");
    const confirm = fd.get("confirm_password");

    const errEl = $("#pw-error");
    errEl.classList.add("hidden");

    if (next !== confirm) {
        errEl.textContent = "New password and confirmation do not match.";
        errEl.classList.remove("hidden");
        return;
    }

    const r = await fetch("/api/settings/password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: current, new_password: next }),
    });

    if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        errEl.textContent = err.detail || "Failed to update password.";
        errEl.classList.remove("hidden");
        return;
    }

    form.reset();
    toast("Password updated.", "success");
    $("#pw-warning").classList.add("hidden");
}

async function checkDefaultPassword() {
    try {
        const r = await fetch("/api/settings/me");
        if (!r.ok) return;
        const data = await r.json();
        if (data.using_default_password) {
            $("#pw-warning").classList.remove("hidden");
        }
    } catch (e) { /* non-critical */ }
}

// ============================================================
// UPDATE SYSTEM
// ============================================================
async function checkUpdate() {
    const status = $("#settings-update-status");
    status.textContent = "Checking GitHub…";

    const r = await fetch("/api/update/status");
    if (!r.ok) {
        status.textContent = "Failed to check.";
        return;
    }
    const data = await r.json();

    $("#local-version").textContent = data.local_version;
    $("#settings-local-version").textContent = data.local_version;

    const remoteEl = $("#settings-remote-version");
    const runBtn = $("#btn-run-update");
    const pill = $("#btn-update-pill");

    if (data.remote_version) {
        remoteEl.innerHTML = `<span class="${data.update_available ? 'text-cyan-300 font-bold' : 'text-slate-100'}">v${data.remote_version}</span>`;
    } else {
        remoteEl.innerHTML = '<span class="text-slate-500">unreachable</span>';
    }

    if (data.update_available) {
        status.innerHTML = `<span class="text-cyan-300">Update available: v${data.local_version} → v${data.remote_version}</span>`;
        runBtn.classList.remove("hidden");
        $("#pill-remote").textContent = data.remote_version;
        pill.classList.remove("hidden");
    } else if (data.remote_version) {
        status.innerHTML = `<span class="text-green-400">You're on the latest version.</span>`;
        runBtn.classList.add("hidden");
        pill.classList.add("hidden");
    } else {
        status.textContent = "Could not reach GitHub.";
        runBtn.classList.add("hidden");
        pill.classList.add("hidden");
    }
}

async function runUpdate() {
    if (!confirm("Pull latest from GitHub and restart the service? You'll be temporarily disconnected.")) return;

    const btn = $("#btn-run-update");
    btn.disabled = true;
    btn.textContent = "Updating…";

    const log = $("#update-log");
    log.classList.remove("hidden");
    log.textContent = "→ Triggering update.sh\n";

    try {
        const r = await fetch("/api/update/run", { method: "POST" });
        const data = await r.json();
        log.textContent += `→ ${data.message}\n`;

        if (data.ok) {
            log.textContent += "→ Service will restart shortly. Waiting…\n";
            await waitForRestart(log);
            log.textContent += "→ Service is back online. Reloading…\n";
            setTimeout(() => location.reload(), 1500);
        } else {
            btn.disabled = false;
            btn.textContent = "Retry update";
        }
    } catch (e) {
        log.textContent += `→ Connection lost (expected during restart). Waiting for service…\n`;
        await waitForRestart(log);
        log.textContent += "→ Service is back online. Reloading…\n";
        setTimeout(() => location.reload(), 1500);
    }
}

async function waitForRestart(log) {
    for (let i = 0; i < 45; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        try {
            const r = await fetch("/healthz", { cache: "no-store" });
            if (r.ok) return true;
        } catch (e) { /* service down, keep trying */ }
        if (i % 3 === 0) log.textContent += `  (still waiting, ${(i + 1) * 2}s)\n`;
    }
    log.textContent += "→ Timeout - check `journalctl -u ar-reverse-proxy`\n";
    return false;
}

// ============================================================
// BOOT
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
    // Proxies
    $("#proxy-form").addEventListener("submit", createProxy);

    // Settings panel
    $("#btn-settings").addEventListener("click", openSettings);
    $("#btn-close-settings").addEventListener("click", closeSettings);
    $("#settings-overlay").addEventListener("click", closeSettings);
    $("#btn-update-pill").addEventListener("click", openSettings);
    const warnBtn = $("#btn-open-settings-from-warning");
    if (warnBtn) warnBtn.addEventListener("click", openSettings);

    // Settings actions
    $("#pw-form").addEventListener("submit", changePassword);
    $("#btn-check-update").addEventListener("click", checkUpdate);
    $("#btn-run-update").addEventListener("click", runUpdate);

    // Initial loads
    loadProxies();
    checkUpdate();
    checkDefaultPassword();
});
