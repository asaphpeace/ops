"""Chat retrieval — "digest the app" without vector embeddings. Same
philosophy as the Ollama supervisor (observation_signals.py): all finding is
deterministic Python/SQL, the model only ever answers from an already-
bounded, already-correct context bundle, never asked to search raw data
itself.

A small set of always-current "live facts" (latest VMS version, open
incident/active upgrade counts — see _live_facts_bundle) is prepended
ahead of every path below; confirmed live that without this, a plain
"what's the latest VMS version"-style question had no path to the real
answer at all (see decision order). Then, first match wins:
  1. A real DSD-*/VMS-* ref in the message -> pull that entity's real
     structured record + related data directly.
  2. A real customer name (exact-normalized match, same as everywhere else
     in this app) -> pull that customer's commercial/health data + open
     cases + migration + ops notes.
  3. A greeting/chit-chat message with no real content (see
     _is_low_information) -> skip fulltext, live facts alone are enough.
  4. Otherwise -> Postgres full-text search over ollama_search_index
     (services/ollama_index.py keeps this rebuilt every ~30 min).

Bounded to ~3000 characters total so prompts stay well inside
settings.ollama_chat_num_ctx alongside the system framing, prior turns, and
the new message.
"""
import re

from sqlalchemy import func, select, text
from sqlalchemy.orm import joinedload

from app.models.case import Case
from app.models.case_comment import CaseComment
from app.models.customer import Customer
from app.models.incident import Incident
from app.models.migration_project import MigrationProject
from app.models.ops_note import OpsNote
from app.models.release import Release
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug

_MAX_CONTEXT_CHARS = 3000
_MAX_SNIPPET_CHARS = 400
_MAX_COMMENTS = 6
_MAX_OPEN_CASES = 5
_MAX_FULLTEXT_ROWS = 8
# Safety cap only — ts_headline's own MaxFragments/MaxWords options (below)
# do the real bounding. Bigger than _MAX_SNIPPET_CHARS since a 3-fragment
# headline (~150 words) can legitimately run to several hundred chars.
_MAX_HEADLINE_CHARS = 700

_REF_PATTERN = re.compile(r"\b(DSD|VMS)-\d+\b", re.IGNORECASE)

# Confirmed live: a plain question like "what's the latest VMS version"
# has no DSD-/VMS- ref and no customer name, so it fell to
# _fulltext_fallback below — which has no concept of "latest" and can
# rank a stale answer from an old support comment (e.g. a 2024 reply
# saying "the latest version is 8.29") above the real current Release row,
# or above nothing useful at all. These few facts are cheap to compute and
# always correct, so they're injected into every context bundle
# regardless of which retrieval path fires — the same "give the model an
# already-correct answer, never make it guess" philosophy as everything
# else in this module.
async def _live_facts_bundle(db) -> list[str]:
    parts: list[str] = []
    latest = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    if latest:
        parts.append(f"Current live fact: the latest released VMS version is {latest.version} (released {latest.released_at}).")
    open_incidents = (
        await db.execute(select(func.count()).select_from(Incident).where(Incident.status == "Open"))
    ).scalar_one()
    parts.append(f"Current live fact: {open_incidents} open product/platform incident(s) right now.")
    active_upgrades = (
        await db.execute(
            select(func.count()).select_from(Upgrade).where(Upgrade.stage.notin_(("Verified Done", "Cancelled")))
        )
    ).scalar_one()
    parts.append(f"Current live fact: {active_upgrades} upgrade(s) currently active in the pipeline.")
    return parts


# Greetings/chit-chat carry almost no real vocabulary, so plainto_tsquery
# still returns *something* (ts_rank is never truly zero) — confirmed live
# "hi" matched real case-comment/ops-note rows at a rank indistinguishable
# from a genuinely relevant match on a real query, so a numeric rank floor
# can't reliably tell the two apart. Skipping fulltext outright for
# messages this short/content-free is simpler and avoids feeding the model
# arbitrary unrelated snippets it might mistake for real grounding.
_CHITCHAT_WORDS = {"hi", "hello", "hey", "yo", "sup", "thanks", "thank", "ok", "okay", "cool", "great", "nice", "cheers"}


