"""Shared call-log writer for every real Ollama call — the supervisor's
background narration (services/ollama_supervisor.py) and interactive chat
(routers/ollama_chat.py) both write here via one function, so metrics cover
the whole feature from one table. Opens its own short-lived session rather
than requiring a `db` param at every call site — the simplest option, since
it changes zero existing call-site signatures in narrate_fixed_but_open/
narrate_cross_signal/run_supervisor_pass."""
import logging

from app.database import AsyncSessionLocal
from app.models.ollama_call_log import OllamaCallLog

logger = logging.getLogger(__name__)


async def log_ollama_call(
    purpose: str,
    model_used: str,
    success: bool,
    *,
    duration_ms: int | None = None,
    prompt_eval_count: int | None = None,
    eval_count: int | None = None,
    error_message: str | None = None,
    conversation_id: int | None = None,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            db.add(OllamaCallLog(
                purpose=purpose, model_used=model_used, success=success,
                duration_ms=duration_ms, prompt_eval_count=prompt_eval_count, eval_count=eval_count,
                error_message=error_message[:2000] if error_message else None,
                conversation_id=conversation_id,
            ))
            await db.commit()
    except Exception as exc:
        # Never let a logging failure take down the real call it's logging.
        logger.error("Failed to write OllamaCallLog: %s", exc)
