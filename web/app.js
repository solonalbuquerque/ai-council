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
  agents: [],
  presets: [],
  cid: null,
  ws: null,
  participants: [],   // da conversa aberta
  seenMsgIds: new Set(),
  scoreboard: {},
  status: "idle",
  urlImport: null,
  trace: [],
  orgModalOpen: false,
  orgRunIndex: 1,
  orgSelectedNode: null,
  orgTree: null,
  orgFlatNodes: [],
  orgView: { panX: 40, panY: 40, zoom: 1, dragging: false, lastX: 0, lastY: 0 },
  orgAnimFrame: null,
  orgPulse: 0,
  messages: [],
  humanFeedback: { text: "", kind: "idle" },
  hasPriorExecution: false,
};

const TRACE_TYPES = new Set([
  "run_start", "round", "turn_start", "agent_step", "log", "status", "message",
]);

const $ = (id) => document.getElementById(id);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const esc = (s) => (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const fmt = (s) => esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
const nf = (n) => (n || 0).toLocaleString("pt-BR");
const money = (n) => "$" + (n || 0).toFixed(4);
const PLACEHOLDER_TITLE = "Uma nova conversa";
const PROVIDER_ORDER = ["claude", "gpt", "gemini", "deepseek"];

function providerColor(key) {
  const base = (key || "").split(":")[0];
  return COLORS[base] || "#888";
}

function providerOptions(selected) {
  const cat = state.catalog || {};
  const avail = state.available || [];
  return PROVIDER_ORDER.filter((k) => cat[k]).map((k) => {
    const dis = avail.includes(k) ? "" : " disabled";
    const sel = k === selected ? " selected" : "";
    return `<option value="${k}"${dis}${sel}>${esc(cat[k].label)}${avail.includes(k) ? "" : " (indisponível)"}</option>`;
  }).join("");
}

function modelOptionsFor(pkey, selectedModel) {
  const base = (pkey || "").split(":")[0];
  const info = (state.catalog || {})[base] || {};
  const models = (info.models || []).map((m) =>
    `<option value="${esc(m)}"${m === selectedModel ? " selected" : ""}>${esc(m)}</option>`
  ).join("");
  return models + `<option value="__custom__"${selectedModel && !(info.models || []).includes(selectedModel) ? " selected" : ""}>customizado…</option>`;
}

function applyTitle(cid, title) {
  if (state.cid === cid) $("cv-title").textContent = title || PLACEHOLDER_TITLE;
  const item = document.querySelector(`.conv-item[data-id="${cid}"] .t`);
  if (item) item.textContent = title || PLACEHOLDER_TITLE;
}

async function generateTitle(cid, goal, participants) {
  try {
    const { title } = await api(`/api/conversations/${cid}/generate-title`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        goal,
        participants: participants.map((p) => ({ pkey: p.pkey, model: p.model })),
      }),
    });
    if (title && title !== PLACEHOLDER_TITLE) applyTitle(cid, title);
  } catch (e) {
    /* mantém placeholder */
  }
}

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
  await loadAgents();
  await loadConversations();
  wireUI();
  window.addEventListener("popstate", onPopState);
  const cid = parseConversationFromUrl();
  if (cid) await openConversation(cid, { skipUrl: true });
}

function conversationUrl(cid) {
  return `/c/${cid}`;
}

function parseConversationFromUrl() {
  const m = location.pathname.match(/^\/c\/([a-f0-9]{32})$/i);
  return m ? m[1] : null;
}

function setConversationUrl(cid, replace = false) {
  const path = cid ? conversationUrl(cid) : "/";
  const st = { cid: cid || null };
  if (replace) history.replaceState(st, "", path);
  else history.pushState(st, "", path);
}

function onPopState(ev) {
  const cid = parseConversationFromUrl() || ev.state?.cid;
  if (cid) openConversation(cid, { skipUrl: true });
  else closeConversationView();
}

function closeConversationView() {
  state.cid = null;
  if (state.ws) { try { state.ws.close(); } catch (e) {} state.ws = null; }
  const cv = $("conv-view");
  const ph = $("placeholder");
  if (cv) cv.style.display = "none";
  if (ph) ph.style.display = "";
  loadConversations();
}

function scrollTranscriptToBottom() {
  const t = $("transcript");
  if (!t) return;
  requestAnimationFrame(() => {
    t.scrollTop = t.scrollHeight;
  });
}

function wireUI() {
  $("new-btn").onclick = openModal;
  $("modal-cancel").onclick = closeModal;
  $("modal-bg").onclick = (e) => { if (e.target === $("modal-bg")) closeModal(); };
  $("modal-create").onclick = createConversation;
  $("agents-btn").onclick = openAgentsModal;
  $("agents-close").onclick = closeAgentsModal;
  $("agents-modal-bg").onclick = (e) => { if (e.target === $("agents-modal-bg")) closeAgentsModal(); };
  $("open-agents-from-conv")?.addEventListener("click", () => { closeModal(); openAgentsModal(); });
  $("agent-url-fetch").onclick = fetchAgentUrl;
  $("agent-url-save").onclick = saveAgentFromUrl;
  $("agent-manual-save").onclick = saveAgentManual;
  document.querySelectorAll("#agents-tabs .tab").forEach((tab) => {
    tab.onclick = () => switchAgentsTab(tab.dataset.tab);
  });
  $("btn-start").onclick = () => send({ action: "start" });
  $("btn-stop").onclick = () => send({ action: "stop" });
  $("btn-pause").onclick = () => {
    if (state.status === "paused") send({ action: "resume" });
    else send({ action: "pause" });
  };
  $("human-send").onclick = sendHuman;
  $("human-text").addEventListener("keydown", (e) => { if (e.key === "Enter") sendHuman(); });
  $("btn-export").onclick = exportConversation;
  $("btn-org").onclick = () => openOrgModal(state.cid);
  $("org-close").onclick = closeOrgModal;
  $("org-modal-bg").onclick = (e) => { if (e.target === $("org-modal-bg")) closeOrgModal(); };
  $("org-run-select").onchange = () => {
    state.orgRunIndex = parseInt($("org-run-select").value) || 1;
    state.orgSelectedNode = null;
    refreshOrgView();
  };
  wireOrgCanvas();
}