def _is_low_information(message: str) -> bool:
    words = re.findall(r"[a-zA-Z']+", message.lower())
    return bool(words) and len(words) <= 2 and all(w in _CHITCHAT_WORDS for w in words)


def _truncate(s: str, n: int = _MAX_SNIPPET_CHARS) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n].rstrip() + "…"


def _cap(parts: list[str]) -> str:
    """Join in order, dropping from the end (lowest-priority pieces —
    comments/notes — are appended last by every bundle builder below) once
    the hard character cap would be exceeded."""
    out: list[str] = []
    total = 0
    for p in parts:
        if total + len(p) + 1 > _MAX_CONTEXT_CHARS:
            break
        out.append(p)
        total += len(p) + 1
    return "\n".join(out)


async def _case_bundle(db, case: Case) -> list[str]:
    parts = [
        f"Case {case.jira_ref}: \"{case.title}\" — status={case.status}, priority={case.priority}, "
        f"customer={case.customer.name if case.customer else 'unknown'}, days_open={case.days_open}."
    ]
    if case.resolution_note:
        parts.append(f"Resolution note: {_truncate(case.resolution_note)}")
    if case.rovo_context:
        parts.append(f"Pasted context: {_truncate(case.rovo_context)}")
    if case.linked_vms_ref:
        parts.append(f"Linked bug: {case.linked_vms_ref}")

    notes = (await db.execute(select(OpsNote).where(OpsNote.jira_ref == case.jira_ref))).scalars().all()
    for n in notes:
        parts.append(f"Ops note: {_truncate(n.text)}")

    comments = (
        await db.execute(
            select(CaseComment)
            .where(CaseComment.jira_ref == case.jira_ref)
            .order_by(CaseComment.created.desc())
            .limit(_MAX_COMMENTS)
        )
    ).scalars().all()
    for c in reversed(comments):
        parts.append(f"Comment ({c.author}): {_truncate(c.text)}")

    return parts


async def _bug_bundle(db, bug: VmsBug) -> list[str]:
    from app.services.bug_linkage import cases_by_bug_ref

    parts = [
        f"VMS bug {bug.jira_ref}: status={bug.status}, fix_version={bug.fix_version}, "
        f"sprint={bug.sprint_name}, assignee={bug.assignee}."
    ]
    if bug.ai_summary:
        parts.append(f"Existing AI summary: {_truncate(bug.ai_summary)}")
    if bug.rovo_context:
        parts.append(f"Pasted context: {_truncate(bug.rovo_context)}")

    linked = (await cases_by_bug_ref(db, {bug.jira_ref})).get(bug.jira_ref, [])
    if linked:
        refs = ", ".join(f"{c.jira_ref} ({c.customer.name if c.customer else '?'})" for c in linked[:8])
        parts.append(f"Linked cases: {refs}")

    return parts


async def _customer_bundle(db, customer: Customer) -> list[str]:
    parts = [
        f"Customer {customer.name}: tier={customer.tier}, health_score={customer.health_score}, "
        f"churn_risk={customer.churn_risk}, product={customer.product}."
    ]

    migration = (
        await db.execute(select(MigrationProject).where(MigrationProject.customer_id == customer.id))
    ).scalar_one_or_none()
    if migration:
        parts.append(f"Migration: stage={migration.stage}, stalled={migration.stalled}.")

    notes = (await db.execute(select(OpsNote).where(OpsNote.customer_id == customer.id))).scalars().all()
    for n in notes:
        parts.append(f"Ops note: {_truncate(n.text)}")

    open_cases = (
        await db.execute(
            select(Case)
            .where(Case.customer_id == customer.id, Case.status != "Closed")
            .order_by(Case.days_open.desc())
            .limit(_MAX_OPEN_CASES)
        )
    ).scalars().all()
    for c in open_cases:
        parts.append(f"Open case {c.jira_ref}: \"{c.title}\" ({c.days_open}d open, priority={c.priority}).")

    return parts


