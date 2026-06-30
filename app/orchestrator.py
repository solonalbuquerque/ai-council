"""Motor da conversa entre as IAs."""
import asyncio

from app import store
from app.providers import make_provider
from app.tools import build_tools

# conversa_id -> Runner ativo
RUNNERS: dict[str, "Runner"] = {}

FOLLOWUP_SYSTEM = (
    "Você continua a conversa com o humano após o debate do conselho. "
    "Responda diretamente ao que o humano disse, com base no contexto. "
    "Seja claro e conversacional. Responda no idioma do objetivo."
)


def build_goal_context(conv: dict) -> str:
    cfg = conv.get("config") or {}
    parts = [f"OBJETIVO:\n{conv.get('goal') or ''}"]
    stop = (cfg.get("stop_when") or "").strip()
    deliver = (cfg.get("deliverable") or "").strip()
    if stop:
        parts.append(f"ENCERRAR QUANDO:\n{stop}")
    if deliver:
        parts.append(f"PRODUZIR AO FINAL:\n{deliver}")
    return "\n\n".join(parts)


def build_prompt(conv, transcript, label, others, can_interact, persona):
    cfg = conv.get("config") or {}
    interact = (
        "Você PODE fazer perguntas aos outros participantes e ao humano, e responder "
        "perguntas dirigidas a você."
        if can_interact
        else "Você NÃO deve fazer perguntas; apresente apenas sua análise e contribuição."
    )
    persona_line = f"Persona: {persona.strip()}\n" if persona and persona.strip() else ""
    stop_hint = ""
    if (cfg.get("stop_when") or "").strip():
        stop_hint = (
            " Avalie se os critérios de ENCERRAR QUANDO já foram atingidos; "
            "se sim, indique explicitamente que o debate pode ser encerrado."
        )
    system = (
        f"Você é {label}, colaborando com {others} para atingir o OBJETIVO abaixo.\n"
        f"{persona_line}{interact}\n"
        "Seja concreto e conciso; agregue valor, não concorde por concordar. "
        "Se precisar de dados externos, use as ferramentas disponíveis. "
        f"Responda no idioma do objetivo.{stop_hint}"
    )
    convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript) or "(início — ainda sem mensagens)"
    goal_ctx = build_goal_context(conv)
    user = f"{goal_ctx}\n\nCONVERSA ATÉ AQUI:\n{convo}\n\nSua vez, {label}."
    return system, user


def _build_transcript(messages: list) -> list[tuple[str, str]]:
    return [
        (m["speaker_label"], m["content"])
        for m in messages
        if m["role"] in ("participant", "human", "synthesis")
    ]


def _pick_responder(conv: dict, parts: list) -> tuple[dict, str, str]:
    if conv["config"].get("synthesize", True):
        p = parts[0]
        return p, "synth", "Síntese"
    p = parts[-1]
    return p, p["pkey"], p["label"]


