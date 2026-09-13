"""Local Ollama supervisor — advisory-only "connecting layer" over the
already-computed deterministic signals in observation_signals.py.

The model NEVER discovers a connection itself — all joining (which case's
linked bug is Done while the case stays open, which customer is hit by 2+
unrelated flags at once) happens in plain Python before the model ever sees
anything. Ollama's only job is writing one short human-readable sentence per
already-correct bundle of facts, one candidate at a time (confirmed live: a
batched "narrate this whole array" request made the local model just echo
its input back instead of transforming it — see narrate_fixed_but_open()).
This mirrors digest.py's own established philosophy (deterministic template
first, AI is optional prose on top) and is the main reason this is safe to
trust from a small local model — there's no batch of refs for it to
mismatch or invent, since each call is already scoped to one known-real
candidate.

Never mutates Case/Upgrade/Customer/Incident data — this module's only
write target is its own AiObservation table.
"""
import json
import logging
import time
from datetime import datetime

import httpx
from sqlalchemy import select

from app.config import settings
from app.models.ai_observation import AiObservation
from app.services.ollama_domain import DOMAIN_CONTEXT
from app.services.ollama_metrics import log_ollama_call

logger = logging.getLogger(__name__)

def _fixed_but_open_prompt(c: dict) -> str:
    notes = c.get("ops_notes") or []
    notes_text = f" Known human context: {'; '.join(notes)}." if notes else ""
    return (
        f"A support ticket {c['jira_ref']} for customer {c['customer_name']} has been open "
        f"{c['days_open']} days, but the underlying bug {c['vms_ref']} was already fixed in "
        f"version {c['fix_version']}.{notes_text} Write ONE short sentence saying what should "
        "happen next (e.g. close the ticket, or tell the customer the fix already shipped). "
        'Reply with ONLY this exact JSON object, nothing else: {"summary": "your sentence here"}'
    )


def _cross_signal_prompt(c: dict) -> str:
    signals_text = "; ".join(f"{s['type']}: {s['detail']}" for s in c["signals"])
    return (
        f"Customer {c['customer_name']} has been flagged by multiple different signals at "
        f"once: {signals_text}. Write ONE short sentence connecting these into a single, "
        "useful observation for a support engineer. "
        'Reply with ONLY this exact JSON object, nothing else: {"summary": "your sentence here"}'
    )


def _migration_priority_prompt(c: dict) -> str:
    incidents_text = (
        f"{len(c['open_incident_remediations'])} open incident(s) they still need to be cleared on "
        f"(e.g. {c['open_incident_remediations'][0]['title']})"
        if c["open_incident_remediations"] else "no open incidents"
    )
    return (
        f"Customer {c['customer_name']} ({c['customer_tier']} tier) is on {c['infra']} infrastructure, "
        f"currently version {c['current_version']} (latest is {c['latest_version']}), migration stage "
        f"'{c['migration_stage']}', with {c['pending_upgrade_defect_count']} real defect(s) they reported "
        "already fixed and waiting on their upgrade, and has "
        f"{incidents_text}. Write ONE short sentence recommending whether and why to bundle this "
        "customer's migration, upgrade, and incident remediation into one coordinated window. "
        'Reply with ONLY this exact JSON object, nothing else: {"summary": "your sentence here"}'
    )


def _training_priority_prompt(c: dict) -> str:
    top_features = "; ".join(f"{f['title']} ({f['topic_area']})" for f in c["features"][:5])
    return (
        f"Customer {c['customer_name']} ({c['customer_tier']} tier) is on version {c['current_version']}, "
        f"behind the latest {c['latest_version']}. Since their version, {c['feature_count']} real new "
        f"feature(s) shipped, including: {top_features}. Write ONE short sentence recommending whether "
        "and what training this customer likely needs once they upgrade, naming the most relevant topic. "
        'Reply with ONLY this exact JSON object, nothing else: {"summary": "your sentence here"}'
    )

# Confirmed live against the user's real Ollama server: qwen3:4b is a
# "thinking" model whose default context window makes Ollama request an
# enormous KV-cache buffer (~38GB, real OOM at load time) unless explicitly
# capped. 4096 is far more than these short, bounded prompts ever need and
# fixed the OOM in a real test call — not a tuning knob, a load-time
# requirement for this model on this hardware.
_NUM_CTX = 4096