async def _entity_ref_lookup(db, ref: str) -> tuple[list[str], dict] | None:
    ref = ref.upper()
    if ref.startswith("DSD-"):
        case = (
            await db.execute(select(Case).where(Case.jira_ref == ref).options(joinedload(Case.customer)))
        ).scalar_one_or_none()
        if not case:
            from app.services.jira import ensure_case_synced

            synced = await ensure_case_synced(db, ref)
            if synced:
                case = (
                    await db.execute(
                        select(Case).where(Case.id == synced.id).options(joinedload(Case.customer))
                    )
                ).scalar_one()
        if not case:
            return None
        return await _case_bundle(db, case), {"path": "entity_case", "refs": [ref]}

    if ref.startswith("VMS-"):
        bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == ref))).scalar_one_or_none()
        if not bug:
            return None
        return await _bug_bundle(db, bug), {"path": "entity_bug", "refs": [ref]}

    return None


async def _customer_name_lookup(db, message: str) -> tuple[list[str], dict] | None:
    from app.services.jira import _normalize_company_name

    normalized_message = _normalize_company_name(message)
    if not normalized_message:
        return None

    customers = (await db.execute(select(Customer))).scalars().all()
    for c in customers:
        normalized_name = _normalize_company_name(c.name)
        # Guard against very short normalized names (e.g. a two-letter
        # abbreviation) matching common words inside an unrelated sentence.
        if len(normalized_name) >= 4 and normalized_name in normalized_message:
            return await _customer_bundle(db, c), {"path": "entity_customer", "refs": [c.name]}
    return None


async def _fulltext_fallback(db, message: str) -> tuple[list[str], dict]:
    """Postgres full-text search over ollama_search_index, ranked by
    ts_rank on the pre-computed content_tsv (cheap — that's what the GIN
    index is for). The excerpt shown is built with ts_headline(), NOT a
    blind first-N-chars truncation — confirmed live this matters: some
    indexed content (whole-channel Slack pastes in ops_notes) runs to
    100K+ characters in a single row, so truncating to the start of the
    document almost never shows the part that actually matched the query.
    ts_headline() extracts fragments centered on the real matching terms
    instead, re-running only against the already-ranked top _MAX_FULLTEXT_ROWS
    rows, not the whole table."""
    rows = (
        await db.execute(
            text(
                "SELECT source_type, source_ref, "
                "ts_headline('english', content, plainto_tsquery('english', :q), "
                "'MaxFragments=3, MaxWords=50, MinWords=15, FragmentDelimiter= ... ') AS excerpt, "
                "ts_rank(content_tsv, plainto_tsquery('english', :q)) AS rank "
                "FROM ollama_search_index "
                "WHERE content_tsv @@ plainto_tsquery('english', :q) "
                "ORDER BY rank DESC LIMIT :limit"
            ),
            {"q": message, "limit": _MAX_FULLTEXT_ROWS},
        )
    ).all()
    # ts_headline's default StartSel/StopSel are literal "<b>"/"</b>" markers
    # (its options string rejects empty values for these, confirmed live) —
    # stripped here rather than fought in SQL, since this text is going
    # straight into a plain-text LLM prompt, never rendered as HTML.
    def _strip_markers(s: str) -> str:
        return s.replace("<b>", "").replace("</b>", "")

    parts = [f"[{r.source_type} {r.source_ref}] {_truncate(_strip_markers(r.excerpt), _MAX_HEADLINE_CHARS)}" for r in rows]
    return parts, {"path": "fulltext" if parts else "none", "refs": [r.source_ref for r in rows]}


async def assemble_context(message: str, db) -> tuple[str, dict]:
    """Returns (context_text, meta). meta is stored verbatim in
    OllamaMessage.context_used for debugging — never shown in the UI by
    default.

    `live_facts` (see above) is prepended ahead of every path below —
    entity/customer lookups return a specific record, but a handful of
    cheap "state of the world" facts are relevant background for almost
    any question and cost three trivial count/lookup queries regardless."""
    live_facts = await _live_facts_bundle(db)

    ref_match = _REF_PATTERN.search(message)
    if ref_match:
        result = await _entity_ref_lookup(db, ref_match.group(0))
        if result:
            parts, meta = result
            return _cap(live_facts + parts), meta

    customer_result = await _customer_name_lookup(db, message)
    if customer_result:
        parts, meta = customer_result
        return _cap(live_facts + parts), meta

    if _is_low_information(message):
        return _cap(live_facts), {"path": "live_facts_only", "refs": []}

    parts, meta = await _fulltext_fallback(db, message)
    return _cap(live_facts + parts), meta