class Runner:
    def __init__(self, conv_id, emit, mcp_tools=None, run_index=1, followup=False):
        self.conv_id = conv_id
        self.emit = emit  # async (type:str, payload:dict)
        self.mcp_tools = mcp_tools or []
        self.run_index = run_index
        self.followup = followup
        self._gate = asyncio.Event()
        self._gate.set()
        self._stopped = False
        self.human_q: asyncio.Queue[dict] = asyncio.Queue()
        self.total_tokens = 0
        self.pending_human_id: str | None = None

    # ---- controles ----
    def pause(self):
        self._gate.clear()

    def resume(self):
        self._gate.set()

    def stop(self):
        self._stopped = True
        self._gate.set()

    def add_human(self, message_id: str, text: str):
        self.human_q.put_nowait({"id": message_id, "text": text})

    async def _checkpoint(self) -> bool:
        if self._stopped:
            return False
        if not self._gate.is_set():
            await self.emit("status", {"state": "paused"})
            await self._gate.wait()
            if self._stopped:
                return False
            await self.emit("status", {"state": "running"})
        return True

    async def _drain_human(self, transcript: list):
        """Mensagens humanas já foram salvas/transmitidas pela camada WS;
        aqui entram na transcrição que as IAs veem."""
        delivered = []
        while not self.human_q.empty():
            item = self.human_q.get_nowait()
            transcript.append(("Humano", item["text"]))
            delivered.append(item)
        for item in delivered:
            await self.emit("human_ack", {
                "message_id": item["id"],
                "status": "delivered",
                "detail": "Entregue — incluída no contexto das IAs.",
                "responder": None,
            })

    async def _emit_human_ack(self, message_id, status, detail, responder=None):
        await self.emit("human_ack", {
            "message_id": message_id,
            "status": status,
            "detail": detail,
            "responder": responder,
        })

    # ---- um turno de uma IA ----
    async def _turn(self, p, prov, conv, transcript, names, tools, rnd):
        key, label = p["pkey"], p["label"]
        others = ", ".join(n for n in names if n != label) or "ninguém"
        system, user = build_prompt(conv, transcript, label, others, p["can_interact"], p["persona"])

        await self.emit("turn_start", {"speaker": key, "label": label, "round": rnd})
        await self.emit("agent_step",
                        {"participant": key, "round": rnd, "kind": "status", "state": "thinking"})

        async def step(kind, payload):
            await self.emit("agent_step",
                            {"participant": key, "round": rnd, "kind": kind, **payload})

        try:
            res = await prov.run(system, user, tools, step)
        except Exception as e:
            await self.emit("log", {"level": "error", "message": f"{label}: {e}"})
            await self.emit("agent_step",
                            {"participant": key, "round": rnd, "kind": "status", "state": "error"})
            return None

        self.total_tokens += res.input_tokens + res.output_tokens
        m = await store.save_message(self.conv_id, rnd, key, label, "participant", res.text,
                                     {"model": prov.model})
        await store.save_usage(self.conv_id, key, rnd, res.input_tokens, res.output_tokens,
                               res.cost_usd, res.tool_calls)
        await self.emit("message", m)
        await self.emit("agent_step",
                        {"participant": key, "round": rnd, "kind": "status", "state": "done"})
        await self.emit("scoreboard", await store.scoreboard(self.conv_id))
        return res

    async def _run_followup_turn(self, conv, parts, providers, transcript, responder_label):
        resp_p, resp_key, resp_label = _pick_responder(conv, parts)
        prov = providers[resp_p["pkey"]]
        use_synth = conv["config"].get("synthesize", True)

        convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript)
        user = (
            f"{build_goal_context(conv)}\n\nCONVERSA:\n{convo}\n\n"
            f"Responda ao humano como {responder_label}."
        )

        await self.emit("agent_step",
                        {"participant": resp_key, "kind": "status", "state": "thinking"})

        async def step(kind, payload):
            await self.emit("agent_step", {"participant": resp_key, "kind": kind, **payload})

        res = await prov.run(FOLLOWUP_SYSTEM, user, [], step)
        self.total_tokens += res.input_tokens + res.output_tokens

        if use_synth:
            m = await store.save_message(
                self.conv_id, 0, "synth", "Síntese", "synthesis", res.text,
                {"model": prov.model, "followup": True},
            )
            usage_key = "synth"
            rnd = 0
        else:
            m = await store.save_message(
                self.conv_id, 0, resp_key, resp_label, "participant", res.text,
                {"model": prov.model, "followup": True},
            )
            usage_key = resp_key
            rnd = 0

        await store.save_usage(
            self.conv_id, usage_key, rnd, res.input_tokens,
            res.output_tokens, res.cost_usd, res.tool_calls,
        )
        await self.emit("message", m)
        await self.emit("agent_step",
                        {"participant": resp_key, "kind": "status", "state": "done"})
        await self.emit("scoreboard", await store.scoreboard(self.conv_id))
        transcript.append((resp_label, res.text))
        return resp_label

    # ---- loop principal ----
    async def run(self):
        try:
            conv = await store.get_conversation_full(self.conv_id)
            if not conv:
                return
            await self.emit("run_start", {
                "run_index": self.run_index,
                "goal": conv["goal"],
                "mode": conv["mode"],
                "max_rounds": conv["max_rounds"],
                "stop_when": (conv.get("config") or {}).get("stop_when") or "",
                "deliverable": (conv.get("config") or {}).get("deliverable") or "",
            })
            parts = [p for p in conv["participants"] if p["active"]]
            providers = {}
            for p in parts:
                prov = make_provider(p["pkey"], p["model"])
                if prov:
                    providers[p["pkey"]] = prov
                else:
                    await self.emit("log",
                                    {"level": "warn", "message": f"Sem chave para {p['label']} — pulando."})
            parts = [p for p in parts if p["pkey"] in providers]
            if not parts:
                await self.emit("error", {"message": "Nenhuma IA ativa com chave de API."})
                await store.set_status(self.conv_id, "idle")
                return

            tools = build_tools(conv["config"], self.mcp_tools)
            names = [p["label"] for p in parts]
            transcript = _build_transcript(conv["messages"])
            goal_ctx = build_goal_context(conv)

            await store.set_status(self.conv_id, "running")
            await self.emit("status", {"state": "running"})
            budget = conv["token_budget"] or 0

            for rnd in range(1, conv["max_rounds"] + 1):
                if not await self._checkpoint():
                    break
                await self.emit("round", {"round": rnd, "total": conv["max_rounds"]})
                await self._drain_human(transcript)

                if conv["mode"] == "parallel":
                    snapshot = list(transcript)

                    async def do(p, snap=snapshot, r=rnd):
                        return p, await self._turn(
                            p, providers[p["pkey"]], conv, snap, names, tools, r)

                    if not await self._checkpoint():
                        break
                    results = await asyncio.gather(*[do(p) for p in parts], return_exceptions=True)
                    for item in results:
                        if isinstance(item, Exception):
                            await self.emit("log", {"level": "error", "message": str(item)})
                            continue
                        p, res = item
                        if res is not None:
                            transcript.append((p["label"], res.text))
                else:  # sequential
                    for p in parts:
                        if not await self._checkpoint():
                            break
                        await self._drain_human(transcript)
                        res = await self._turn(
                            p, providers[p["pkey"]], conv, transcript, names, tools, rnd)
                        if res is not None:
                            transcript.append((p["label"], res.text))

                if budget and self.total_tokens >= budget:
                    await self.emit("log",
                                    {"level": "warn", "message": f"Orçamento de {budget} tokens atingido."})
                    break

            # ---- síntese final ----
            if conv["config"].get("synthesize", True) and not self._stopped and await self._checkpoint():
                synth_p = parts[0]
                prov = providers[synth_p["pkey"]]
                await self.emit("agent_step",
                                {"participant": "synth", "kind": "status", "state": "thinking"})
                deliver = ((conv.get("config") or {}).get("deliverable") or "").strip()
                deliver_hint = f" Entregue exatamente o formato pedido em PRODUZIR AO FINAL: {deliver}." if deliver else ""
                system = (
                    "Você é o sintetizador. Leia a conversa e produza UMA resposta final, "
                    "clara e acionável, atingindo o objetivo. Integre os melhores pontos e "
                    "liste questões em aberto. Responda no idioma do objetivo."
                    + deliver_hint
                )
                convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript)
                user = f"{goal_ctx}\n\nCONVERSA:\n{convo}\n\nProduza a resposta final."

                async def step(kind, payload):
                    await self.emit("agent_step", {"participant": "synth", "kind": kind, **payload})

                res = await prov.run(system, user, [], step)
                self.total_tokens += res.input_tokens + res.output_tokens
                m = await store.save_message(self.conv_id, 0, "synth", "Síntese", "synthesis",
                                             res.text, {"model": prov.model})
                await store.save_usage(self.conv_id, "synth", 0, res.input_tokens,
                                       res.output_tokens, res.cost_usd, res.tool_calls)
                await self.emit("message", m)
                await self.emit("agent_step",
                                {"participant": "synth", "kind": "status", "state": "done"})
                await self.emit("scoreboard", await store.scoreboard(self.conv_id))

            final_state = "stopped" if self._stopped else "done"
            await store.set_status(self.conv_id, final_state)
            await self.emit("status", {"state": final_state})

        except asyncio.CancelledError:
            await store.set_status(self.conv_id, "stopped")
            await self.emit("status", {"state": "stopped"})
            raise
        except Exception as e:
            await store.set_status(self.conv_id, "error")
            await self.emit("error", {"message": str(e)})
        finally:
            RUNNERS.pop(self.conv_id, None)

    async def run_followup(self, trigger_message_id: str | None = None):
        try:
            conv = await store.get_conversation_full(self.conv_id)
            if not conv:
                return

            parts = [p for p in conv["participants"] if p["active"]]
            providers = {}
            for p in parts:
                prov = make_provider(p["pkey"], p["model"])
                if prov:
                    providers[p["pkey"]] = prov
            parts = [p for p in parts if p["pkey"] in providers]
            if not parts:
                await self.emit("error", {"message": "Nenhuma IA ativa com chave de API."})
                if trigger_message_id:
                    await self._emit_human_ack(
                        trigger_message_id, "answered",
                        "Não foi possível responder — nenhuma IA disponível.",
                    )
                return

            _, _, responder_label = _pick_responder(conv, parts)
            transcript = _build_transcript(conv["messages"])

            await store.set_status(self.conv_id, "running")
            await self.emit("status", {"state": "running"})

            pending_ids = []
            if trigger_message_id:
                pending_ids.append(trigger_message_id)

            while pending_ids or not self.human_q.empty():
                while not self.human_q.empty():
                    item = self.human_q.get_nowait()
                    pending_ids.append(item["id"])

                message_id = pending_ids.pop(0)
                self.pending_human_id = message_id

                conv = await store.get_conversation_full(self.conv_id)
                if conv:
                    transcript = _build_transcript(conv["messages"])
                    _, _, responder_label = _pick_responder(conv, parts)

                await self._emit_human_ack(
                    message_id, "processing",
                    f"{responder_label} está respondendo ao humano…",
                    responder_label,
                )

                try:
                    await self._run_followup_turn(conv, parts, providers, transcript, responder_label)
                    await self._emit_human_ack(
                        message_id, "answered",
                        "Resposta enviada. Você pode continuar a conversa.",
                        responder_label,
                    )
                except Exception as e:
                    await self.emit("log", {"level": "error", "message": str(e)})
                    await self._emit_human_ack(
                        message_id, "answered",
                        f"Erro ao responder: {e}",
                        responder_label,
                    )

            await store.set_status(self.conv_id, "done")
            await self.emit("status", {"state": "done"})

        except asyncio.CancelledError:
            await store.set_status(self.conv_id, "stopped")
            await self.emit("status", {"state": "stopped"})
            raise
        except Exception as e:
            await store.set_status(self.conv_id, "error")
            await self.emit("error", {"message": str(e)})
        finally:
            RUNNERS.pop(self.conv_id, None)


async def start_runner(conv_id, emit, mcp_tools=None) -> "Runner":
    if conv_id in RUNNERS:
        return RUNNERS[conv_id]
    run_index = await store.next_run_index(conv_id)

    async def run_emit(type_: str, payload: dict):
        if type_ == "human_ack":
            await emit(type_, payload)
        else:
            await emit(type_, {**payload, "run_index": run_index})

    r = Runner(conv_id, run_emit, mcp_tools, run_index)
    RUNNERS[conv_id] = r
    asyncio.create_task(r.run())
    return r


async def start_followup_runner(
    conv_id, emit, mcp_tools=None, trigger_message_id: str | None = None,
) -> "Runner":
    if conv_id in RUNNERS:
        r = RUNNERS[conv_id]
        return r

    run_index = await store.next_run_index(conv_id)

    async def followup_emit(type_: str, payload: dict):
        if type_ == "human_ack":
            await emit(type_, payload)
        else:
            await emit(type_, {**payload, "run_index": run_index})

    r = Runner(conv_id, followup_emit, mcp_tools, run_index, followup=True)
    RUNNERS[conv_id] = r
    asyncio.create_task(r.run_followup(trigger_message_id))
    return r
