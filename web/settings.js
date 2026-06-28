/* ============ Settings — CLI config ============ */
const COLORS = {
  claude: "#d98a63", gpt: "#19c39c", gemini: "#5b8def", deepseek: "#9d7bf0",
};
const STATUS_LABEL = {
  ok: "OK", auth: "Precisa autenticar", missing: "Não instalado",
  installed: "Instalado", error: "Erro",
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

let state = { providers: [], config: {}, runtime_mode: "local" };

async function load() {
  const data = await api("/api/cli/status");
  state.providers = data.providers || [];
  state.config = data.config || {};
  state.runtime_mode = data.runtime_mode || "local";
  $("prefer-cli").checked = state.config.prefer_cli !== false;

  const warn = $("docker-warn");
  if (state.runtime_mode === "docker") {
    warn.style.display = "block";
    warn.innerHTML =
      "Rodando dentro do <b>Docker</b>: o container não enxerga os CLIs instalados no seu computador. " +
      "Para usar claude, codex, gemini e deepseek da sua máquina, pare o Docker do app e rode " +
      "<code>npm run dev</code> (app local + Postgres no Docker).";
  } else {
    warn.style.display = "block";
    warn.className = "warnbox okbox";
    warn.innerHTML =
      "Modo <b>local</b> — detectando CLIs instalados nesta máquina. " +
      "Autentique no terminal e use <b>Testar OI</b> abaixo.";
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

  const installLabel = inDocker ? "Instalar (no container)" : "Instalar";
  const installTitle = inDocker
    ? "Instala dentro do container Docker — prefira npm run dev para usar CLIs do host"
    : "Instala o CLI globalmente via npm nesta máquina";

  card.innerHTML =
    `<div class="cli-head">
      <span class="dot"></span>
      <span class="nm">${esc(p.label)}</span>
      <span class="pill ${stCls}">${esc(stLabel)}</span>
    </div>
    <div class="cli-meta">
      <div><span class="k">Comando</span> <code>${esc(p.path || p.command || "—")}</code></div>
      <div><span class="k">Versão</span> ${esc(p.version || "—")}</div>
    </div>
    <div class="cli-msg ${stCls}">${esc(p.message || "")}</div>
    <div class="cli-auth note">${esc(p.auth_help || "")}</div>
    <div class="cli-install note">Instalar: <code>${esc(p.install || "")}</code></div>
    <div class="cli-response" id="resp-${p.pkey}" style="display:none"></div>
    <div class="cli-actions">
      <button class="btn" data-act="install" data-key="${p.pkey}" title="${esc(installTitle)}">${esc(installLabel)}</button>
      <button class="btn primary" data-act="test" data-key="${p.pkey}">Testar OI</button>
    </div>`;

  const installBtn = card.querySelector('[data-act="install"]');
  installBtn.onclick = () => installCli(p.pkey);
  card.querySelector('[data-act="test"]').onclick = () => testCli(p.pkey);
  return card;
}

async function testCli(pkey) {
  const btn = document.querySelector(`[data-act="test"][data-key="${pkey}"]`);
  const respBox = $(`resp-${pkey}`);
  btn.disabled = true;
  btn.textContent = "Testando…";
  respBox.style.display = "none";

  try {
    const r = await api(`/api/cli/test/${pkey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "OI" }),
    });
    respBox.style.display = "block";
    if (r.ok) {
      respBox.className = "cli-response ok";
      respBox.innerHTML = `<span class="k">Resposta</span><div class="txt">${esc(r.response)}</div>`;
    } else {
      respBox.className = "cli-response bad";
      respBox.innerHTML = `<span class="k">Falha</span><div class="txt">${esc(r.message)}</div>` +
        (r.raw ? `<pre class="raw">${esc(r.raw)}</pre>` : "");
    }
    await load();
  } catch (e) {
    respBox.style.display = "block";
    respBox.className = "cli-response bad";
    respBox.innerHTML = esc(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Testar OI";
  }
}

async function installCli(pkey) {
  if (state.runtime_mode === "docker") {
    if (!confirm(
      "Isso instala o CLI DENTRO do container Docker, não na sua máquina.\n\n" +
      "Para usar os CLIs do seu computador, pare o app Docker e rode: npm run dev\n\n" +
      "Continuar mesmo assim?"
    )) return;
  } else if (!confirm("Instalar/atualizar o CLI via npm? Pode levar alguns minutos.")) {
    return;
  }
  const btn = document.querySelector(`[data-act="install"][data-key="${pkey}"]`);
  btn.disabled = true;
  btn.textContent = "Instalando…";
  try {
    const r = await api(`/api/cli/install/${pkey}`, { method: "POST" });
    alert(r.ok ? "Instalação concluída." : ("Falha: " + r.message));
    await load();
  } catch (e) {
    alert("Erro: " + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = state.runtime_mode === "docker" ? "Instalar (no container)" : "Instalar";
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
  $("cli-cards").innerHTML = `<div class="warnbox">Erro ao carregar: ${esc(e.message)}</div>`;
});
