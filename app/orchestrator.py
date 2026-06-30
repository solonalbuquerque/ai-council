"""Conversation engine between AIs."""
import asyncio

from app import store
from app.providers import make_provider
from app.tools import build_tools, filter_tools_for_participant

# conv_id -> active Runner
RUNNERS: dict[str, "Runner"] = {}

FOLLOWUP_SYSTEM = (
    "You continue the conversation with the human after the council debate. "
    "Respond directly to what the human said, based on the context. "
    "Be clear and conversational. Respond in the same language as the goal."
)

COMPRESS_SYSTEM = (
    "You summarize debates between multiple AIs. Produce a dense, structured summary "
    "with: consensus, disagreements, verified facts, open hypotheses, and "
    "pending decisions. Preserve important numbers and names. "
    "Respond in the same language as the goal."
)


def build_goal_context(conv: dict) -> str:
    cfg = conv.get("config") or {}
    parts = [f"GOAL:\n{conv.get('goal') or ''}"]
    stop = (cfg.get("stop_when") or "").strip()
    deliver = (cfg.get("deliverable") or "").strip()
    if stop:
        parts.append(f"STOP WHEN:\n{stop}")
    if deliver:
        parts.append(f"DELIVER AT END:\n{deliver}")
    return "\n\n".join(parts)


def _run_config(conv: dict) -> dict:
    return conv.get("config") or {}


def _transcript_chars(transcript: list[tuple[str, str]]) -> int:
    return sum(len(n) + len(t) + 4 for n, t in transcript)


def _trim_transcript(
    transcript: list[tuple[str, str]],
    max_chars: int,
    keep_last_round: bool = True,
    round_start_idx: int = 0,
) -> list[tuple[str, str]]:
    if _transcript_chars(transcript) <= max_chars:
        return transcript

    if keep_last_round and 0 < round_start_idx < len(transcript):
        prefix = list(transcript[:round_start_idx])
        suffix = list(transcript[round_start_idx:])
        while _transcript_chars(prefix) + _transcript_chars(suffix) > max_chars and len(prefix) > 1:
            prefix.pop(0)
        while _transcript_chars(prefix) + _transcript_chars(suffix) > max_chars and len(suffix) > 1:
            suffix.pop(0)
        return prefix + suffix

    trimmed = list(transcript)
    while _transcript_chars(trimmed) > max_chars and len(trimmed) > 1:
        trimmed.pop(0)
    return trimmed


def build_prompt(conv, transcript, label, others, can_interact, persona):
    cfg = _run_config(conv)
    interact = (
        "You MAY ask questions of other participants and the human, and answer "
        "questions directed at you."
        if can_interact
        else "You must NOT ask questions; present only your analysis and contribution."
    )
    persona_line = f"Persona: {persona.strip()}\n" if persona and persona.strip() else ""
    stop_hint = ""
    if (cfg.get("stop_when") or "").strip():
        stop_hint = (
            " Evaluate whether the STOP WHEN criteria have been met; "
            "if so, explicitly state that the debate may be concluded."
        )
    max_words = int(cfg.get("max_words_per_turn") or 0)
    concision = (
        f" Limit your response to at most {max_words} words."
        if max_words > 0
        else ""
    )
    system = (
        f"You are {label}, collaborating with {others} to achieve the GOAL below.\n"
        f"{persona_line}{interact}\n"
        "Be concrete and concise; add value, do not agree for the sake of agreeing. "
        "If you need external data, use the available tools. "
        f"Respond in the same language as the goal.{stop_hint}{concision}"
    )
    convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript) or "(start — no messages yet)"
    goal_ctx = build_goal_context(conv)
    user = f"{goal_ctx}\n\nCONVERSATION SO FAR:\n{convo}\n\nYour turn, {label}."
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
        return p, "synth", "Synthesis"
    p = parts[-1]
    return p, p["pkey"], p["label"]