function exportConversation() {
  if (!state.cid) { alert("Abra uma conversa primeiro."); return; }
  window.location.href = `/api/conversations/${state.cid}/export`;
}

/* ---------------- sidebar ---------------- */
async function loadConversations() {
  let list = [];
  try { list = await api("/api/conversations"); } catch (e) {}
  const box = $("conv-list"); box.innerHTML = "";
  if (!list.length) { box.appendChild(el("div", "note", "Nenhuma conversa ainda.")); return; }
  for (const c of list) {
    const item = el("div", "conv-item" + (c.id === state.cid ? " active" : ""));
    item.dataset.id = c.id;
    const head = el("div", "conv-head");
    head.appendChild(el("div", "t", esc(c.title)));
    const orgBtn = el("button", "conv-org", "ORG");
    orgBtn.type = "button";
    orgBtn.title = "Organograma de execução";
    orgBtn.onclick = (e) => { e.stopPropagation(); openOrgModal(c.id); };
    head.appendChild(orgBtn);
    item.appendChild(head);
    item.appendChild(el("div", "g", esc(c.goal || "sem objetivo")));
    item.appendChild(el("div", "s", esc(c.status)));
    item.onclick = () => openConversation(c.id);
    box.appendChild(item);
  }
}

/* ---------------- open conversation ---------------- */
async function openConversation(cid, opts = {}) {
  state.cid = cid;
  state.seenMsgIds = new Set();
  $("placeholder").style.display = "none";
  $("conv-view").style.display = "flex";
  if (!opts.skipUrl) setConversationUrl(cid, !!opts.replaceUrl);
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

const HUMAN_COMMANDS = {
  start: { action: "start" },
  stop: { action: "stop" },
};

function parseHumanCommand(text) {
  if (!text.startsWith("/")) return null;
  const name = text.slice(1).trim().split(/\s+/)[0]?.toLowerCase();
  return name || null;
}

function handleHumanCommand(name) {
  if (name === "start") {
    if (state.status === "running") {
      setHumanFeedback("Execução em andamento — use /stop para interromper.", "warn");
      return;
    }
    if (state.status === "paused") {
      setHumanFeedback("Execução pausada — use Retomar ou /stop.", "warn");
      return;
    }
    setHumanFeedback("Iniciando debate…", "processing");
    send({ action: "start" });
    return;
  }
  if (name === "stop") {
    if (state.status !== "running" && state.status !== "paused") {
      setHumanFeedback("Nenhuma execução ativa para parar.", "warn");
      return;
    }
    setHumanFeedback("Parando execução…", "processing");
    send({ action: "stop" });
    return;
  }
  setHumanFeedback("Comando desconhecido. Use /start ou /stop.", "warn");
}

function sendHuman() {
  const inp = $("human-text"); const text = inp.value.trim();
  if (!text) return;
  inp.value = "";
  if (text.startsWith("/")) {
    handleHumanCommand(parseHumanCommand(text));
    return;
  }
  setHumanFeedback("Enviando…", "processing");
  send({ action: "human", text });
}

function setHumanFeedback(text, kind) {
  state.humanFeedback = { text: text || "", kind: kind || "idle" };
  const el = $("human-status");
  if (!el) return;
  el.textContent = text || "";
  el.className = "human-status" + (kind ? " " + kind : "");
}

function updateHumanInputHint() {
  if (state.humanFeedback.kind !== "idle" &&
      !["running", "paused", "done", "stopped", "idle", "error"].includes(state.status)) {
    return;
  }
  const cmdHint = "Comandos: /start (iniciar debate), /stop (parar).";
  let hint = "";
  let kind = "idle";
  if (state.status === "running") {
    hint = cmdHint + " Durante a execução, as IAs lerão sua mensagem no próximo turno.";
    kind = "queued";
  } else if (state.status === "paused") {
    hint = cmdHint + " Execução pausada — mensagem ficará na fila até retomar.";
    kind = "warn";
  } else if (state.hasPriorExecution && (state.status === "done" || state.status === "stopped")) {
    hint = cmdHint + " Após o debate, a Síntese (ou última IA) responde ao humano. Use /start para rodar de novo.";
  } else {
    hint = cmdHint + " Ou escreva uma mensagem para as IAs.";
  }
  setHumanFeedback(hint, kind);
}

function handleHumanAck(p) {
  const kindMap = {
    pending_start: "warn",
    queued: "queued",
    delivered: "done",
    processing: "processing",
    answered: "done",
  };
  setHumanFeedback(p.detail || "", kindMap[p.status] || "idle");
  if (p.status === "delivered" || p.status === "answered") {
    setTimeout(() => {
      state.humanFeedback = { text: "", kind: "idle" };
      updateHumanInputHint();
    }, 4000);
  }
}

function computeHasPriorExecution(c) {
  const msgs = c?.messages || [];
  if (msgs.some((m) => m.role === "participant" || m.role === "synthesis")) return true;
  const trace = c?.trace || [];
  return trace.some((e) => e.type === "run_start");
}

/* ---------------- event router ---------------- */
function handleEvent(msg) {
  const p = msg.payload || {};
  switch (msg.type) {
    case "snapshot": renderSnapshot(p); break;
    case "status": setStatus(p.state); pushTraceEvent("status", p); break;
    case "round": updateBadge("round", `Rodada <b>${p.round}/${p.total}</b>`); pushTraceEvent("round", p); break;
    case "turn_start": pushTraceEvent("turn_start", p); break;
    case "message": appendMessage(p); pushTraceEvent("message", p); break;
    case "agent_step": agentStep(p); pushTraceEvent("agent_step", p); break;
    case "scoreboard": state.scoreboard = p; renderScoreboard(); break;
    case "log": logLine(p.level, p.message); pushTraceEvent("log", p); break;
    case "error": logLine("error", p.message); setStatus("error"); break;
    case "run_start": pushTraceEvent("run_start", p); break;
    case "human_ack": handleHumanAck(p); break;
  }
}

function pushTraceEvent(type, payload) {
  if (!TRACE_TYPES.has(type)) return;
  const seq = payload.seq;
  if (seq && state.trace.some((e) => e.seq === seq)) return;
  const stored = { ...payload };
  delete stored.trace_id;
  delete stored.seq;
  state.trace.push({
    id: payload.trace_id || `local-${Date.now()}-${state.trace.length}`,
    run_index: payload.run_index || state.orgRunIndex || 1,
    seq: seq || state.trace.length + 1,
    type,
    payload: stored,
    created_at: new Date().toISOString(),
  });
  if (state.orgModalOpen) refreshOrgView();
}

/* ---------------- render snapshot ---------------- */
function renderSnapshot(c) {
  state.participants = c.participants || [];
  state.scoreboard = c.scoreboard || {};
  state.trace = c.trace || [];
  state.messages = c.messages || [];
  state.hasPriorExecution = computeHasPriorExecution(c);
  $("cv-title").textContent = c.title || "—";
  const g = $("cv-goal"); g.textContent = c.goal || ""; g.title = c.goal || "";
  renderConvBrief(c.config);

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
  scrollTranscriptToBottom();

  setStatus(c.status);
  state.humanFeedback = { text: "", kind: "idle" };
  updateHumanInputHint();
  if (state.orgModalOpen) refreshOrgView();
}

function renderConvBrief(config) {
  const box = $("conv-brief");
  if (!box) return;
  const stop = (config?.stop_when || "").trim();
  const deliver = (config?.deliverable || "").trim();
  if (!stop && !deliver) {
    box.style.display = "none";
    box.innerHTML = "";
    return;
  }
  box.style.display = "grid";
  box.innerHTML = "";
  if (stop) {
    const item = el("div", "brief-item");
    item.appendChild(el("div", "brief-k", "Encerrar quando"));
    item.appendChild(el("div", "brief-v", esc(stop)));
    box.appendChild(item);
  }
  if (deliver) {
    const item = el("div", "brief-item");
    item.appendChild(el("div", "brief-k", "Produzir ao final"));
    item.appendChild(el("div", "brief-v", esc(deliver)));
    box.appendChild(item);
  }
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
  const c = providerColor(key);
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
  card.style.setProperty("--accent", providerColor(key));
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
  c.style.setProperty("--accent", providerColor(key));
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
  state.humanFeedback = { text: "", kind: "idle" };
  updateHumanInputHint();
}
function updateBadge(which, html) {
  if (which === "round") { const b = $("bdg-round"); if (b) b.innerHTML = html; }
}

/* ---------------- agentes ---------------- */
async function loadAgents() {
  try {
    state.agents = await api("/api/agents");
  } catch (e) {
    state.agents = [];
  }
  try {
    const data = await api("/api/agents/presets");
    state.presets = data.presets || [];
  } catch (e) {
    state.presets = [];
  }
  renderAgentsList();
  renderAgentsPresets();
  buildConvAgentRows();
}

function switchAgentsTab(tab) {
  document.querySelectorAll("#agents-tabs .tab").forEach((t) => {
    t.classList.toggle("active", t.dataset.tab === tab);
  });
  document.querySelectorAll(".agents-add .tab-panel").forEach((p) => {
    p.classList.toggle("active", p.id === "tab-" + tab);
  });
}

function openAgentsModal() {
  loadAgents().then(() => $("agents-modal-bg").classList.add("open"));
}
function closeAgentsModal() { $("agents-modal-bg").classList.remove("open"); }

function renderAgentsList() {
  const box = $("agents-list");
  if (!box) return;
  box.innerHTML = "";
  if (!state.agents.length) {
    box.appendChild(el("div", "note", "Nenhum agente salvo ainda."));
    return;
  }
  for (const a of state.agents) {
    const card = el("div", "agent-card saved");
    const src = a.source === "preset" ? "preset" : a.source === "url" ? "url" : "manual";
    card.innerHTML =
      `<div class="agent-card-head">` +
      `<span class="nm">${esc(a.name)}</span>` +
      `<span class="src">${esc(src)}</span>` +
      `<button type="button" class="btn ghost agent-del" data-id="${esc(a.id)}">Remover</button>` +
      `</div>` +
      `<div class="agent-desc">${esc((a.description || "").slice(0, 220))}${(a.description || "").length > 220 ? "…" : ""}</div>`;
    card.querySelector(".agent-del").onclick = () => deleteAgent(a.id);
    box.appendChild(card);
  }
}

function renderAgentsPresets() {
  const box = $("agents-presets");
  if (!box) return;
  box.innerHTML = "";
  const savedNames = new Set(state.agents.map((a) => a.name));
  for (const p of state.presets) {
    const exists = savedNames.has(p.name);
    const card = el("div", "agent-card preset" + (exists ? " added" : ""));
    card.innerHTML =
      `<div class="agent-card-head"><span class="nm">${esc(p.name)}</span>` +
      `<span class="src">${exists ? "já na biblioteca" : "clique para adicionar"}</span></div>` +
      `<div class="agent-desc">${esc((p.description || "").slice(0, 160))}…</div>`;
    if (!exists) {
      card.onclick = () => addPresetAgent(p);
      card.style.cursor = "pointer";
    }
    box.appendChild(card);
  }
}

async function addPresetAgent(preset) {
  try {
    await api("/api/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: preset.name, description: preset.description, source: "preset" }),
    });
    await loadAgents();
  } catch (e) {
    alert("Erro ao adicionar preset: " + e.message);
  }
}

