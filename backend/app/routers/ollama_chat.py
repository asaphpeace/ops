"""Interactive chat with the local Ollama model, extending the advisory-only
supervisor (services/ollama_supervisor.py) with a real conversational
surface. Retrieval is deterministic (services/ollama_context.py) — the model
never searches raw data itself, same philosophy as the supervisor.

Streaming mechanics: FastAPI's Depends(get_db) session is torn down as soon
as the endpoint function returns its response object, BEFORE the
StreamingResponse's generator body actually runs (Starlette streams the body
afterward). So all DB work needed before the model call (context retrieval,
persisting the user message) happens synchronously inside the endpoint using
the injected `db`; the generator's own post-stream writes (the assistant
message, the call-log row) open a fresh AsyncSessionLocal() instead — the
same "own short-lived session" pattern already established in
services/ollama_metrics.py.
"""
import json
import logging
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models.ollama_call_log import OllamaCallLog
from app.models.ollama_conversation import OllamaConversation, OllamaMessage
from app.services.ollama_context import assemble_context
from app.services.ollama_domain import DOMAIN_CONTEXT
from app.services.ollama_index import rebuild_search_index
from app.services.ollama_metrics import log_ollama_call
from app.services.time_windows import window_start

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ollama-chat", tags=["ollama-chat"])

_MAX_HISTORY_MESSAGES = 6

# Always sent as the first system message, on every turn — previously the
# model got NO framing at all unless assemble_context() happened to match a
# real ref/customer/keyword (confirmed live: most general questions got
# nothing but bare chat history, so the model had no idea it was Sedna Ops,
# what DSD/VMS mean, or that this is Dataloy VMS/maritime domain). Domain
# facts live in ollama_domain.DOMAIN_CONTEXT, shared with the supervisor
# narration prompts (ollama_supervisor.py) so the two can't drift; only the
# chat-specific role/instruction framing lives here.
_SYSTEM_PROMPT = (
    "You are the assistant embedded in Sedna Ops. " + DOMAIN_CONTEXT + "\n\n"
    "You are talking to one of the app's own support engineers, not an end customer — "
    "usually Asaph.\n\n"
    "Use the real data context given to you below when it's relevant to the question; "
    "say plainly when you don't have enough real data to answer instead of guessing. "
    "Keep answers concise and practical — this is a working tool, not a chat companion."
)


def _enrich_conversation(c: OllamaConversation) -> dict:
    return {"id": c.id, "title": c.title, "created_at": c.created_at, "updated_at": c.updated_at}


def _enrich_message(m: OllamaMessage) -> dict:
    return {"id": m.id, "role": m.role, "content": m.content, "model_used": m.model_used, "created_at": m.created_at}


def _enrich_call_log(c: OllamaCallLog) -> dict:
    return {
        "id": c.id, "purpose": c.purpose, "model_used": c.model_used, "success": c.success,
        "error_message": c.error_message, "duration_ms": c.duration_ms,
        "prompt_eval_count": c.prompt_eval_count, "eval_count": c.eval_count,
        "created_at": c.created_at,
    }


@router.get("/status")
async def get_status():
    return {"enabled": settings.ollama_enabled, "model": settings.ollama_model, "base_url": settings.ollama_base_url}


@router.post("/conversations")
async def create_conversation(db: AsyncSession = Depends(get_db)):
    conv = OllamaConversation(title="New conversation")
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return _enrich_conversation(conv)


@router.get("/conversations")
async def list_conversations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OllamaConversation).order_by(OllamaConversation.updated_at.desc()))
    return [_enrich_conversation(c) for c in result.scalars().all()]


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(conversation_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OllamaMessage).where(OllamaMessage.conversation_id == conversation_id).order_by(OllamaMessage.created_at)
    )
    return [_enrich_message(m) for m in result.scalars().all()]