def _pick_summarizer(parts: list) -> dict:
    for p in parts:
        if "summarizer" in (p.get("label") or "").lower() or "resumidor" in (p.get("label") or "").lower():
            return p
    return parts[0]


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

    def _provider_kwargs(self, conv: dict) -> dict:
        cfg = _run_config(conv)
        return {
            "max_output_tokens": int(cfg.get("max_output_tokens") or 2000),
            "tool_result_max_chars": int(cfg.get("tool_result_max_chars") or 4000),
        }

    async def _emit_context_size(self, conv: dict, transcript: list[tuple[str, str]]):
        cfg = _run_config(conv)
        chars = _transcript_chars(transcript)
        max_chars = int(cfg.get("context_max_chars") or 12000)
        await self.emit("context_size", {
            "chars": chars,
            "max_chars": max_chars,
            "estimated_tokens": chars // 4,
            "token_budget": conv.get("token_budget") or 0,
            "total_tokens": self.total_tokens,
        })

    async def _compress_transcript(
        self,
        conv: dict,
        transcript: list[tuple[str, str]],
        rnd: int,
        round_start_idx: int,
        providers: dict,
        parts: list,
    ) -> list[tuple[str, str]]:
        cfg = _run_config(conv)
        keep_last = cfg.get("context_keep_last_round", True)

        if keep_last and round_start_idx > 0:
            to_summarize = transcript[:round_start_idx]
            keep = transcript[round_start_idx:]
        else:
            to_summarize = transcript
            keep = []

        if not to_summarize:
            return transcript

        synth_p = _pick_summarizer(parts)
        prov = providers[synth_p["pkey"]]
        convo = "\n\n".join(f"{n}:\n{t}" for n, t in to_summarize)
        user = (
            f"{build_goal_context(conv)}\n\nCONVERSATION TO SUMMARIZE:\n{convo}\n\n"
            "Summarize in at most 800 words, keeping concrete data."
        )

        async def step(kind, payload):
            await self.emit("agent_step", {"participant": "synth", "kind": kind, **payload})

        kwargs = self._provider_kwargs(conv)
        kwargs["max_output_tokens"] = min(kwargs["max_output_tokens"], 1500)
        res = await prov.run(COMPRESS_SYSTEM, user, [], step, **kwargs)
        self.total_tokens += res.input_tokens + res.output_tokens

        summary_label = f"Synthesis (through round {rnd})"
        new_transcript = [(summary_label, res.text)] + list(keep)

        m = await store.save_message(
            self.conv_id, rnd, "synth", summary_label, "synthesis", res.text,
            {"model": prov.model, "kind": "round_summary", "round": rnd},
        )
        await store.save_usage(
            self.conv_id, "synth", rnd, res.input_tokens,
            res.output_tokens, res.cost_usd, res.tool_calls,
        )
        await self.emit("message", m)
        await self.emit("scoreboard", await store.scoreboard(self.conv_id))
        return new_transcript

    async def _maybe_compress_context(
        self,
        conv: dict,
        transcript: list[tuple[str, str]],
        rnd: int,
        round_start_idx: int,
        providers: dict,
        parts: list,
    ) -> list[tuple[str, str]]:
        cfg = _run_config(conv)
        max_chars = int(cfg.get("context_max_chars") or 12000)
        before = _transcript_chars(transcript)

        if before <= max_chars:
            await self._emit_context_size(conv, transcript)
            return transcript

        if cfg.get("compress_context", True):
            try:
                new_transcript = await self._compress_transcript(
                    conv, transcript, rnd, round_start_idx, providers, parts,
                )
                after = _transcript_chars(new_transcript)
                if after <= max_chars or after < before:
                    await self.emit("context_compressed", {
                        "round": rnd,
                        "chars_before": before,
                        "chars_after": after,
                        "max_chars": max_chars,
                    })
                    await self.emit("log", {
                        "level": "info",
                        "message": (
                            f"Context compressed: {before:,} → {after:,} chars "
                            f"(round {rnd})"
                        ),
                    })
                    await self._emit_context_size(conv, new_transcript)
                    return new_transcript
            except Exception as e:
                await self.emit("log", {
                    "level": "warn",
                    "message": f"Compression failed ({e}). Using truncation.",
                })

        trimmed = _trim_transcript(
            transcript, max_chars,
            cfg.get("context_keep_last_round", True),
            round_start_idx,
        )
        after = _transcript_chars(trimmed)
        if after < before:
            await self.emit("log", {
                "level": "info",
                "message": (
                    f"Context truncated: {before:,} → {after:,} chars (round {rnd})"
                ),
            })
        await self._emit_context_size(conv, trimmed)
        return trimmed

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
        """Human messages were already saved/broadcast by the WS layer;
        here they enter the transcript the AIs see."""
        delivered = []
        while not self.human_q.empty():
            item = self.human_q.get_nowait()
            transcript.append(("Human", item["text"]))
            delivered.append(item)
        for item in delivered:
            await self.emit("human_ack", {
                "message_id": item["id"],
                "status": "delivered",
                "detail": "Delivered — included in the AIs' context.",
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
        others = ", ".join(n for n in names if n != label) or "no one"
        system, user = build_prompt(conv, transcript, label, others, p["can_interact"], p["persona"])
        participant_tools = filter_tools_for_participant(tools, _run_config(conv), key)
        prov_kwargs = self._provider_kwargs(conv)

        await self.emit("turn_start", {"speaker": key, "label": label, "round": rnd})
        await self.emit("agent_step",
                        {"participant": key, "round": rnd, "kind": "status", "state": "thinking"})

        async def step(kind, payload):
            await self.emit("agent_step",
                            {"participant": key, "round": rnd, "kind": kind, **payload})

        try:
            res = await prov.run(system, user, participant_tools, step, **prov_kwargs)
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
        await self._emit_context_size(conv, transcript)
        return res

    async def _run_followup_turn(self, conv, parts, providers, transcript, responder_label):
        resp_p, resp_key, resp_label = _pick_responder(conv, parts)
        prov = providers[resp_p["pkey"]]
        use_synth = conv["config"].get("synthesize", True)
        prov_kwargs = self._provider_kwargs(conv)

        convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript)
        user = (
            f"{build_goal_context(conv)}\n\nCONVERSATION:\n{convo}\n\n"
            f"Reply to the human as {responder_label}."
        )

        await self.emit("agent_step",
                        {"participant": resp_key, "kind": "status", "state": "thinking"})

        async def step(kind, payload):
            await self.emit("agent_step", {"participant": resp_key, "kind": kind, **payload})

        res = await prov.run(FOLLOWUP_SYSTEM, user, [], step, **prov_kwargs)
        self.total_tokens += res.input_tokens + res.output_tokens

        if use_synth:
            m = await store.save_message(
                self.conv_id, 0, "synth", "Synthesis", "synthesis", res.text,
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
                                    {"level": "warn", "message": f"No API key for {p['label']} — skipping."})
            parts = [p for p in parts if p["pkey"] in providers]
            if not parts:
                await self.emit("error", {"message": "No active AI with an API key."})
                await store.set_status(self.conv_id, "idle")
                return

            tools = build_tools(conv["config"], self.mcp_tools)
            names = [p["label"] for p in parts]
            transcript = _build_transcript(conv["messages"])
            goal_ctx = build_goal_context(conv)

            await store.set_status(self.conv_id, "running")
            await self.emit("status", {"state": "running"})
            budget = conv["token_budget"] or 0
            await self._emit_context_size(conv, transcript)

            for rnd in range(1, conv["max_rounds"] + 1):
                if not await self._checkpoint():
                    break
                await self.emit("round", {"round": rnd, "total": conv["max_rounds"]})
                round_start_idx = len(transcript)
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

                transcript = await self._maybe_compress_context(
                    conv, transcript, rnd, round_start_idx, providers, parts,
                )

                if budget and self.total_tokens >= budget:
                    await self.emit("log",
                                    {"level": "warn", "message": f"Token budget of {budget} reached."})
                    break

            # ---- final synthesis ----
            if conv["config"].get("synthesize", True) and not self._stopped and await self._checkpoint():
                synth_p = parts[0]
                prov = providers[synth_p["pkey"]]
                prov_kwargs = self._provider_kwargs(conv)
                await self.emit("agent_step",
                                {"participant": "synth", "kind": "status", "state": "thinking"})
                deliver = ((conv.get("config") or {}).get("deliverable") or "").strip()
                deliver_hint = f" Deliver exactly the format requested in DELIVER AT END: {deliver}." if deliver else ""
                system = (
                    "You are the synthesizer. Read the conversation and produce ONE final response, "
                    "clear and actionable, achieving the goal. Integrate the best points and "
                    "list open questions. Respond in the same language as the goal."
                    + deliver_hint
                )
                convo = "\n\n".join(f"{n}:\n{t}" for n, t in transcript)
                user = f"{goal_ctx}\n\nCONVERSATION:\n{convo}\n\nProduce the final response."

                async def step(kind, payload):
                    await self.emit("agent_step", {"participant": "synth", "kind": kind, **payload})

                res = await prov.run(system, user, [], step, **prov_kwargs)
                self.total_tokens += res.input_tokens + res.output_tokens
                m = await store.save_message(self.conv_id, 0, "synth", "Synthesis", "synthesis",
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
                await self.emit("error", {"message": "No active AI with an API key."})
                if trigger_message_id:
                    await self._emit_human_ack(
                        trigger_message_id, "answered",
                        "Could not reply — no AI available.",
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
                    f"{responder_label} is replying to the human…",
                    responder_label,
                )

                try:
                    await self._run_followup_turn(conv, parts, providers, transcript, responder_label)
                    await self._emit_human_ack(
                        message_id, "answered",
                        "Reply sent. You can continue the conversation.",
                        responder_label,
                    )
                except Exception as e:
                    await self.emit("log", {"level": "error", "message": str(e)})
                    await self._emit_human_ack(
                        message_id, "answered",
                        f"Error replying: {e}",
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
