"""Motor da conversa entre as IAs."""
import asyncio

from app import store
from app.providers import make_provider
from app.tools import build_tools

# conversa_id -> Runner ativo
RUNNERS: dict[str, "Runner"] = {}


def build_prompt(goal, transcript, label, others, can_interact, persona):
    interact = (
        "Você PODE fazer perguntas aos outros participantes e ao humano, e responder "
        "perguntas dirigidas a você."
        if can_interact
        else "Você NÃO deve fazer perguntas; apresente apenas sua análise e contribuição."
    )
    persona_line = f"Persona: {persona.strip()}\n" if persona and persona.strip() else ""
    system = (
        f"Você é {label}, colaborando com {others} para atingir o OBJETIVO abaixo.\n"
        f"{persona_line}{interact}\n"
        "Seja concreto e conciso; agregue valor, não concorde por concordar. "
        "Se precisar de dados externos, use as ferramentas disponíveis. "
        "Responda no idioma do objetivo."
    )
    convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript) or "(início — ainda sem mensagens)"
    user = f"OBJETIVO:\n{goal}\n\nCONVERSA ATÉ AQUI:\n{convo}\n\nSua vez, {label}."
    return system, user


class Runner:
    def __init__(self, conv_id, emit, mcp_tools=None, run_index=1):
        self.conv_id = conv_id
        self.emit = emit  # async (type:str, payload:dict)
        self.mcp_tools = mcp_tools or []
        self.run_index = run_index
        self._gate = asyncio.Event()
        self._gate.set()
        self._stopped = False
        self.human_q: asyncio.Queue[str] = asyncio.Queue()
        self.total_tokens = 0

    # ---- controles ----
    def pause(self):
        self._gate.clear()

    def resume(self):
        self._gate.set()

    def stop(self):
        self._stopped = True
        self._gate.set()

    def add_human(self, text: str):
        self.human_q.put_nowait(text)

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

    def _drain_human(self, transcript: list):
        """Mensagens humanas já foram salvas/transmitidas pela camada WS;
        aqui só entram na transcrição que as IAs veem."""
        while not self.human_q.empty():
            text = self.human_q.get_nowait()
            transcript.append(("Humano", text))

    # ---- um turno de uma IA ----
    async def _turn(self, p, prov, goal, transcript, names, tools, rnd):
        key, label = p["pkey"], p["label"]
        others = ", ".join(n for n in names if n != label) or "ninguém"
        system, user = build_prompt(goal, transcript, label, others, p["can_interact"], p["persona"])

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
            transcript = [
                (m["speaker_label"], m["content"])
                for m in conv["messages"]
                if m["role"] in ("participant", "human", "synthesis")
            ]

            await store.set_status(self.conv_id, "running")
            await self.emit("status", {"state": "running"})
            budget = conv["token_budget"] or 0

            for rnd in range(1, conv["max_rounds"] + 1):
                if not await self._checkpoint():
                    break
                await self.emit("round", {"round": rnd, "total": conv["max_rounds"]})
                self._drain_human(transcript)

                if conv["mode"] == "parallel":
                    snapshot = list(transcript)

                    async def do(p, snap=snapshot, r=rnd):
                        return p, await self._turn(
                            p, providers[p["pkey"]], conv["goal"], snap, names, tools, r)

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
                        self._drain_human(transcript)
                        res = await self._turn(
                            p, providers[p["pkey"]], conv["goal"], transcript, names, tools, rnd)
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
                system = (
                    "Você é o sintetizador. Leia a conversa e produza UMA resposta final, "
                    "clara e acionável, atingindo o objetivo. Integre os melhores pontos e "
                    "liste questões em aberto. Responda no idioma do objetivo."
                )
                convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript)
                user = f"OBJETIVO:\n{conv['goal']}\n\nCONVERSA:\n{convo}\n\nProduza a resposta final."

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


async def start_runner(conv_id, emit, mcp_tools=None) -> "Runner":
    if conv_id in RUNNERS:
        return RUNNERS[conv_id]
    run_index = await store.next_run_index(conv_id)

    async def run_emit(type_: str, payload: dict):
        await emit(type_, {**payload, "run_index": run_index})

    r = Runner(conv_id, run_emit, mcp_tools, run_index)
    RUNNERS[conv_id] = r
    asyncio.create_task(r.run())
    return r