async function deleteAgent(id) {
  if (!confirm("Remover este agente da biblioteca?")) return;
  try {
    await api(`/api/agents/${id}`, { method: "DELETE" });
    await loadAgents();
  } catch (e) {
    alert("Erro ao remover: " + e.message);
  }
}

async function fetchAgentUrl() {
  const url = $("agent-url").value.trim();
  const msg = $("agent-url-msg");
  msg.textContent = "Buscando…";
  try {
    const data = await api("/api/agents/import-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    if (data.error) throw new Error(data.error);
    state.urlImport = data;
    $("agent-url-name").value = data.name || "";
    $("agent-url-desc").value = data.description || "";
    $("agent-url-preview").style.display = "block";
    msg.textContent = "Conteúdo importado — revise e salve.";
  } catch (e) {
    $("agent-url-preview").style.display = "none";
    msg.textContent = "Erro: " + e.message;
  }
}

async function saveAgentFromUrl() {
  const name = $("agent-url-name").value.trim();
  const description = $("agent-url-desc").value.trim();
  if (!name || !description) { alert("Nome e descrição são obrigatórios."); return; }
  try {
    await api("/api/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name, description, source: "url",
        source_url: state.urlImport?.source_url || $("agent-url").value.trim(),
      }),
    });
    $("agent-url").value = "";
    $("agent-url-preview").style.display = "none";
    $("agent-url-msg").textContent = "Agente salvo.";
    state.urlImport = null;
    await loadAgents();
  } catch (e) {
    alert("Erro ao salvar: " + e.message);
  }
}