@router.post("/conversations/{conversation_id}/messages")
async def send_message(conversation_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    if not settings.ollama_enabled:
        raise HTTPException(status_code=503, detail="Ollama not configured (OLLAMA_BASE_URL unset)")

    content = str(data.get("content", "")).strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is required")

    conversation = (
        await db.execute(select(OllamaConversation).where(OllamaConversation.id == conversation_id))
    ).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    prior_messages = (
        await db.execute(
            select(OllamaMessage)
            .where(OllamaMessage.conversation_id == conversation_id)
            .order_by(OllamaMessage.created_at)
        )
    ).scalars().all()

    is_first_message = not prior_messages
    if is_first_message:
        conversation.title = content[:60]

    db.add(OllamaMessage(conversation_id=conversation_id, role="user", content=content))
    conversation.updated_at = datetime.utcnow()
    await db.commit()

    # Deterministic retrieval — the model never searches raw data itself.
    context_text, context_meta = await assemble_context(content, db)

    model_messages: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if context_text:
        model_messages.append({
            "role": "system",
            "content": (
                "Relevant context from the app's real data (cases, comments, bugs, upgrades, "
                "migrations, releases, incidents, ops notes). Use it if it's relevant to the "
                "question; ignore it if it isn't.\n\n" + context_text
            ),
        })
    for m in list(prior_messages)[-_MAX_HISTORY_MESSAGES:]:
        model_messages.append({"role": m.role, "content": m.content})
    model_messages.append({"role": "user", "content": content})

    context_used_json = json.dumps(context_meta)

    async def _stream():
        start = time.monotonic()
        full_text = ""
        prompt_eval_count: int | None = None
        eval_count: int | None = None
        error: str | None = None
        try:
            async with httpx.AsyncClient(timeout=settings.ollama_chat_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": settings.ollama_model,
                        "messages": model_messages,
                        "stream": True,
                        "think": False,
                        "options": {"num_ctx": settings.ollama_chat_num_ctx},
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        delta = chunk.get("message", {}).get("content", "")
                        if delta:
                            full_text += delta
                            yield f"data: {json.dumps({'delta': delta})}\n\n"
                        if chunk.get("done"):
                            prompt_eval_count = chunk.get("prompt_eval_count")
                            eval_count = chunk.get("eval_count")
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as exc:
            logger.error("Ollama chat stream failed: %s", exc)
            error = str(exc)
            yield f"data: {json.dumps({'error': error})}\n\n"
        finally:
            duration_ms = int((time.monotonic() - start) * 1000)
            if full_text:
                async with AsyncSessionLocal() as log_db:
                    log_db.add(OllamaMessage(
                        conversation_id=conversation_id, role="assistant",
                        content=full_text, context_used=context_used_json,
                        model_used=settings.ollama_model,
                    ))
                    conv = await log_db.get(OllamaConversation, conversation_id)
                    if conv:
                        conv.updated_at = datetime.utcnow()
                    await log_db.commit()
            await log_ollama_call(
                purpose="chat", model_used=settings.ollama_model, success=error is None and bool(full_text),
                duration_ms=duration_ms, prompt_eval_count=prompt_eval_count, eval_count=eval_count,
                error_message=error, conversation_id=conversation_id,
            )

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/conversations/{conversation_id}/escalate")
async def escalate_conversation(conversation_id: int, db: AsyncSession = Depends(get_db)):
    """Hands the conversation over to Claude (this app already has a
    configured Anthropic API key for AI summaries — see services/digest.py)
    when the local model's answer isn't good enough. Not streamed (Claude
    is fast enough that the non-streaming _haiku()-style call shape is
    simpler and sufficient — no need for a second SSE pipeline); the reply
    is appended to the SAME conversation, tagged model_used="claude-haiku-4-5"
    so the UI can show which model actually answered. Reuses the exact same
    deterministic retrieval (assemble_context) as the normal Ollama path —
    Claude gets the same real app-data grounding, not a blanker slate."""
    from app.services.digest import CLAUDE_HANDOVER_MODEL, claude_chat_reply

    if not settings.ai_enabled:
        raise HTTPException(status_code=503, detail="Claude not configured (ANTHROPIC_API_KEY unset)")

    conversation = (
        await db.execute(select(OllamaConversation).where(OllamaConversation.id == conversation_id))
    ).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    prior_messages = (
        await db.execute(
            select(OllamaMessage)
            .where(OllamaMessage.conversation_id == conversation_id)
            .order_by(OllamaMessage.created_at)
        )
    ).scalars().all()
    if not prior_messages:
        raise HTTPException(status_code=400, detail="Nothing to escalate — send a message first")

    last_user_message = next((m for m in reversed(prior_messages) if m.role == "user"), None)
    context_text, context_meta = (
        await assemble_context(last_user_message.content, db) if last_user_message else ("", {"path": "none"})
    )

    claude_messages = [{"role": m.role, "content": m.content} for m in prior_messages]
    system_prompt = _SYSTEM_PROMPT + (
        (
            "\n\nRelevant context from the app's real data (cases, comments, bugs, upgrades, migrations, "
            "releases, incidents, ops notes). Use it if it's relevant to the question; ignore it if it "
            "isn't.\n\n" + context_text
        )
        if context_text else ""
    )

    start = time.monotonic()
    reply = await claude_chat_reply(claude_messages, system=system_prompt)
    duration_ms = int((time.monotonic() - start) * 1000)

    await log_ollama_call(
        purpose="claude_escalation", model_used=CLAUDE_HANDOVER_MODEL, success=reply is not None,
        duration_ms=duration_ms, conversation_id=conversation_id,
        error_message=None if reply else "Claude call failed or AI disabled",
    )

    if not reply:
        raise HTTPException(status_code=502, detail="Claude call failed — check ANTHROPIC_API_KEY and try again")

    message = OllamaMessage(
        conversation_id=conversation_id, role="assistant", content=reply,
        context_used=json.dumps(context_meta), model_used=CLAUDE_HANDOVER_MODEL,
    )
    db.add(message)
    conversation.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(message)
    return _enrich_message(message)


@router.get("/metrics")
async def get_metrics(window: str = "week", db: AsyncSession = Depends(get_db)):
    start = window_start(window)
    result = await db.execute(select(OllamaCallLog).where(OllamaCallLog.created_at >= start))
    calls = result.scalars().all()

    total_calls = len(calls)
    durations = [c.duration_ms for c in calls if c.duration_ms is not None]
    successes = [c for c in calls if c.success]
    purpose_breakdown: dict[str, int] = {}
    for c in calls:
        purpose_breakdown[c.purpose] = purpose_breakdown.get(c.purpose, 0) + 1

    return {
        "total_calls": total_calls,
        "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
        "success_rate": round(len(successes) / total_calls, 3) if total_calls else None,
        "last_call_at": max((c.created_at for c in calls), default=None),
        "purpose_breakdown": purpose_breakdown,
    }


@router.get("/recent-calls")
async def get_recent_calls(limit: int = 20, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(OllamaCallLog).order_by(OllamaCallLog.created_at.desc()).limit(limit))
    return [_enrich_call_log(c) for c in result.scalars().all()]


@router.post("/reindex")
async def reindex(db: AsyncSession = Depends(get_db)):
    """Manually triggers a full content-index rebuild right now — the
    scheduled job runs every 30min, but a manual test/verify shouldn't have
    to wait for the next tick (same reasoning as ai_observations' recompute)."""
    total = await rebuild_search_index(db)
    return {"indexed": total}