async def _ollama_chat(prompt: str, purpose: str = "supervisor") -> str | None:
    """Mirrors digest.py's _haiku(): checks settings.ollama_enabled, never
    raises past this function, returns None on any failure.

    think=False disables qwen3:4b's reasoning preamble — confirmed live
    this is where nearly all the latency was going: a trivial test prompt
    with thinking on took ~200s and the raw response showed a long hidden
    "thinking" block before a two-word answer; real candidate-list prompts
    exceeded a 600s timeout entirely with thinking on. This is a summarize/
    narrate task (see this module's own docstring — the model is never
    asked to reason its way to a finding, only to phrase an already-correct
    one), so there's nothing for reasoning mode to actually buy here.

    Timeout is still generous (this is a background job, not a request
    path) but far shorter than before now that thinking is off.

    `purpose` is passed straight through to log_ollama_call() — every call
    here is logged to OllamaCallLog (success or failure), the same table
    interactive chat writes to (routers/ollama_chat.py), so the metrics view
    covers both without a second logging path.

    Every call carries DOMAIN_CONTEXT as a system message — previously these
    narration prompts had zero framing (the model didn't know it was
    summarizing Sedna Ops/Dataloy VMS data, only whatever bare facts each
    prompt spelled out inline), the same gap already found and fixed for
    interactive chat. Shared with ollama_chat.py's system prompt so the two
    surfaces can't drift into different vocabulary."""
    if not settings.ollama_enabled:
        return None
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": settings.ollama_model,
                    "messages": [
                        {"role": "system", "content": DOMAIN_CONTEXT},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "think": False,
                    "options": {"num_ctx": _NUM_CTX},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            await log_ollama_call(
                purpose=purpose, model_used=settings.ollama_model, success=True,
                duration_ms=int((time.monotonic() - start) * 1000),
                prompt_eval_count=data.get("prompt_eval_count"), eval_count=data.get("eval_count"),
            )
            return data["message"]["content"]
    except Exception as exc:
        logger.error("Ollama call failed: %s", exc)
        await log_ollama_call(
            purpose=purpose, model_used=settings.ollama_model, success=False,
            duration_ms=int((time.monotonic() - start) * 1000), error_message=str(exc),
        )
        return None


def _parse_summary(raw: str | None) -> str | None:
    """Defensive parse for a single-object response — a small local model
    in JSON mode is syntactically valid but not always shaped as asked
    (confirmed live: sometimes wrapped in a list anyway). Never raises."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ollama returned non-JSON content, discarding")
        return None
    if isinstance(parsed, list):
        parsed = parsed[0] if parsed else None
    if not isinstance(parsed, dict):
        return None
    summary = parsed.get("summary")
    return str(summary) if summary else None


async def narrate_fixed_but_open(candidates: list[dict]) -> list[dict]:
    """One model call PER candidate, not one batched call for all of them —
    confirmed live this matters: asking qwen3:4b to narrate a whole JSON
    array at once (with thinking disabled for speed) made it just echo the
    input straight back instead of writing a summary; a single, simple,
    one-candidate-at-a-time prompt reliably produces a real sentence. This
    also removes any need for a reference-validation guard — each call is
    already scoped to one known-real candidate, so there is no ref for the
    model to invent or mismatch. Returns [{jira_ref, summary}]."""
    out = []
    for c in candidates:
        summary = _parse_summary(await _ollama_chat(_fixed_but_open_prompt(c), purpose="supervisor_fixed_but_open"))
        if summary:
            out.append({"jira_ref": c["jira_ref"], "summary": summary})
    return out


async def narrate_cross_signal(candidates: list[dict]) -> list[dict]:
    """Same one-call-per-candidate shape as narrate_fixed_but_open(), for
    the same confirmed reason. Returns [{customer_name, summary}]."""
    out = []
    for c in candidates:
        summary = _parse_summary(await _ollama_chat(_cross_signal_prompt(c), purpose="supervisor_cross_signal"))
        if summary:
            out.append({"customer_name": c["customer_name"], "summary": summary})
    return out


async def narrate_migration_priority(candidates: list[dict]) -> list[dict]:
    """Same one-call-per-candidate shape as the two functions above, for the
    same confirmed reason. Returns [{customer_id, summary}]."""
    out = []
    for c in candidates:
        summary = _parse_summary(await _ollama_chat(_migration_priority_prompt(c), purpose="supervisor_migration_priority"))
        if summary:
            out.append({"customer_id": c["customer_id"], "summary": summary})
    return out


async def narrate_training_priority(candidates: list[dict]) -> list[dict]:
    """Same one-call-per-candidate shape as the functions above, for the
    same confirmed reason. Returns [{customer_id, summary}]."""
    out = []
    for c in candidates:
        summary = _parse_summary(await _ollama_chat(_training_priority_prompt(c), purpose="supervisor_training_priority"))
        if summary:
            out.append({"customer_id": c["customer_id"], "summary": summary})
    return out


async def _seen_refs(db, kind: str) -> set[str]:
    """Every `refs` string already stored for this kind, REGARDLESS of
    status — including Dismissed. Dismiss means "stop telling me about
    this," not "hide it until the next pass re-invents it" — confirmed
    this is the same shape of bug already found and fixed once this
    session on Jira Mapping's own dismiss flow (JiraUnmatched.dismissed):
    a dismissed finding must never be silently resurrected just because
    the underlying condition still holds two hours later."""
    result = await db.execute(select(AiObservation.refs).where(AiObservation.kind == kind))
    return {row[0] for row in result.all()}


async def run_supervisor_pass(db) -> int:
    """Orchestrates one full pass: compute both candidate sets, drop
    anything already seen (any status, including Dismissed) BEFORE
    narrating — not just before inserting — so a repeat pass never wastes
    a real, slow Ollama call re-narrating a finding it's just going to
    throw away. Returns the count of genuinely new rows created. The only
    write this whole feature ever performs against the database is this
    insert plus the review/dismiss status update in
    routers/ai_observations.py — nothing here touches
    Case/Upgrade/Customer/Incident."""
    from app.services.observation_signals import (
        cross_signal_candidates, fixed_but_open_candidates, migration_priority_candidates,
        training_priority_candidates,
    )

    created = 0

    fixed_but_open = await fixed_but_open_candidates(db)
    seen_refs = await _seen_refs(db, "fixed_but_open")
    new_fixed_but_open = [c for c in fixed_but_open if c["jira_ref"] not in seen_refs]
    for finding in await narrate_fixed_but_open(new_fixed_but_open):
        candidate = next(c for c in new_fixed_but_open if c["jira_ref"] == finding["jira_ref"])
        db.add(AiObservation(
            kind="fixed_but_open", summary=finding["summary"], refs=finding["jira_ref"],
            customer_id=candidate.get("customer_id"), model_used=settings.ollama_model,
            created_at=datetime.utcnow(),
        ))
        created += 1

    cross_signal = await cross_signal_candidates(db)
    seen_names = await _seen_refs(db, "cross_signal")
    new_cross_signal = [c for c in cross_signal if c["customer_name"] not in seen_names]
    for finding in await narrate_cross_signal(new_cross_signal):
        candidate = next(c for c in new_cross_signal if c["customer_name"] == finding["customer_name"])
        db.add(AiObservation(
            kind="cross_signal", summary=finding["summary"], refs=finding["customer_name"],
            customer_id=candidate.get("customer_id"), model_used=settings.ollama_model,
            created_at=datetime.utcnow(),
        ))
        created += 1

    migration_priority = await migration_priority_candidates(db)
    seen_customer_ids = await _seen_refs(db, "migration_priority")
    new_migration_priority = [c for c in migration_priority if str(c["customer_id"]) not in seen_customer_ids]
    for finding in await narrate_migration_priority(new_migration_priority):
        db.add(AiObservation(
            kind="migration_priority", summary=finding["summary"], refs=str(finding["customer_id"]),
            customer_id=finding["customer_id"], model_used=settings.ollama_model,
            created_at=datetime.utcnow(),
        ))
        created += 1

    training_priority = await training_priority_candidates(db)
    seen_training_customer_ids = await _seen_refs(db, "training_priority")
    new_training_priority = [c for c in training_priority if str(c["customer_id"]) not in seen_training_customer_ids]
    for finding in await narrate_training_priority(new_training_priority):
        db.add(AiObservation(
            kind="training_priority", summary=finding["summary"], refs=str(finding["customer_id"]),
            customer_id=finding["customer_id"], model_used=settings.ollama_model,
            created_at=datetime.utcnow(),
        ))
        created += 1

    await db.commit()
    return created
