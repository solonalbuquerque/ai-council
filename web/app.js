/* ============ Conselho de IAs — frontend ============ */
const COLORS = {
  claude: "#d98a63", gpt: "#19c39c", gemini: "#5b8def",
  deepseek: "#9d7bf0", synth: "#e0b25a", human: "#46c6d8",
};
const LABELS = { claude: "Claude", gpt: "ChatGPT", gemini: "Gemini", deepseek: "DeepSeek", synth: "Síntese", human: "Humano" };

const state = {
  catalog: null,
  available: [],
  toolsAvail: {},
  cid: null,
  ws: null,
  participants: [],   // da conversa aberta
  seenMsgIds: new Set(),
  scoreboard: {},
  status: "idle",
};

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const fmt = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
const nf = (n) => (n || 0).toLocaleString("pt-BR");
const money = (n) => "$" + (n || 0).toFixed(4);

/* ---------------- API ---------------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* ---------------- init ---------------- */
async function init() {
  try {
    const cat = await api("/api/catalog");
    state.catalog = cat.catalog;
    state.available = cat.available || [];
    state.toolsAvail = cat.tools || {};
  } catch (e) {
    state.catalog = {}; state.available = [];
  }
  buildParticipantRows();
  await loadConversations();
  wireUI();
}

function wireUI() {
  $("new-btn").onclick = openModal;
  $("modal-cancel").onclick = closeModal;
  $("modal-bg").onclick = (e) => { if (e.target === $("modal-bg")) closeModal(); };
  $("modal-create").onclick = createConversation;
  $("btn-start").onclick = () => send({ action: "start" });
  $("btn-stop").onclick = () => send({ action: "stop" });
  $("btn-pause").onclick = () => {
    if (state.status === "paused") send({ action: "resume" });
    else send({ action: "pause" });
  };
  $("human-send").onclick = sendHuman;
  $("human-text").addEventListener("keydown", (e) => { if (e.key === "Enter") sendHuman(); });
}

/* ---------------- sidebar ---------------- */
async function loadConversations() {
  let list = [];
  try { list = await api("/api/conversations"); } catch (e) {}
  const box = $("conv-list"); box.innerHTML = "";
  if (!list.length) { box.appendChild(el("div", "note", "Nenhuma conversa ainda.")); return; }
  for (const c of list) {
    const item = el("div", "conv-item" + (c.id === state.cid ? " active" : ""));
    item.appendChild(el("div", "t", esc(c.title)));
    item.appendChild(el("div", "g", esc(c.goal || "sem objetivo")));
    item.appendChild(el("div", "s", esc(c.status)));
    item.onclick = () => openConversation(c.id);
    box.appendChild(item);
  }
}

/* ---------------- open conversation ---------------- */
async function openConversation(cid) {
  state.cid = cid;
  state.seenMsgIds = new Set();
  $("placeholder").style.display = "none";
  $("conv-view").style.display = "flex";
  await loadConversations();
  connectWS(cid);
}