async function saveAgentManual() {
  const name = $("agent-manual-name").value.trim();
  const description = $("agent-manual-desc").value.trim();
  if (!name || !description) { alert("Nome e descrição são obrigatórios."); return; }
  try {
    await api("/api/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, description, source: "manual" }),
    });
    $("agent-manual-name").value = "";
    $("agent-manual-desc").value = "";
    await loadAgents();
  } catch (e) {
    alert("Erro ao salvar: " + e.message);
  }
}

function buildConvAgentRows() {
  const box = $("conv-agents");
  const noBox = $("no-agents");
  if (!box) return;
  box.innerHTML = "";
  if (!state.agents.length) {
    if (noBox) noBox.style.display = "block";
    return;
  }
  if (noBox) noBox.style.display = "none";

  const defaultPkey = (state.available || [])[0] || "claude";
  for (const a of state.agents) {
    const card = el("div", "pcard agent-conv-card");
    card.style.setProperty("--accent", providerColor(defaultPkey));
    card.dataset.agentId = a.id;
    const models = modelOptionsFor(defaultPkey, (state.catalog?.[defaultPkey]?.models || [])[0]);
    card.innerHTML =
      `<div class="ph">` +
      `<span class="dot"></span><span class="nm">${esc(a.name)}</span>` +
      `<label class="chk" style="margin-left:auto"><input type="checkbox" class="a-active" data-id="${esc(a.id)}" /> usar</label>` +
      `</div>` +
      `<div class="agent-desc note">${esc((a.description || "").slice(0, 120))}${(a.description || "").length > 120 ? "…" : ""}</div>` +
      `<div class="pgrid a-config" data-id="${esc(a.id)}" style="display:none">` +
      `<div><label class="note">CLI</label><select class="a-pkey" data-id="${esc(a.id)}">${providerOptions(defaultPkey)}</select></div>` +
      `<div><label class="note">Modelo</label><select class="a-model" data-id="${esc(a.id)}">${models}</select>` +
      `<input type="text" class="a-model-custom" data-id="${esc(a.id)}" placeholder="modelo customizado" style="display:none;margin-top:6px" /></div>` +
      `<div><label class="note">Interação</label><div><label class="chk"><input type="checkbox" class="a-interact" data-id="${esc(a.id)}" checked /> pode perguntar / trocar ideias</label></div></div>` +
      `</div>`;
    box.appendChild(card);
  }

  box.querySelectorAll(".a-active").forEach((chk) => {
    chk.addEventListener("change", () => {
      const cfg = box.querySelector(`.a-config[data-id="${chk.dataset.id}"]`);
      if (cfg) cfg.style.display = chk.checked ? "grid" : "none";
      const card = chk.closest(".agent-conv-card");
      const pkey = box.querySelector(`.a-pkey[data-id="${chk.dataset.id}"]`)?.value || defaultPkey;
      if (card) card.style.setProperty("--accent", providerColor(pkey));
    });
  });

  box.querySelectorAll(".a-pkey").forEach((sel) => {
    sel.addEventListener("change", () => {
      const id = sel.dataset.id;
      const modelSel = box.querySelector(`.a-model[data-id="${id}"]`);
      if (modelSel) {
        modelSel.innerHTML = modelOptionsFor(sel.value, (state.catalog?.[sel.value]?.models || [])[0]);
      }
      const card = sel.closest(".agent-conv-card");
      if (card) card.style.setProperty("--accent", providerColor(sel.value));
    });
  });

  box.querySelectorAll(".a-model").forEach((sel) => {
    sel.addEventListener("change", () => {
      const custom = box.querySelector(`.a-model-custom[data-id="${sel.dataset.id}"]`);
      if (custom) custom.style.display = sel.value === "__custom__" ? "block" : "none";
    });
  });
}

