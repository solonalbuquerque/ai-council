"""Camada de acesso ao banco."""
from sqlalchemy import func, select

from app import models
from app.agent_presets import AGENT_PRESETS
from app.db import Session


def _agent(a: models.Agent) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "description": a.description,
        "source": a.source,
        "source_url": a.source_url,
        "created_at": a.created_at.isoformat(),
    }


async def seed_agents():
    """Insere presets ausentes (idempotente por nome)."""
    async with Session() as s:
        existing = {
            row[0]
            for row in (await s.execute(select(models.Agent.name))).all()
        }
        added = False
        for preset in AGENT_PRESETS:
            if preset["name"] in existing:
                continue
            s.add(models.Agent(
                name=preset["name"],
                description=preset["description"],
                source="preset",
            ))
            added = True
        if added:
            await s.commit()


async def list_agents() -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(
            select(models.Agent).order_by(models.Agent.created_at.desc())
        )).scalars().all()
        return [_agent(a) for a in rows]


async def get_agent(agent_id: str) -> dict | None:
    async with Session() as s:
        a = await s.get(models.Agent, agent_id)
        return _agent(a) if a else None


async def create_agent(payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip()
    if not name:
        raise ValueError("Nome do agente é obrigatório.")
    if not description:
        raise ValueError("Descrição do agente é obrigatória.")
    source = (payload.get("source") or "manual").strip() or "manual"
    source_url = (payload.get("source_url") or "").strip() or None

    async with Session() as s:
        a = models.Agent(
            name=name[:120],
            description=description,
            source=source[:20],
            source_url=source_url[:500] if source_url else None,
        )
        s.add(a)
        await s.commit()
        await s.refresh(a)
        return _agent(a)


async def delete_agent(agent_id: str) -> bool:
    async with Session() as s:
        a = await s.get(models.Agent, agent_id)
        if not a:
            return False
        await s.delete(a)
        await s.commit()
        return True


async def create_conversation(payload: dict) -> str:
    goal = payload.get("goal") or ""
    async with Session() as s:
        conv = models.Conversation(
            title=payload.get("title") or "Uma nova conversa",
            goal=goal,
            mode=payload.get("mode") or "sequential",
            max_rounds=int(payload.get("max_rounds") or 3),
            token_budget=int(payload.get("token_budget") or 0),
            config=payload.get("config")
            or {"web": True, "apify": False, "mcp": False, "synthesize": True},
        )
        s.add(conv)
        await s.flush()
        for i, p in enumerate(payload.get("participants", [])):
            s.add(models.Participant(
                conversation_id=conv.id,
                pkey=p["pkey"],
                label=p.get("label", p["pkey"]),
                model=p["model"],
                active=p.get("active", True),
                can_interact=p.get("can_interact", True),
                order_index=i,
                persona=p.get("persona", ""),
            ))
        await s.commit()
        return conv.id


async def list_conversations() -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(
            select(models.Conversation).order_by(models.Conversation.created_at.desc())
        )).scalars().all()
        return [
            {"id": c.id, "title": c.title, "goal": c.goal, "status": c.status,
             "mode": c.mode, "created_at": c.created_at.isoformat()}
            for c in rows
        ]


def _msg(m: "models.Message") -> dict:
    return {
        "id": m.id, "round": m.round, "speaker_key": m.speaker_key,
        "speaker_label": m.speaker_label, "role": m.role, "content": m.content,
        "meta": m.meta, "created_at": m.created_at.isoformat(),
    }


async def _scoreboard(s, cid: str) -> dict:
    rows = (await s.execute(
        select(
            models.UsageEvent.participant_key,
            func.coalesce(func.sum(models.UsageEvent.input_tokens), 0),
            func.coalesce(func.sum(models.UsageEvent.output_tokens), 0),
            func.coalesce(func.sum(models.UsageEvent.cost_usd), 0.0),
            func.coalesce(func.sum(models.UsageEvent.tool_calls), 0),
            func.count(models.UsageEvent.id),
        )
        .where(models.UsageEvent.conversation_id == cid)
        .group_by(models.UsageEvent.participant_key)
    )).all()
    return {
        r[0]: {
            "input_tokens": int(r[1]), "output_tokens": int(r[2]),
            "cost_usd": float(r[3]), "tool_calls": int(r[4]), "turns": int(r[5]),
        }
        for r in rows
    }


