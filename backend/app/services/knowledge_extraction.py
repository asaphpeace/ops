"""Mines real OpsNote content (pasted Slack context) for categorized
institutional knowledge — Trend / System / Process / Procedure / Challenge /
Relationship — using the same local Ollama model as the supervisor.

Unlike the supervisor (observation_signals.py + ollama_supervisor.py), this
IS a genuine discovery task, not narration of an already-computed fact —
there's no deterministic way to pre-find "trends" in a raw Slack scroll.
Mitigated the same way this app always mitigates a small local model's
risk: JSON-mode output, a fixed validated category vocabulary (anything
else is silently dropped), and every stored row traces back to its real
source note so a human can check the original text.

Real notes run well past the model's usable context (confirmed live:
5.7K-35.8K tokens per note, vs. the model's 4096-token num_ctx used here)
— so each note is split into smaller chunks first, and each chunk gets its
own extraction call. A local Ollama server has no concurrency benefit (one
GPU/CPU, one job at a time), so chunks are processed sequentially — a full
backfill over many/large notes is a genuinely slow, one-time cost; steady
state afterward is cheap since only new (never-extracted) notes are
reprocessed.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import select

from app.config import settings
from app.models.knowledge_extract import KnowledgeExtract
from app.models.ops_note import OpsNote
from app.services.ollama_supervisor import _ollama_chat

logger = logging.getLogger(__name__)

_ALLOWED_CATEGORIES = {"Trend", "System", "Process", "Procedure", "Challenge", "Relationship"}

# Chunk boundary — comfortably fits the extraction prompt's instructions +
# a chunk + the model's JSON output inside a 4096-token num_ctx (roughly
# 2200 chars ≈ 550 tokens of source text, generous headroom either side).
_MAX_CHUNK_CHARS = 2200

# Per-note safety cap — a pathological note (or the odd 143K-char whole-
# channel dump already seen live) shouldn't turn one extraction pass into
# an unbounded number of sequential model calls.
_MAX_CHUNKS_PER_NOTE = 40


def _chunk_text(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """Greedily packs lines (not mid-sentence splits) into chunks up to
    max_chars — a single very long line still becomes its own chunk rather
    than being dropped or mid-word-truncated."""
    lines = text.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        line_len = len(line) + 1
        if current and current_len + line_len > max_chars:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks[:_MAX_CHUNKS_PER_NOTE]


def _extraction_prompt(chunk: str, source_label: str | None) -> str:
    """Confirmed live this needs to fight two real failure modes of a small
    model doing genuine extraction: (1) defaulting to "Trend" for almost
    everything regardless of fit (first backfill pass: 62/64 extracts were
    Trend, including things that were plainly a Process/Procedure), and (2)
    literally echoing a category's own definition back as the "summary"
    (confirmed live: two real rows whose summary was verbatim "A recurring
    pattern over time"). Concrete positive examples per category and an
    explicit anti-echo instruction address both; _parse_extracts() below
    adds a second line of defense against (2)."""
    context_line = f' (from "{source_label}")' if source_label else ""
    return (
        f"This is a raw Slack conversation excerpt{context_line}. Read it and identify anything worth "
        "remembering as institutional knowledge — a real, specific fact stated in the text, not a "
        "general description.\n\n"
        "Categories — use the MOST SPECIFIC one that fits; prefer these over Trend whenever they apply:\n"
        '- System: a named system/tool/component mentioned. Example: "Jira Cloud is used for ticket tracking."\n'
        '- Process: how work actually gets done in practice. Example: "Escalations to Gisele go through '
        'email, not Slack."\n'
        '- Procedure: a specific step-by-step rule. Example: "WFC tickets auto-close after a 5-day nudge '
        'then a 48-hour window."\n'
        '- Challenge: a specific pain point or blocker mentioned. Example: "The monthly report has failed '
        'every run since the migration."\n'
        '- Relationship: how a specific person/customer/system/ticket connects to another. Example: "Geir '
        'escalates tickets by email when he needs help."\n'
        '- Trend: ONLY a genuinely recurring pattern observed across multiple instances — NOT a one-off '
        'fact. Example: "Customers have independently reported the same upgrade-delay issue across '
        'several tickets."\n\n'
        "Rules:\n"
        "- Only extract things clearly and specifically stated in the text below — never invent, assume, "
        "or generalize.\n"
        "- Every summary must be a specific fact from the actual text, naming the real people/systems/"
        "tickets/customers involved where present — NEVER write a summary that is just a category's own "
        "definition or description.\n"
        "- If nothing in this excerpt fits any category, return an empty array.\n\n"
        'Reply with ONLY a JSON array, nothing else: [{"category": "Process", "summary": "a specific, '
        'concrete sentence naming what actually happened"}, ...]\n\n'
        f"Text:\n{chunk}"
    )


# Real failure mode confirmed live (see _extraction_prompt's docstring) —
# the model sometimes echoes a category's own one-line definition back as
# the "summary" instead of a real extracted fact. Exact-match guard against
# the literal phrases used in the prompt above.
_CATEGORY_DEFINITION_ECHOES = {
    "a named system/tool/component mentioned",
    "how work actually gets done in practice",
    "a specific step-by-step rule",
    "a specific pain point or blocker mentioned",
    "how a specific person/customer/system/ticket connects to another",
    "a genuinely recurring pattern observed across multiple instances",
    # Older prompt wording, kept so a stray cached/retried call from before
    # this fix still gets caught rather than slipping through.
    "a recurring pattern over time",
    "a named system/component/tool mentioned",
    "how work actually gets done",
    "a specific step-by-step instruction",
    "a pain point or blocker",
    "how people/customers/systems/tickets connect to each other",
}


def _parse_extracts(raw: str | None) -> list[dict]:
    """Defensive parse — drops anything not shaped like {category, summary},
    anything whose category isn't in the fixed vocabulary, and anything
    that's just the category's own definition echoed back (confirmed live
    failure mode, see _extraction_prompt's docstring) — rather than storing
    any of it as-is."""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Knowledge extraction: non-JSON response, discarding")
        return []
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return []
    out = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        category = item.get("category")
        summary = item.get("summary")
        if not (category in _ALLOWED_CATEGORIES and isinstance(summary, str) and summary.strip()):
            continue
        clean = summary.strip()
        if clean.rstrip(".").lower() in _CATEGORY_DEFINITION_ECHOES:
            logger.warning("Knowledge extraction: dropped a category-definition echo (%r)", clean)
            continue
        out.append({"category": category, "summary": clean})
    return out


async def extract_note(db, note: OpsNote) -> int:
    """Chunks one note, runs extraction per chunk, dedupes (exact match on
    normalized summary, both within this run and against what's already
    stored for this note — cheap and sufficient at this scale, no need for
    semantic similarity), inserts new KnowledgeExtract rows, marks the note
    processed. Returns the count of rows created."""
    existing = (
        await db.execute(select(KnowledgeExtract.summary).where(KnowledgeExtract.source_note_id == note.id))
    ).all()
    seen = {row[0].strip().lower() for row in existing}

    created = 0
    for chunk in _chunk_text(note.text):
        raw = await _ollama_chat(_extraction_prompt(chunk, note.source_label), purpose="knowledge_extraction")
        for item in _parse_extracts(raw):
            key = item["summary"].lower()
            if key in seen:
                continue
            seen.add(key)
            db.add(KnowledgeExtract(
                category=item["category"], summary=item["summary"],
                source_note_id=note.id, model_used=settings.ollama_model,
            ))
            created += 1

    note.knowledge_extracted_at = datetime.utcnow()
    await db.commit()
    return created


async def run_knowledge_extraction(db) -> int:
    """Processes every OpsNote not yet extracted. Steady-state cheap (only
    new notes each run); the first pass over existing notes is the real,
    one-time slow cost — see this module's own docstring."""
    notes = (
        await db.execute(select(OpsNote).where(OpsNote.knowledge_extracted_at.is_(None)))
    ).scalars().all()

    total_created = 0
    for note in notes:
        try:
            total_created += await extract_note(db, note)
        except Exception as exc:
            logger.error("Knowledge extraction failed for note %s: %s", note.id, exc)
    return total_created
