/* ============ Settings — CLI config ============ */
const COLORS = {
  claude: "#d98a63", gpt: "#19c39c", gemini: "#5b8def", antigravity: "#f2c94c", deepseek: "#9d7bf0",
};
const STATUS_LABEL = {
  ok: "OK", auth: "Needs auth", missing: "Not installed",
  installed: "Installed", error: "Error",
};
const STATUS_CLS = {
  ok: "ok", auth: "warn", missing: "bad", installed: "idle", error: "bad",
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

async function api(path, opts) {
  const r = await fetch(path, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.message || data.detail || "HTTP " + r.status);
  return data;
}

let state = { providers: [], config: {}, runtime_mode: "local", lastTests: {} };

function testResultHtml(r) {
  if (r.ok) {
    return `<span class="k">Response</span><div class="txt">${esc(r.response)}</div>` +
      (r.at ? `<div class="ts">Tested ${new Date(r.at).toLocaleTimeString("en-US")}</div>` : "");
  }
  return `<span class="k">Failed</span><div class="txt">${esc(r.message)}</div>` +
    (r.raw ? `<pre class="raw">${esc(r.raw)}</pre>` : "") +
    (r.at ? `<div class="ts">Tested ${new Date(r.at).toLocaleTimeString("en-US")}</div>` : "");
}

function setLoginBtnVisible(pkey, visible) {
  const btn = document.querySelector(`[data-act="login"][data-key="${pkey}"]`);
  if (btn) btn.style.display = visible ? "" : "none";
  const row = $(`token-row-${pkey}`);
  if (row && visible) row.style.display = "block";
}

function tokenRowHtml(p, show) {
  const placeholder = p.token_hint || "Paste token here and click Save";
  const savedNote = p.has_token ? '<span class="token-saved">Token saved</span>' : "";
  return `<div class="cli-token" id="token-row-${p.pkey}" style="display:${show || p.has_token ? "block" : "none"}">
      <label class="k">Authentication token ${savedNote}</label>
      <div class="token-input-row">
        <input type="password" class="token-input" id="token-${p.pkey}" placeholder="${esc(placeholder)}" autocomplete="off" />
        <button class="btn" data-act="save-token" data-key="${p.pkey}">Save</button>
      </div>
    </div>`;
}

function applyTestToCard(pkey, r) {
  const respBox = $(`resp-${pkey}`);
  if (!respBox) return;
  respBox.style.display = "block";
  respBox.className = "cli-response " + (r.ok ? "ok" : "bad");
  respBox.innerHTML = testResultHtml(r);
  const card = respBox.closest(".cli-card");
  if (!card) return;
  const pill = card.querySelector(".pill");
  const st = r.ok ? "ok" : (r.status || "error");
  if (pill) {
    pill.className = "pill " + (STATUS_CLS[st] || "bad");
    pill.textContent = STATUS_LABEL[st] || st;
  }
  const msg = card.querySelector(".cli-msg");
  if (msg) {
    msg.className = "cli-msg " + (STATUS_CLS[st] || "bad");
    msg.textContent = r.message || "";
  }
  setLoginBtnVisible(pkey, st === "auth");
}

async function load() {
  const data = await api("/api/cli/status");
  state.providers = data.providers || [];
  state.config = data.config || {};
  state.runtime_mode = data.runtime_mode || "local";
  $("prefer-cli").checked = state.config.prefer_cli !== false;

  const warn = $("docker-warn");
  if (state.runtime_mode === "docker") {
    warn.style.display = "block";
    warn.className = "warnbox";
    warn.innerHTML =
      "Running inside <b>Docker</b>: the container cannot see CLIs installed on your computer. " +
      "To use claude, codex, gemini, and deepseek from your machine, stop the Docker app and run " +
      "<code>npm run dev</code> (local app + Postgres in Docker).";
  } else {
    warn.style.display = "block";
    warn.className = "warnbox okbox";
    warn.innerHTML =
      "<b>Local</b> mode — detecting CLIs installed on this machine. " +
      "Use <b>Test</b> and, if needed, <b>Log in</b> (opens a terminal on your system).";
  }
  renderCards();
}

function renderCards() {
  const box = $("cli-cards");
  box.innerHTML = "";
  for (const p of state.providers) {
    box.appendChild(makeCard(p));
  }
}

function makeCard(p) {
  const c = COLORS[p.pkey] || "#888";
  const card = el("div", "cli-card");
  card.style.setProperty("--accent", c);
  const inDocker = state.runtime_mode === "docker";

  const st = p.status || (p.installed ? "installed" : "missing");
  const stLabel = STATUS_LABEL[st] || st;
  const stCls = STATUS_CLS[st] || "idle";
  const showLogin = st === "auth" || (state.lastTests[p.pkey] && state.lastTests[p.pkey].status === "auth");

  const installLabel = inDocker ? "Install (in container)" : "Install";
  const installTitle = inDocker
    ? "Installs inside the Docker container — prefer npm run dev to use host CLIs"
    : "Installs the CLI globally via npm on this machine";

  card.innerHTML =
    `<div class="cli-head">
      <span class="dot"></span>
      <span class="nm">${esc(p.label)}</span>
      <span class="pill ${stCls}">${esc(stLabel)}</span>
    </div>
    <div class="cli-meta">
      <div><span class="k">Command</span> <code>${esc(p.path || p.command || "—")}</code></div>
      <div><span class="k">Version</span> ${esc(p.version || "—")}</div>
    </div>
    <div class="cli-msg ${stCls}">${esc(p.message || "")}</div>
    <div class="cli-auth note">${esc(p.auth_help || "")}</div>
    <div class="cli-install note">Install: <code>${esc(p.install || "")}</code></div>
    <div class="cli-response" id="resp-${p.pkey}" style="display:${state.lastTests[p.pkey] ? "block" : "none"}"></div>
    ${p.supports_token ? tokenRowHtml(p, true) : ""}
    <div class="cli-actions">
      <button class="btn" data-act="install" data-key="${p.pkey}" title="${esc(installTitle)}">${esc(installLabel)}</button>
      <button class="btn" data-act="login" data-key="${p.pkey}" style="display:${showLogin ? "" : "none"}">Log in</button>
      <button class="btn primary" data-act="test" data-key="${p.pkey}">Test</button>
    </div>`;

  card.querySelector('[data-act="install"]').onclick = () => installCli(p.pkey);
  card.querySelector('[data-act="test"]').onclick = () => testCli(p.pkey);
  card.querySelector('[data-act="login"]').onclick = () => loginCli(p.pkey);
  if (p.supports_token) {
    card.querySelector('[data-act="save-token"]').onclick = () => saveToken(p.pkey);
  }
  if (state.lastTests[p.pkey]) applyTestToCard(p.pkey, state.lastTests[p.pkey]);
  return card;
}

async function testCli(pkey) {
  const btn = document.querySelector(`[data-act="test"][data-key="${pkey}"]`);
  const respBox = $(`resp-${pkey}`);
  btn.disabled = true;
  btn.textContent = "Testing…";
  respBox.style.display = "block";
  respBox.className = "cli-response loading";
  respBox.innerHTML =
    `<span class="k">Waiting</span>` +
    `<div class="txt">Sending <strong>HI</strong> to CLI… may take up to 1 minute.</div>` +
    `<div class="spinner"></div>`;

  try {
    const r = await api(`/api/cli/test/${pkey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "HI" }),
    });
    const saved = { ...r, at: Date.now() };
    state.lastTests[pkey] = saved;
    applyTestToCard(pkey, saved);
  } catch (e) {
    const saved = { ok: false, status: "error", message: e.message, at: Date.now() };
    state.lastTests[pkey] = saved;
    applyTestToCard(pkey, saved);
  } finally {
    btn.disabled = false;
    btn.textContent = "Test";
  }
}

async function loginCli(pkey) {
  const btn = document.querySelector(`[data-act="login"][data-key="${pkey}"]`);
  const respBox = $(`resp-${pkey}`);
  btn.disabled = true;
  btn.textContent = "Opening…";

  try {
    const r = await api(`/api/cli/login/${pkey}`, { method: "POST" });
    respBox.style.display = "block";
    respBox.className = "cli-response " + (r.ok ? "ok" : "bad");
    let html = `<span class="k">${r.ok ? "Terminal" : "Manual login"}</span>`;
    html += `<div class="txt">${esc(r.message)}</div>`;
    if (r.command) {
      html += `<div class="note" style="margin-top:8px">Command: <code>${esc(r.command)}</code></div>`;
    }
    const prov = state.providers.find((p) => p.pkey === pkey);
    if (r.ok && prov && prov.supports_token) {
      const what = pkey === "claude" ? "the token <code>sk-ant-oat01-…</code>" : "the generated key";
      html += `<div class="note" style="margin-top:8px">Copy ${what} from the terminal, paste below, and click Save.</div>`;
      const row = $(`token-row-${pkey}`);
      if (row) row.style.display = "block";
    }
    respBox.innerHTML = html;
  } catch (e) {
    respBox.style.display = "block";
    respBox.className = "cli-response bad";
    respBox.innerHTML = `<span class="k">Error</span><div class="txt">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Log in";
  }
}

async function saveToken(pkey) {
  const input = $(`token-${pkey}`);
  const btn = document.querySelector(`[data-act="save-token"][data-key="${pkey}"]`);
  const token = (input.value || "").trim();
  btn.disabled = true;
  btn.textContent = "Saving…";
  try {
    const r = await api(`/api/cli/token/${pkey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    input.value = "";
    const respBox = $(`resp-${pkey}`);
    respBox.style.display = "block";
    respBox.className = "cli-response ok";
    respBox.innerHTML = `<span class="k">Token</span><div class="txt">${esc(r.message)}</div>`;
    if (r.ok && token) await testCli(pkey);
  } catch (e) {
    const respBox = $(`resp-${pkey}`);
    respBox.style.display = "block";
    respBox.className = "cli-response bad";
    respBox.innerHTML = `<span class="k">Error</span><div class="txt">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Save";
  }
}

async function installCli(pkey) {
  if (state.runtime_mode === "docker") {
    if (!confirm(
      "This installs the CLI INSIDE the Docker container, not on your machine.\n\n" +
      "To use CLIs from your computer, stop the Docker app and run: npm run dev\n\n" +
      "Continue anyway?"
    )) return;
  } else if (!confirm("Install/update the CLI via npm? This may take a few minutes.")) {
    return;
  }
  const btn = document.querySelector(`[data-act="install"][data-key="${pkey}"]`);
  btn.disabled = true;
  btn.textContent = "Installing…";
  try {
    const r = await api(`/api/cli/install/${pkey}`, { method: "POST" });
    alert(r.ok ? "Installation complete." : ("Failed: " + r.message));
    await load();
  } catch (e) {
    alert("Error: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = state.runtime_mode === "docker" ? "Install (in container)" : "Install";
  }
}

async function savePreferCli() {
  await api("/api/cli/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prefer_cli: $("prefer-cli").checked }),
  });
}

$("btn-refresh").onclick = load;
$("prefer-cli").onchange = savePreferCli;

load().catch((e) => {
  $("cli-cards").innerHTML = `<div class="warnbox">Error loading: ${esc(e.message)}</div>`;
});