function connectWS(cid) {
  if (state.ws) { try { state.ws.close(); } catch (e) {} }
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${cid}`);
  state.ws = ws;
  $("conn").innerHTML = "●&nbsp; conectando";
  ws.onopen = () => { $("conn").innerHTML = "<b style='color:#19c39c'>●</b>&nbsp; conectado"; };
  ws.onclose = () => { $("conn").innerHTML = "●&nbsp; desconectado"; };
  ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
}

function send(obj) {
  if (state.ws && state.ws.readyState === 1) state.ws.send(JSON.stringify(obj));
}
function sendHuman() {
  const inp = $("human-text"); const text = inp.value.trim();
  if (!text) return;
  send({ action: "human", text });
  inp.value = "";
}

/* ---------------- event router ---------------- */
function handleEvent(msg) {
  const p = msg.payload || {};
  switch (msg.type) {
    case "snapshot": renderSnapshot(p); break;
    case "status": setStatus(p.state); break;
    case "round": updateBadge("round", `Rodada <b>${p.round}/${p.total}</b>`); break;
    case "turn_start": break;
    case "message": appendMessage(p); break;
    case "agent_step": agentStep(p); break;
    case "scoreboard": state.scoreboard = p; renderScoreboard(); break;
    case "log": logLine(p.level, p.message); break;
    case "error": logLine("error", p.message); setStatus("error"); break;
  }
}

/* ---------------- render snapshot ---------------- */
function renderSnapshot(c) {
  state.participants = c.participants || [];
  state.scoreboard = c.scoreboard || {};
  $("cv-title").textContent = c.title || "—";
  const g = $("cv-goal"); g.textContent = c.goal || ""; g.title = c.goal || "";

  // badges
  const b = $("cv-badges"); b.innerHTML = "";
  const mode = c.mode === "parallel" ? "Paralelo" : "Sequencial";
  b.appendChild(el("span", "badge", `Modo <b>${mode}</b>`));
  b.appendChild(el("span", "badge", `<span id="bdg-round">Rodada <b>0/${c.max_rounds}</b></span>`));
  b.appendChild(el("span", "badge", `Orçamento <b>${c.token_budget ? nf(c.token_budget) : "∞"}</b>`));
  const tl = [];
  if (c.config?.web) tl.push("web");
  if (c.config?.apify) tl.push("apify");
  if (c.config?.mcp) tl.push("mcp");
  b.appendChild(el("span", "badge", `Ferramentas <b>${tl.join(", ") || "—"}</b>`));

  buildPanes();
  renderScoreboard();

  // transcript
  const t = $("transcript"); t.innerHTML = "";
  const msgs = c.messages || [];
  if (!msgs.length) t.appendChild(el("div", "t-empty", "A transcrição aparece aqui conforme as IAs falam."));
  else for (const m of msgs) appendMessage(m, true);

  setStatus(c.status);
}

/* ---------------- panes / terminals ---------------- */
function buildPanes() {
  const box = $("panes"); box.innerHTML = "";
  const active = state.participants.filter((p) => p.active);
  for (const p of active) box.appendChild(makePane(p.pkey, p.label, p.model));
  box.appendChild(makePane("synth", "Síntese", ""));
  // system log pane
  const sys = el("div", "term system");
  sys.id = "term-system";
  sys.appendChild(el("div", "th", `<span class="dot"></span><span class="nm">Log do sistema</span><span class="st" id="st-system"></span>`));
  sys.appendChild(el("div", "tl", "")).id = "tl-system";
  box.appendChild(sys);
}
function makePane(key, label, model) {
  const c = COLORS[key] || "#888";
  const t = el("div", "term");
  t.id = "term-" + key;
  t.style.setProperty("--accent", c);
  t.appendChild(el("div", "th",
    `<span class="dot"></span><span class="nm">${esc(label)}</span>` +
    (model ? `<span class="st" style="text-transform:none;color:#5d6478">${esc(model)}</span>` : "") +
    `<span class="st" id="st-${key}">aguardando</span>`));
  const tl = el("div", "tl"); tl.id = "tl-" + key;
  t.appendChild(tl);
  return t;
}
function termLine(key, cls, html) {
  const tl = $("tl-" + key);
  if (!tl) return;
  const ln = el("div", "ln " + (cls || ""), html);
  tl.appendChild(ln);
  tl.scrollTop = tl.scrollHeight;
}
function setTermStatus(key, state_) {
  const st = $("st-" + key);
  if (!st) return;
  st.className = "st " + state_;
  st.textContent = { thinking: "pensando…", done: "pronto", error: "erro" }[state_] || state_;
}

function agentStep(p) {
  const key = p.participant;
  if (!$("term-" + key)) {
    // pane criado sob demanda (ex.: síntese)
    $("panes").insertBefore(makePane(key, LABELS[key] || key, ""), $("term-system"));
  }
  if (p.kind === "status") {
    setTermStatus(key, p.state);
    if (p.state === "thinking") termLine(key, "", `<span class="pfx">▶</span> iniciando turno${p.round ? " (rodada " + p.round + ")" : ""}`);
  } else if (p.kind === "tool_call") {
    const args = JSON.stringify(p.args || {});
    termLine(key, "tool", `<span class="pfx">🔧</span> ${esc(p.tool)}(${esc(args.slice(0, 160))})`);
  } else if (p.kind === "tool_result") {
    termLine(key, "res", `<span class="pfx">↳</span> ${esc((p.preview || "").slice(0, 200))}`);
  }
}

function logLine(level, message) {
  const tl = $("tl-system");
  if (!tl) return;
  const cls = level === "error" ? "error" : level === "warn" ? "warn" : "";
  const ln = el("div", "ln " + cls, `<span class="pfx">[${esc(level || "info")}]</span> ${esc(message)}`);
  tl.appendChild(ln);
  tl.scrollTop = tl.scrollHeight;
}

/* ---------------- transcript ---------------- */
function appendMessage(m, fromSnapshot) {
  if (m.id && state.seenMsgIds.has(m.id)) return;
  if (m.id) state.seenMsgIds.add(m.id);
  const t = $("transcript");
  const empty = t.querySelector(".t-empty"); if (empty) empty.remove();

  const role = m.role;
  const key = m.speaker_key;
  const cls = role === "synthesis" ? "synth" : role === "human" ? "human" : "";
  const card = el("div", "msg " + cls);
  card.style.setProperty("--accent", COLORS[key] || "#888");
  const time = m.created_at ? new Date(m.created_at).toLocaleTimeString("pt-BR") : "";
  const model = m.meta?.model ? " · " + esc(m.meta.model) : "";
  card.appendChild(el("div", "mh",
    `<span class="tag">${esc(m.speaker_label)}</span><span class="meta">${m.round ? "rodada " + m.round + " · " : ""}${time}${model}</span>`));
  card.appendChild(el("div", "mb", fmt(m.content)));
  t.appendChild(card);
  if (!fromSnapshot) t.scrollTop = t.scrollHeight;
}

/* ---------------- scoreboard ---------------- */
function renderScoreboard() {
  const box = $("scoreboard"); box.innerHTML = "";
  const active = state.participants.filter((p) => p.active);
  let tin = 0, tout = 0, tcost = 0, ttools = 0, tturns = 0;
  for (const p of active) {
    const s = state.scoreboard[p.pkey] || {};
    tin += s.input_tokens || 0; tout += s.output_tokens || 0; tcost += s.cost_usd || 0;
    ttools += s.tool_calls || 0; tturns += s.turns || 0;
    box.appendChild(scoreCard(p.pkey, p.label, p.model, s));
  }
  // síntese, se houver gasto
  if (state.scoreboard.synth) {
    box.appendChild(scoreCard("synth", "Síntese", "", state.scoreboard.synth));
    const s = state.scoreboard.synth;
    tin += s.input_tokens || 0; tout += s.output_tokens || 0; tcost += s.cost_usd || 0; ttools += s.tool_calls || 0;
  }
  const total = el("div", "score total");
  total.appendChild(el("div", "h", `<span class="nm">TOTAL</span>`));
  total.appendChild(el("div", "grid",
    `<div>entrada <b>${nf(tin)}</b></div><div>saída <b>${nf(tout)}</b></div>` +
    `<div>gasto <b>${money(tcost)}</b></div><div>ferram. <b>${nf(ttools)}</b></div>`));
  box.appendChild(total);
}
function scoreCard(key, label, model, s) {
  const c = el("div", "score");
  c.style.setProperty("--accent", COLORS[key] || "#888");
  c.appendChild(el("div", "h",
    `<span class="dot"></span><span class="nm">${esc(label)}</span><span class="md">${esc(model || "")}</span>`));
  c.appendChild(el("div", "grid",
    `<div>entrada <b>${nf(s.input_tokens)}</b></div><div>saída <b>${nf(s.output_tokens)}</b></div>` +
    `<div>gasto <b>${money(s.cost_usd)}</b></div><div>prontos <b>${nf(s.turns)}</b></div>` +
    `<div>ferram. <b>${nf(s.tool_calls)}</b></div>`));
  return c;
}

/* ---------------- status / transport ---------------- */
function setStatus(stateStr) {
  state.status = stateStr;
  $("led").className = "led " + stateStr;
  const txt = { running: "rodando", paused: "pausado", done: "concluído", stopped: "parado", error: "erro", idle: "ocioso" }[stateStr] || stateStr;
  $("status-txt").textContent = txt;

  const running = stateStr === "running";
  const paused = stateStr === "paused";
  $("btn-start").disabled = running || paused;
  $("btn-pause").disabled = !(running || paused);
  $("btn-pause").innerHTML = paused ? "▶ Retomar" : "⏸ Pausar";
  $("btn-stop").disabled = !(running || paused);
}
function updateBadge(which, html) {
  if (which === "round") { const b = $("bdg-round"); if (b) b.innerHTML = html; }
}

/* ---------------- modal ---------------- */
function buildParticipantRows() {
  const box = $("participants"); box.innerHTML = "";
  const cat = state.catalog || {};
  const avail = state.available;
  if (!avail.length) { $("no-keys").style.display = "block"; }
  // ordem padrão
  const order = ["claude", "gpt", "gemini", "deepseek"];
  for (const key of order) {
    if (!cat[key]) continue;
    const isAvail = avail.includes(key);
    const info = cat[key];
    const card = el("div", "pcard" + (isAvail ? "" : " off"));
    card.style.setProperty("--accent", COLORS[key] || "#888");
    const models = (info.models || []).map((m) => `<option value="${esc(m)}">${esc(m)}</option>`).join("");
    card.innerHTML =
      `<div class="ph"><span class="dot"></span><span class="nm">${esc(info.label)}</span>` +
      `<label class="chk" style="margin-left:auto"><input type="checkbox" class="p-active" data-key="${key}" ${isAvail ? "checked" : ""} ${isAvail ? "" : "disabled"} /> ativa</label></div>` +
      (isAvail ? "" : `<div class="note">Indisponível — <a href="/settings" style="color:var(--gemini)">configure o CLI</a> ou defina chave no .env.</div>`) +
      `<div class="pgrid">` +
      `<div><label class="note">Modelo</label><select class="p-model" data-key="${key}">${models}<option value="__custom__">customizado…</option></select>` +
      `<input type="text" class="p-model-custom" data-key="${key}" placeholder="modelo customizado" style="display:none;margin-top:6px" /></div>` +
      `<div><label class="note">Interação</label><div><label class="chk"><input type="checkbox" class="p-interact" data-key="${key}" checked /> pode perguntar / trocar ideias</label></div></div>` +
      `<div class="full"><label class="note">Persona (opcional)</label><input type="text" class="p-persona" data-key="${key}" placeholder="Ex.: cético, focado em riscos" /></div>` +
      `</div>`;
    box.appendChild(card);
  }
  // toggle custom model input
  box.querySelectorAll(".p-model").forEach((sel) => {
    sel.addEventListener("change", () => {
      const custom = box.querySelector(`.p-model-custom[data-key="${sel.dataset.key}"]`);
      custom.style.display = sel.value === "__custom__" ? "block" : "none";
    });
  });
}

function openModal() { $("modal-bg").classList.add("open"); }
function closeModal() { $("modal-bg").classList.remove("open"); }

async function createConversation() {
  const order = ["claude", "gpt", "gemini", "deepseek"];
  const participants = [];
  for (const key of order) {
    const active = document.querySelector(`.p-active[data-key="${key}"]`);
    if (!active || !active.checked) continue;
    const sel = document.querySelector(`.p-model[data-key="${key}"]`);
    let model = sel ? sel.value : "";
    if (model === "__custom__") model = document.querySelector(`.p-model-custom[data-key="${key}"]`).value.trim();
    if (!model) continue;
    participants.push({
      pkey: key,
      label: LABELS[key] || key,
      model,
      active: true,
      can_interact: document.querySelector(`.p-interact[data-key="${key}"]`).checked,
      persona: document.querySelector(`.p-persona[data-key="${key}"]`).value.trim(),
    });
  }
  if (!participants.length) { alert("Selecione ao menos uma IA com modelo definido."); return; }

  const payload = {
    title: $("f-title").value.trim() || "Nova conversa",
    goal: $("f-goal").value.trim(),
    mode: $("f-sequential").checked ? "sequential" : "parallel",
    max_rounds: parseInt($("f-rounds").value) || 3,
    token_budget: parseInt($("f-budget").value) || 0,
    config: {
      web: $("f-web").checked,
      apify: $("f-apify").checked,
      mcp: $("f-mcp").checked,
      synthesize: $("f-synth").checked,
    },
    participants,
  };
  try {
    const { id } = await api("/api/conversations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    closeModal();
    await openConversation(id);
  } catch (e) {
    alert("Erro ao criar conversa: " + e.message);
  }
}

init();