async def scoreboard(cid: str) -> dict:
    async with Session() as s:
        return await _scoreboard(s, cid)


def _trace_event(e: models.ExecutionEvent) -> dict:
    return {
        "id": e.id,
        "run_index": e.run_index,
        "seq": e.seq,
        "type": e.type,
        "payload": e.payload,
        "created_at": e.created_at.isoformat(),
    }


async def next_run_index(cid: str) -> int:
    async with Session() as s:
        row = (await s.execute(
            select(func.coalesce(func.max(models.ExecutionEvent.run_index), 0))
            .where(models.ExecutionEvent.conversation_id == cid)
        )).scalar_one()
        return int(row) + 1


async def save_execution_event(cid: str, run_index: int, type_: str, payload: dict) -> dict:
    async with Session() as s:
        row = (await s.execute(
            select(func.coalesce(func.max(models.ExecutionEvent.seq), 0))
            .where(models.ExecutionEvent.conversation_id == cid)
        )).scalar_one()
        seq = int(row) + 1
        e = models.ExecutionEvent(
            conversation_id=cid,
            run_index=run_index,
            seq=seq,
            type=type_,
            payload=payload,
        )
        s.add(e)
        await s.commit()
        await s.refresh(e)
        return _trace_event(e)


async def get_execution_trace(cid: str) -> list[dict]:
    async with Session() as s:
        rows = (await s.execute(
            select(models.ExecutionEvent)
            .where(models.ExecutionEvent.conversation_id == cid)
            .order_by(models.ExecutionEvent.seq)
        )).scalars().all()
        return [_trace_event(e) for e in rows]


async def get_conversation_full(cid: str) -> dict | None:
    async with Session() as s:
        c = await s.get(models.Conversation, cid)
        if not c:
            return None
        parts = (await s.execute(
            select(models.Participant)
            .where(models.Participant.conversation_id == cid)
            .order_by(models.Participant.order_index)
        )).scalars().all()
        msgs = (await s.execute(
            select(models.Message)
            .where(models.Message.conversation_id == cid)
            .order_by(models.Message.created_at)
        )).scalars().all()
        trace_rows = (await s.execute(
            select(models.ExecutionEvent)
            .where(models.ExecutionEvent.conversation_id == cid)
            .order_by(models.ExecutionEvent.seq)
        )).scalars().all()
        return {
            "id": c.id, "title": c.title, "goal": c.goal, "mode": c.mode,
            "max_rounds": c.max_rounds, "token_budget": c.token_budget,
            "status": c.status, "config": c.config,
            "participants": [
                {"pkey": p.pkey, "label": p.label, "model": p.model, "active": p.active,
                 "can_interact": p.can_interact, "persona": p.persona,
                 "order_index": p.order_index}
                for p in parts
            ],
            "messages": [_msg(m) for m in msgs],
            "scoreboard": await _scoreboard(s, cid),
            "trace": [_trace_event(e) for e in trace_rows],
        }


async def save_message(cid, rnd, key, label, role, content, meta=None) -> dict:
    async with Session() as s:
        m = models.Message(
            conversation_id=cid, round=rnd, speaker_key=key, speaker_label=label,
            role=role, content=content, meta=meta or {},
        )
        s.add(m)
        await s.commit()
        return _msg(m)


async def save_usage(cid, key, rnd, in_tok, out_tok, cost, tool_calls):
    async with Session() as s:
        s.add(models.UsageEvent(
            conversation_id=cid, participant_key=key, round=rnd,
            input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost, tool_calls=tool_calls,
        ))
        await s.commit()


async def set_status(cid: str, status: str):
    async with Session() as s:
        c = await s.get(models.Conversation, cid)
        if c:
            c.status = status
            await s.commit()


async def update_title(cid: str, title: str) -> bool:
    async with Session() as s:
        c = await s.get(models.Conversation, cid)
        if not c:
            return False
        c.title = (title or "Uma nova conversa")[:200]
        await s.commit()
        return True