function collectAgentParticipants() {
  const out = [];
  for (const a of state.agents) {
    const chk = document.querySelector(`.a-active[data-id="${a.id}"]`);
    if (!chk?.checked) continue;
    const pkey = document.querySelector(`.a-pkey[data-id="${a.id}"]`)?.value;
    if (!pkey || !state.available.includes(pkey)) continue;
    const sel = document.querySelector(`.a-model[data-id="${a.id}"]`);
    let model = sel ? sel.value : "";
    if (model === "__custom__") {
      model = document.querySelector(`.a-model-custom[data-id="${a.id}"]`)?.value.trim() || "";
    }
    if (!model) continue;
    out.push({
      pkey: `${pkey}:${a.id}`,
      label: a.name,
      model,
      active: true,
      can_interact: document.querySelector(`.a-interact[data-id="${a.id}"]`)?.checked ?? true,
      persona: a.description,
      agent_id: a.id,
    });
  }
  return out;
}

function collectAdhocParticipants() {
  const participants = [];
  for (const key of PROVIDER_ORDER) {
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
  return participants;
}

/* ---------------- modal ---------------- */
function buildParticipantRows() {
  const box = $("participants"); box.innerHTML = "";
  const cat = state.catalog || {};
  const avail = state.available;
  if (!avail.length) { $("no-keys").style.display = "block"; }
  for (const key of PROVIDER_ORDER) {
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

function openModal() {
  buildConvAgentRows();
  $("modal-bg").classList.add("open");
}
function closeModal() { $("modal-bg").classList.remove("open"); }

async function createConversation() {
  const agentParts = collectAgentParticipants();
  const adhocParts = collectAdhocParticipants();
  const participants = [...agentParts, ...adhocParts];
  if (!participants.length) {
    alert("Selecione ao menos um agente (com CLI/modelo) ou um participante ad-hoc.");
    return;
  }

  const goal = $("f-goal").value.trim();
  if (!goal) { alert("Informe o objetivo da conversa."); return; }
  const stopWhen = $("f-stop-when").value.trim();
  const deliverable = $("f-deliverable").value.trim();

  const agentIds = agentParts.map((p) => p.agent_id).filter(Boolean);
  const payload = {
    title: PLACEHOLDER_TITLE,
    goal,
    mode: $("f-sequential").checked ? "sequential" : "parallel",
    max_rounds: parseInt($("f-rounds").value) || 3,
    token_budget: parseInt($("f-budget").value) || 0,
    config: {
      web: $("f-web").checked,
      apify: $("f-apify").checked,
      mcp: $("f-mcp").checked,
      synthesize: $("f-synth").checked,
      agent_ids: agentIds,
      stop_when: stopWhen,
      deliverable,
    },
    participants: participants.map(({ agent_id, ...rest }) => rest),
  };
  try {
    const { id } = await api("/api/conversations", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    closeModal();
    await openConversation(id, { replaceUrl: true });
    generateTitle(id, goal, participants);
  } catch (e) {
    alert("Erro ao criar conversa: " + e.message);
  }
}

/* ---------------- organograma ORG ---------------- */
const ORG_NODE_W = 148;
const ORG_NODE_H = 42;
const ORG_GAP_X = 24;
const ORG_GAP_Y = 56;

function orgRunsFromTrace(trace) {
  const runs = new Set();
  for (const e of trace) {
    if (e.run_index) runs.add(e.run_index);
  }
  return [...runs].sort((a, b) => a - b);
}

function makeOrgNode(id, label, kind, status, participant, logs) {
  return {
    id, label, kind, status: status || "pending",
    participant: participant || null,
    logs: logs || [],
    children: [],
    x: 0, y: 0, w: ORG_NODE_W, h: ORG_NODE_H,
  };
}

function buildOrgTree(events, runIndex, participants, messages) {
  const filtered = events.filter((e) => (e.run_index || 1) === runIndex);
  if (!filtered.length && messages?.length) {
    return buildOrgTreeFromMessages(messages, runIndex);
  }

  const root = makeOrgNode("run", `Execução ${runIndex}`, "run", "pending", null, []);
  let currentRound = null;
  let currentTurn = null;
  let pendingTool = null;
  let synthTurn = null;
  const systemLogs = [];

  for (const ev of filtered) {
    const p = ev.payload || {};
    switch (ev.type) {
      case "run_start":
        root.label = `Execução ${runIndex}`;
        root.logs = [
          `Objetivo: ${p.goal || "—"}`,
          `Modo: ${p.mode === "parallel" ? "Paralelo" : "Sequencial"}`,
          `Rodadas: ${p.max_rounds || "?"}`,
        ];
        if (p.stop_when) root.logs.push(`Encerrar quando: ${p.stop_when}`);
        if (p.deliverable) root.logs.push(`Produzir ao final: ${p.deliverable}`);
        root.status = "active";
        break;
      case "round":
        currentTurn = null;
        pendingTool = null;
        currentRound = makeOrgNode(
          `round-${p.round}`, `Rodada ${p.round}/${p.total}`, "round", "done", null, [],
        );
        root.children.push(currentRound);
        break;
      case "turn_start": {
        const parent = currentRound || root;
        currentTurn = makeOrgNode(
          `turn-${p.round}-${p.speaker}-${ev.seq}`,
          p.label || p.speaker,
          "turn",
          "active",
          p.speaker,
          [`Início do turno · rodada ${p.round || "?"}`],
        );
        parent.children.push(currentTurn);
        pendingTool = null;
        break;
      }
      case "agent_step": {
        const key = p.participant;
        let turn = currentTurn;
        if (key === "synth") {
          if (!synthTurn) {
            synthTurn = makeOrgNode("synth-turn", "Síntese", "turn", "active", "synth", []);
            root.children.push(synthTurn);
          }
          turn = synthTurn;
        }
        if (!turn) {
          turn = makeOrgNode(
            `turn-${key}-${ev.seq}`, LABELS[key] || key, "turn", "active", key, [],
          );
          (currentRound || root).children.push(turn);
          currentTurn = turn;
        }
        if (p.kind === "status") {
          if (p.state === "thinking") {
            turn.children.push(makeOrgNode(
              `think-${ev.seq}`, "Pensando…", "step", "active", key, [],
            ));
            turn.status = "active";
          } else if (p.state === "done") {
            turn.status = "done";
            turn.children.push(makeOrgNode(
              `done-${ev.seq}`, "Mensagem enviada", "step", "done", key, [],
            ));
          } else if (p.state === "error") {
            turn.status = "error";
            turn.children.push(makeOrgNode(
              `err-${ev.seq}`, "Erro no turno", "step", "error", key, [],
            ));
          }
        } else if (p.kind === "tool_call") {
          pendingTool = makeOrgNode(
            `tool-${ev.seq}`, p.tool || "ferramenta", "tool", "active", key,
            [`Chamada: ${p.tool}`, `Args: ${JSON.stringify(p.args || {})}`],
          );
          turn.children.push(pendingTool);
        } else if (p.kind === "tool_result") {
          if (pendingTool) {
            pendingTool.status = "done";
            pendingTool.logs.push(`Resultado: ${(p.preview || "").slice(0, 500)}`);
            pendingTool = null;
          } else {
            turn.children.push(makeOrgNode(
              `res-${ev.seq}`, `↳ ${p.tool || "resultado"}`, "tool", "done", key,
              [(p.preview || "").slice(0, 500)],
            ));
          }
        }
        break;
      }
      case "log":
        systemLogs.push(`[${p.level || "info"}] ${p.message || ""}`);
        break;
      case "status":
        if (p.state === "done") root.status = "done";
        else if (p.state === "error") root.status = "error";
        else if (p.state === "stopped") root.status = "error";
        else if (p.state === "running") root.status = "active";
        root.logs.push(`Status: ${p.state}`);
        break;
      case "message":
        break;
      default:
        break;
    }
  }

  if (systemLogs.length) {
    const logNode = makeOrgNode("system-logs", "Log do sistema", "logs", "done", null, systemLogs);
    root.children.push(logNode);
  }

  markOrgActiveNode(root);
  return root;
}

function buildOrgTreeFromMessages(messages, runIndex) {
  const root = makeOrgNode("run", `Execução ${runIndex}`, "run", "done", null, [
    "Trace detalhado indisponível — reconstruído a partir das mensagens.",
  ]);
  const byRound = {};
  for (const m of messages || []) {
    const rnd = m.round || 0;
    if (!byRound[rnd]) {
      byRound[rnd] = makeOrgNode(
        `round-${rnd}`, rnd ? `Rodada ${rnd}` : "Outros", "round", "done", null, [],
      );
      root.children.push(byRound[rnd]);
    }
    byRound[rnd].children.push(makeOrgNode(
      `msg-${m.id}`, m.speaker_label || m.speaker_key, "turn", "done", m.speaker_key,
      [(m.content || "").slice(0, 300)],
    ));
  }
  return root;
}

function markOrgActiveNode(root) {
  let lastActive = null;
  const walk = (n) => {
    if (n.status === "active") lastActive = n;
    for (const ch of n.children) walk(ch);
  };
  walk(root);
  if (lastActive && state.status === "running") return;
  if (lastActive && state.status !== "running") {
    lastActive.status = lastActive.status === "active" ? "done" : lastActive.status;
  }
}

function calcOrgSubtreeW(node) {
  if (!node.children.length) {
    node.subtreeW = ORG_NODE_W;
    return node.subtreeW;
  }
  let total = 0;
  for (const ch of node.children) {
    total += calcOrgSubtreeW(ch) + ORG_GAP_X;
  }
  node.subtreeW = Math.max(ORG_NODE_W, total - ORG_GAP_X);
  return node.subtreeW;
}

function assignOrgPositions(node, leftX, depth) {
  node.absY = depth * (ORG_NODE_H + ORG_GAP_Y);
  if (!node.children.length) {
    node.absX = leftX + node.subtreeW / 2;
    return leftX + node.subtreeW;
  }
  let x = leftX;
  for (const ch of node.children) {
    x = assignOrgPositions(ch, x, depth + 1);
    x += ORG_GAP_X;
  }
  node.absX = leftX + node.subtreeW / 2;
  return leftX + node.subtreeW;
}

function layoutOrgTree(node) {
  calcOrgSubtreeW(node);
  assignOrgPositions(node, 0, 0);
  const offset = -node.absX;
  const shift = (n) => {
    n.absX += offset;
    for (const ch of n.children) shift(ch);
  };
  shift(node);
}

function flattenOrgTree(node, list, parent) {
  node.parent = parent || null;
  list.push(node);
  for (const ch of node.children) flattenOrgTree(ch, list, node);
}

function orgNodeColor(node) {
  if (node.participant) return providerColor(node.participant);
  if (node.kind === "run") return "#5b8def";
  if (node.kind === "round") return "#46c6d8";
  if (node.kind === "logs") return "#888";
  return "#666";
}

function orgStatusStroke(status) {
  return { pending: "#3a4050", active: "#9d7bf0", done: "#19c39c", error: "#e05c5c" }[status] || "#3a4050";
}

function drawOrgCanvas() {
  const canvas = $("org-canvas");
  const wrap = $("org-canvas-wrap");
  if (!canvas || !wrap || !state.orgTree) return;

  const dpr = window.devicePixelRatio || 1;
  const rect = wrap.getBoundingClientRect();
  canvas.width = Math.max(1, rect.width * dpr);
  canvas.height = Math.max(480, rect.height) * dpr;
  canvas.style.height = Math.max(480, rect.height) + "px";

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, rect.width, rect.height);

  layoutOrgTree(state.orgTree);
  const flat = [];
  flattenOrgTree(state.orgTree, flat);
  state.orgFlatNodes = flat;

  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const n of flat) {
    const x = n.absX;
    const y = n.absY;
    minX = Math.min(minX, x - ORG_NODE_W / 2);
    maxX = Math.max(maxX, x + ORG_NODE_W / 2);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y + ORG_NODE_H);
  }

  const treeW = maxX - minX + 80;
  const treeH = maxY - minY + 80;
  if (!state.orgView._centered) {
    state.orgView.panX = (rect.width - treeW * state.orgView.zoom) / 2 - minX * state.orgView.zoom + 40;
    state.orgView.panY = 40 - minY * state.orgView.zoom;
    state.orgView._centered = true;
  }

  ctx.save();
  ctx.translate(state.orgView.panX, state.orgView.panY);
  ctx.scale(state.orgView.zoom, state.orgView.zoom);

  for (const n of flat) {
    if (!n.parent) continue;
    const px = n.parent.absX;
    const py = n.parent.absY + ORG_NODE_H;
    const cx = n.absX;
    const cy = n.absY;
    ctx.strokeStyle = "#2a3142";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(px, py);
    ctx.lineTo(px, py + (ORG_GAP_Y - ORG_NODE_H) / 2);
    ctx.lineTo(cx, py + (ORG_GAP_Y - ORG_NODE_H) / 2);
    ctx.lineTo(cx, cy);
    ctx.stroke();
  }

  for (const n of flat) {
    const x = n.absX - ORG_NODE_W / 2;
    const y = n.absY;
    const accent = orgNodeColor(n);
    const stroke = orgStatusStroke(n.status);
    ctx.fillStyle = "#12151c";
    ctx.strokeStyle = stroke;
    ctx.lineWidth = n.id === state.orgSelectedNode?.id ? 2.5 : 1.5;
    roundRect(ctx, x, y, ORG_NODE_W, ORG_NODE_H, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = accent;
    ctx.fillRect(x, y, 4, ORG_NODE_H);

    if (n.status === "active" && state.status === "running") {
      ctx.strokeStyle = "#9d7bf0";
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.35 + 0.35 * Math.sin(state.orgPulse);
      roundRect(ctx, x - 2, y - 2, ORG_NODE_W + 4, ORG_NODE_H + 4, 10);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    ctx.fillStyle = "#e8eaef";
    ctx.font = "600 11px JetBrains Mono, monospace";
    const label = n.label.length > 18 ? n.label.slice(0, 17) + "…" : n.label;
    ctx.fillText(label, x + 10, y + 18);
    ctx.fillStyle = "#5d6478";
    ctx.font = "9px JetBrains Mono, monospace";
    ctx.fillText(n.kind, x + 10, y + 32);
  }

  ctx.restore();
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function hitTestOrgCanvas(clientX, clientY) {
  const canvas = $("org-canvas");
  const wrap = $("org-canvas-wrap");
  if (!canvas || !wrap) return null;
  const rect = canvas.getBoundingClientRect();
  const x = (clientX - rect.left - state.orgView.panX) / state.orgView.zoom;
  const y = (clientY - rect.top - state.orgView.panY) / state.orgView.zoom;
  for (let i = state.orgFlatNodes.length - 1; i >= 0; i--) {
    const n = state.orgFlatNodes[i];
    const nx = n.absX - ORG_NODE_W / 2;
    const ny = n.absY;
    if (x >= nx && x <= nx + ORG_NODE_W && y >= ny && y <= ny + ORG_NODE_H) return n;
  }
  return null;
}

function renderOrgLogPanel(node) {
  const empty = $("org-log-empty");
  const content = $("org-log-content");
  if (!node) {
    empty.style.display = "block";
    content.style.display = "none";
    return;
  }
  empty.style.display = "none";
  content.style.display = "block";
  const lines = (node.logs || []).map((l) => `<div class="log-line">${esc(l)}</div>`).join("");
  content.innerHTML =
    `<div class="log-h">${esc(node.label)} <span style="color:var(--muted)">(${esc(node.kind)})</span></div>` +
    (lines || `<div class="log-line" style="color:var(--muted)">Sem logs adicionais.</div>`);
}

function refreshOrgView() {
  const runs = orgRunsFromTrace(state.trace);
  const sel = $("org-run-select");
  sel.innerHTML = "";
  if (runs.length > 1) {
    sel.style.display = "inline-block";
    for (const r of runs) {
      const opt = document.createElement("option");
      opt.value = r;
      opt.textContent = `Execução ${r}`;
      if (r === state.orgRunIndex) opt.selected = true;
      sel.appendChild(opt);
    }
  } else {
    sel.style.display = "none";
    if (runs.length) state.orgRunIndex = runs[runs.length - 1];
  }

  const msgs = [];
  state.orgTree = buildOrgTree(state.trace, state.orgRunIndex, state.participants, state.messages);
  const warn = $("org-warn");
  const hasDetail = state.trace.some((e) => e.run_index === state.orgRunIndex);
  if (!hasDetail && state.participants.length) {
    warn.style.display = "block";
    warn.textContent = "Trace detalhado indisponível para esta execução — organograma reconstruído a partir das mensagens.";
  } else {
    warn.style.display = "none";
  }

  state.orgView._centered = false;
  drawOrgCanvas();
  if (state.orgSelectedNode) {
    const found = state.orgFlatNodes.find((n) => n.id === state.orgSelectedNode.id);
    renderOrgLogPanel(found || null);
  }
  startOrgAnim();
}

function startOrgAnim() {
  stopOrgAnim();
  if (!state.orgModalOpen || state.status !== "running") return;
  const tick = () => {
    state.orgPulse += 0.08;
    drawOrgCanvas();
    state.orgAnimFrame = requestAnimationFrame(tick);
  };
  state.orgAnimFrame = requestAnimationFrame(tick);
}

function stopOrgAnim() {
  if (state.orgAnimFrame) {
    cancelAnimationFrame(state.orgAnimFrame);
    state.orgAnimFrame = null;
  }
}

function wireOrgCanvas() {
  const wrap = $("org-canvas-wrap");
  const canvas = $("org-canvas");
  if (!wrap || !canvas) return;

  wrap.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    state.orgView.dragging = true;
    state.orgView.lastX = e.clientX;
    state.orgView.lastY = e.clientY;
    wrap.classList.add("dragging");
  });
  window.addEventListener("mousemove", (e) => {
    if (!state.orgView.dragging) return;
    state.orgView.panX += e.clientX - state.orgView.lastX;
    state.orgView.panY += e.clientY - state.orgView.lastY;
    state.orgView.lastX = e.clientX;
    state.orgView.lastY = e.clientY;
    drawOrgCanvas();
  });
  window.addEventListener("mouseup", () => {
    state.orgView.dragging = false;
    wrap.classList.remove("dragging");
  });
  wrap.addEventListener("wheel", (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    state.orgView.zoom = Math.min(2.5, Math.max(0.35, state.orgView.zoom * delta));
    drawOrgCanvas();
  }, { passive: false });
  canvas.addEventListener("click", (e) => {
    if (state.orgView.dragging) return;
    const node = hitTestOrgCanvas(e.clientX, e.clientY);
    state.orgSelectedNode = node;
    renderOrgLogPanel(node);
    drawOrgCanvas();
  });
  window.addEventListener("resize", () => {
    if (state.orgModalOpen) drawOrgCanvas();
  });
}

async function openOrgModal(cid) {
  const target = cid || state.cid;
  if (!target) { alert("Selecione uma conversa primeiro."); return; }
  if (target !== state.cid) await openConversation(target);
  try {
    const full = await api(`/api/conversations/${state.cid}`);
    state.trace = full.trace || [];
    state.messages = full.messages || [];
    state.participants = full.participants || state.participants;
  } catch (e) {
    try {
      const data = await api(`/api/conversations/${state.cid}/trace`);
      state.trace = data.trace || state.trace;
    } catch (e2) { /* mantém estado atual */ }
  }
  const runs = orgRunsFromTrace(state.trace);
  state.orgRunIndex = runs.length ? runs[runs.length - 1] : 1;
  state.orgSelectedNode = null;
  state.orgView = { panX: 40, panY: 40, zoom: 1, dragging: false, lastX: 0, lastY: 0 };
  state.orgModalOpen = true;
  $("org-modal-bg").classList.add("open");
  renderOrgLogPanel(null);
  refreshOrgView();
}

function closeOrgModal() {
  state.orgModalOpen = false;
  $("org-modal-bg").classList.remove("open");
  stopOrgAnim();
}

init();
