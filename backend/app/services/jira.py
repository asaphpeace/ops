"""
Jira REST API v3 client — read-only.

Polls open DSD Support tickets and upserts them into the local cases table.

Ground truth from the real DSD project (checked live, not assumed):
  - Only 6 statuses ever appear: "Waiting for support", "Waiting for customer",
    "Resolved", "Defect / Enhancement submitted", "Critical Defect Submitted",
    "Pending Upgrade" — there is no "Awaiting Dev"/"Awaiting DevOps"/"Requested".
    Dev vs DevOps vs escalated is never in the status field.
  - Priority is "Severity 1"..."Severity 4" (1 = most severe), not
    Blocker/Critical/High/Low.
  - issuetype is uniformly "Support" and labels are usually empty — case_type
    is derived from labels/original-status instead.
  - The real handoff signal is an @mention in an internal (jsdPublic=False)
    Jira comment — except the SLA-breach automation (account "Bernhard
    Hafting") also posts internal comments mentioning the team lead on every
    ticket nearing its SLA (a leftover from when she was the only support
    person), which is noise, not a human decision, and is filtered out.
  - TTFR: the native "Initial Response" SLA field (customfield_10054) is
    populated on 100/100 sampled tickets (74/100 with a completed cycle) —
    authoritative. Its siblings "Time to first response"/"Time to
    resolution"/"Time to done" and "Waiting for Customer" are dead fields
    (0-1/100 populated) — never build on them. TTR stays computed from
    resolutiondate, there is no live native alternative.
  - Customer identity: the "Customer" field (customfield_10047) is populated
    on 82/100 sampled tickets, e.g. {"value": "Stena Rederi|10180"} — the
    trailing number is a Jira-internal picklist option id, NOT a Salesforce
    Account ID (confirmed: different formats, no correlation) — match by
    name only, never by that id.
  - Bug linkage: "Defect / Enhancement submitted" tickets link via native
    issuelinks to the separate VMS project — confirmed link targets are
    always parent-level Bug/Task (never Sub-task) in every sample checked.

Matching strategy:
  - Known jira_ref  → update status, priority, days_open, assignee, mention,
                       TTFR, customer identity, linked VMS bug.
  - Unknown jira_ref → logged (with customer identity) for manual mapping.

Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env to enable.
"""
import asyncio
import logging
import re
import statistics
import time
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.case_comment import CaseComment
from app.models.customer import Customer
from app.models.customer_name_alias import CustomerNameAlias
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.jira_unmatched import JiraUnmatched
from app.models.release import Release
from app.services.lanes import SUPPORT_TEAM as _LANES_SUPPORT_TEAM
from app.models.sso_onboarding import SSOOnboarding
from app.models.training import TrainingGap
from app.models.unmatched_upgrade_customer import UnmatchedUpgradeCustomer
from app.models.upgrade import Upgrade
from app.models.vms_bug import VmsBug
from app.services.lanes import BOT_ACCOUNT_NAME, TEAM_LEAD

logger = logging.getLogger(__name__)

_HEADERS = {"Accept": "application/json"}
_FIELDS = (
    "summary,status,priority,issuetype,labels,assignee,created,resolutiondate,"
    "comment,customfield_10054,customfield_10047,customfield_10014,issuelinks,components"
)

_STATUS_MAP: dict[str, str] = {
    "Waiting for support": "Active",
    "Defect / Enhancement submitted": "Active",
    "Critical Defect Submitted": "Active",
    "Waiting for customer": "Awaiting Customer",
    "Resolved": "Closed",
    "Pending Upgrade": "Closed",
}

# Sub-tasks are never the "real bug" — confirmed live, every DSD->VMS link
# sampled pointed at a parent-level Bug/Task, never a Sub-task.
_VMS_BUG_ISSUE_TYPES = {"Bug", "Task", "Story"}


def _auth() -> httpx.BasicAuth:
    return httpx.BasicAuth(settings.jira_email, settings.jira_api_token)


def _map_status(name: str) -> str:
    return _STATUS_MAP.get(name, "Active")


# Jira Service Desk Request Type value for the "Sys Admin" queue — confirmed
# live via /rest/servicedeskapi/servicedesk/5/queue (queue 46, "Untriaged
# (Sys Admin)"). These tickets initiate the upgrade pipeline but sit at
# ordinary statuses (e.g. "Waiting for support") until much later, so status
# alone can't classify them — Request Type can, from creation.
_SYS_ADMIN_REQUEST_TYPE = "Upgrade or Installation Request"


def _map_type(raw_status: str, labels: list[str], request_type: str | None = None) -> str:
    label_set = {lbl.lower() for lbl in labels}
    # The real, authoritative signal for a defect is the Jira STATUS itself
    # (_DEFECT_STATUSES, already used elsewhere — e.g. support_defect_dev_status())
    # — the "problem" label was the only check here before this fix and is
    # rarely actually applied, confirmed live: only 2 of 156 local cases had
    # case_type="Defect" despite far more real tickets sitting at one of
    # these two statuses (root cause of the "defects" lane showing 0).
    if raw_status in _DEFECT_STATUSES:
        return "Defect"
    if "problem" in label_set:
        return "Defect"
    if "training_archive" in label_set:
        return "Training Gap"
    if request_type == _SYS_ADMIN_REQUEST_TYPE:
        return "Upgrade"
    if raw_status == "Pending Upgrade":
        return "Upgrade"
    return "Support"


def _map_priority(name: str) -> str:
    # Real scheme: Severity 1 (most severe) .. Severity 4 (least severe).
    if name in ("Severity 1", "Severity 2"):
        return "High"
    if name == "Severity 4":
        return "Low"
    return "Medium"


def _days_from_created(created_str: str) -> int:
    try:
        created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        return max(0, (datetime.now(timezone.utc) - created).days)
    except Exception:
        return 0


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_mentions(body: dict) -> list[str]:
    """Walk an Atlassian Document Format comment body for @mention nodes."""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "mention":
                text = node.get("attrs", {}).get("text", "")
                found.append(text.lstrip("@"))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(body)
    return found


def _adf_to_text(body: dict) -> str:
    """Walk an Atlassian Document Format comment body for readable plain
    text — sibling to _extract_mentions() above, same recursive-walk style,
    collecting `type: "text"` node values instead of mention nodes. Inserts
    a blank line at each `type: "paragraph"` boundary so multi-paragraph
    comments don't collapse into one run-on line."""
    lines: list[str] = []
    current: list[str] = []

    def flush():
        if current:
            lines.append("".join(current))
            current.clear()

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "text":
                current.append(node.get("text", ""))
            elif node.get("type") == "paragraph":
                flush()
            for v in node.values():
                walk(v)
            if node.get("type") == "paragraph":
                flush()
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(body)
    flush()
    return "\n".join(lines).strip()


def _last_human_mention(comments: list[dict]) -> tuple[str, datetime] | None:
    """Most recent @mention from a real internal comment, skipping the SLA bot."""
    for c in reversed(comments):
        if c.get("jsdPublic") is not False:
            continue
        if c.get("author", {}).get("displayName") == BOT_ACCOUNT_NAME:
            continue
        mentions = _extract_mentions(c.get("body", {}))
        if mentions:
            created = _parse_dt(c.get("created"))
            if created:
                return mentions[-1], created
    return None


def _first_public_reply_at(comments: list[dict]) -> datetime | None:
    for c in comments:  # embedded field returns oldest-first
        if c.get("jsdPublic") is True:
            return _parse_dt(c.get("created"))
    return None


def _last_reply(comments: list[dict]) -> tuple[str | None, datetime | None]:
    """Who replied most recently, and when — from the same real comment
    history already fetched for mention-extraction/reply-SLA purposes.
    Returns "customer" for the most recent real public (jsdPublic=True)
    comment, or the real display name for an internal one (so the frontend
    can tell YOU vs a teammate apart) — the SLA bot is skipped, same as
    _last_human_mention().

    jsdPublic=True means "visible to the customer," NOT "written by the
    customer" — confirmed live (DSD-31981): a real team member (Gisele
    Wolff, accountType="atlassian") posted a public/customer-visible reply,
    which an earlier version of this function wrongly attributed to
    "customer". Only count a public comment as the customer's when its
    author's accountType is neither "atlassian" (an internal/licensed
    Jira account) nor "app" (an integration/bot). accountType is None for
    comments cached before this distinction existed — falls back to the
    old jsdPublic-only guess in that case rather than mislabeling a known
    account as unknown."""
    for c in reversed(comments):
        author_obj = c.get("author") or {}
        author = author_obj.get("displayName")
        if author == BOT_ACCOUNT_NAME:
            continue
        created = _parse_dt(c.get("created"))
        if not created:
            continue
        if c.get("jsdPublic") is True and author_obj.get("accountType") not in ("atlassian", "app"):
            return "customer", created
        return author, created
    return None, None


async def _tag_resolved_freshness(
    db, client: httpx.AsyncClient, issues: list[dict], window_start: datetime,
) -> dict[str, bool]:
    """For a set of resolved issues (each must carry resolutiondate/created
    fields plus expand=changelog and the comment field), determine per-issue
    whether its last real activity before its own resolving transition falls
    within window_start..now. Shared by team_daily_resolved() (Resolved
    counts) and team_resolved_stats() (TTFR/TTR medians) — both need the
    identical "was this actually worked in the window it's credited to"
    answer, just consumed differently.

    fresh/backlog — a real, live-Jira-anchored answer to "was this ticket
    actually worked on in the window it's being credited to, or did it just
    get closed during it": fresh = the ticket's last real activity (a
    comment, a status/field change, or its own creation if neither ever
    happened) falls within this same window; backlog = the close is real,
    but the ticket was actually last touched before the window started.
    Deliberately NOT a second number the reader has to cross-reference —
    engineers can't game "when did I last comment" the way they can game
    "when did I click resolve," so this tags each ticket at the source.

    The transition that actually resolves the ticket is itself a
    status-change changelog entry timestamped ~the same moment as
    resolutiondate — without excluding it, "last activity" would always
    include the close action itself, making every ticket trivially "fresh"
    by definition (confirmed live: DSD-29015 sat with zero real activity
    from 2025-10-28 to 2026-08-21, a real 297-day stale-then-batch-closed
    ticket, yet its own resolving status change alone would have made it
    look worked-on today). A 5-second buffer before `resolutiondate`
    reliably drops that self-referential entry regardless of millisecond
    ordering, while still counting a genuine comment/status-change made
    shortly before close.

    Skips the comment fetch entirely for tickets CREATED inside the
    window — trivially fresh regardless of any other activity, so there's
    nothing the comment/changelog check could change. Batch-cached for the
    rest via _cached_comments_batch() (a real fetch only for the busy
    minority under the embedded 20-comment cap AND not already cached
    locally costs nothing extra) — same DB-backed cache team_open_stats()
    uses, not just _dedup_fetch's in-memory layer.
    """
    def _needs_comment_fetch(issue: dict) -> bool:
        created = _parse_dt(issue["fields"].get("created"))
        return created is None or created < window_start

    needs_check = [issue for issue in issues if _needs_comment_fetch(issue)]
    comments_by_key = await _cached_comments_batch(db, client, needs_check) if needs_check else {}

    fresh_by_key: dict[str, bool] = {}
    for issue in issues:
        f = issue["fields"]
        resolved = _parse_dt(f.get("resolutiondate"))
        if not resolved:
            continue
        cutoff = resolved - timedelta(seconds=5)
        # `created` is never the resolving action itself, so it's always a
        # legitimate activity marker (and the guaranteed fallback when
        # nothing else qualifies) — not subject to the cutoff filter.
        activity_dates = [d for d in (_parse_dt(f.get("created")),) if d]
        for c in comments_by_key.get(issue["key"], []):
            d = _parse_dt(c.get("created"))
            if d and d <= cutoff:
                activity_dates.append(d)
        for history in issue.get("changelog", {}).get("histories", []):
            d = _parse_dt(history.get("created"))
            if d and d <= cutoff:
                activity_dates.append(d)
        last_activity = max(activity_dates)
        fresh_by_key[issue["key"]] = last_activity >= window_start
    return fresh_by_key


async def _fetch_full_comments(client: httpx.AsyncClient, issue_key: str, embedded: dict | None) -> list[dict]:
    """The `comment` field embedded on a /search result is capped at 20,
    oldest-first — confirmed live: a ticket with 84 total comments only
    returned entries from 9+ months ago, meaning today's actual comments are
    structurally invisible on any ticket busy enough to hit the cap (~17% of
    open DSD tickets, sampled live). For those tickets, fetch the real
    comments from Jira's dedicated per-issue endpoint (newest-first, since
    with only maxResults=50 we want the most recent ones, not the oldest)
    instead — this is the only way to see recent activity on a high-
    comment-count ticket. Cheap/no-op for the ~83% of tickets under the cap.

    ALWAYS returns oldest-first, matching the embedded field's own order —
    confirmed live this was NOT the case before this fix (the re-fetch
    branch returned Jira's raw newest-first order unchanged), a real bug
    that silently inverted every downstream reversed()-based "most recent"
    lookup (_last_human_mention, _first_public_reply_at, _last_reply) for
    any ticket over the 20-comment cap — they'd report the OLDEST of the 50
    fetched comments as if it were the newest. Confirmed on DSD-31779: a
    fresh internal reply from Asaph (18:25) was being reported as the
    "last reply" being an older public comment (18:01) instead."""
    embedded = embedded or {}
    comments = embedded.get("comments", [])
    total = embedded.get("total", len(comments))
    if total <= len(comments):
        return comments
    resp = await client.get(
        f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{issue_key}/comment",
        headers=_HEADERS, params={"orderBy": "-created", "maxResults": 50},
    )
    resp.raise_for_status()
    return list(reversed(resp.json().get("comments", [])))


def _comment_row_to_raw(c: CaseComment) -> dict:
    """Reconstructs the raw Jira comment shape (matching _fetch_full_comments()'s
    own return) from a cached row — safe for every current bulk consumer
    (team_open_stats/_tag_resolved_freshness/etc), which only ever reads
    author.displayName/created/jsdPublic, never body. _adf_to_text() has
    exactly one call site (inside _cached_comments() below, writing the
    cache) — nothing downstream re-parses this reconstructed `body`."""
    return {
        "id": c.jira_comment_id,
        "author": {"displayName": c.author, "accountType": c.author_account_type},
        "created": c.created.isoformat() if c.created else None,
        "body": c.text,
        "jsdPublic": c.public,
    }


async def _cached_comments(
    db, client: httpx.AsyncClient, jira_ref: str, embedded: dict | None, case_id: int | None = None,
) -> list[dict]:
    """Shared DB-backed comment cache, keyed by jira_ref — generalizes the
    'query latest, do nothing if no news' behavior originally built for
    fetch_case_activity()'s Jira Activity tab. SEQUENTIAL USE ONLY — a
    single AsyncSession can't be used concurrently (confirmed live:
    InvalidRequestError under asyncio.gather). fetch_case_activity() calls
    this directly (one ticket, no concurrency); every bulk/multi-ticket
    caller must use _cached_comments_batch() below instead, which never
    touches `db` from more than one coroutine at a time.

    Returns the RAW Jira comment shape, not fetch_case_activity()'s parsed
    {author,created,text,public} entries — see _comment_row_to_raw().
    `case_id`, when known, is stored as a back-reference only; lookup and
    dedup are always by jira_ref, since most tickets processed by the bulk
    functions have no local Case row at all."""
    stored = (await db.execute(
        select(CaseComment).where(CaseComment.jira_ref == jira_ref).order_by(CaseComment.created)
    )).scalars().all()
    embedded = embedded or {}
    total = embedded.get("total", len(embedded.get("comments", [])))
    if total <= len(stored):
        return [_comment_row_to_raw(c) for c in stored]

    full = await _fetch_full_comments(client, jira_ref, embedded)
    existing_ids = {c.jira_comment_id for c in stored}
    for c in full:
        comment_id = c.get("id")
        if not comment_id or comment_id in existing_ids:
            continue
        db.add(CaseComment(
            case_id=case_id, jira_ref=jira_ref, jira_comment_id=comment_id,
            author=(c.get("author") or {}).get("displayName", "Unknown"),
            created=_parse_dt(c.get("created")),
            text=_adf_to_text(c.get("body", {})),
            public=c.get("jsdPublic"),
            author_account_type=(c.get("author") or {}).get("accountType"),
        ))
        existing_ids.add(comment_id)
    await db.commit()
    return full


async def _cached_comments_batch(
    db, client: httpx.AsyncClient, issues: list[dict],
) -> dict[str, list[dict]]:
    """Batch version of _cached_comments() for use inside asyncio.gather()
    — a single AsyncSession can't be used concurrently (confirmed live:
    InvalidRequestError, "This session is provisioning a new connection").
    Does exactly ONE batched DB read up front, runs the real Jira comment
    fetches concurrently for only the tickets that actually need one, then
    ONE batched DB write at the end — `db` is never touched from more than
    one coroutine at a time. Returns {issue_key: [raw comment dicts]}, the
    same per-ticket shape _fetch_full_comments() always returned."""
    keys = [issue["key"] for issue in issues]
    stored_all = (await db.execute(
        select(CaseComment).where(CaseComment.jira_ref.in_(keys)).order_by(CaseComment.created)
    )).scalars().all()
    stored_by_key: dict[str, list[CaseComment]] = {}
    for c in stored_all:
        stored_by_key.setdefault(c.jira_ref, []).append(c)

    needs_fetch: list[dict] = []
    results: dict[str, list[dict]] = {}
    for issue in issues:
        key = issue["key"]
        stored = stored_by_key.get(key, [])
        embedded = issue["fields"].get("comment") or {}
        total = embedded.get("total", len(embedded.get("comments", [])))
        if total <= len(stored):
            results[key] = [_comment_row_to_raw(c) for c in stored]
        else:
            needs_fetch.append(issue)

    if needs_fetch:
        fetched = await asyncio.gather(*(
            _fetch_full_comments(client, issue["key"], issue["fields"].get("comment"))
            for issue in needs_fetch
        ))
        for issue, full in zip(needs_fetch, fetched):
            key = issue["key"]
            results[key] = full
            existing_ids = {c.jira_comment_id for c in stored_by_key.get(key, [])}
            for c in full:
                comment_id = c.get("id")
                if not comment_id or comment_id in existing_ids:
                    continue
                db.add(CaseComment(
                    case_id=None, jira_ref=key, jira_comment_id=comment_id,
                    author=(c.get("author") or {}).get("displayName", "Unknown"),
                    created=_parse_dt(c.get("created")),
                    text=_adf_to_text(c.get("body", {})),
                    public=c.get("jsdPublic"),
                    author_account_type=(c.get("author") or {}).get("accountType"),
                ))
                existing_ids.add(comment_id)
        try:
            await db.commit()
        except IntegrityError:
            # Another concurrent caller (a different session/request) already
            # cached the same ticket's comments and won the race on
            # uq_case_comment_ref — confirmed live under real concurrent load.
            # The rows we tried to add are redundant, not wrong: roll back and
            # move on. `results` is already correct regardless, since it was
            # built from the live Jira fetch above, not from post-commit DB
            # state — this only affects whether *this* call persists the
            # cache, not what it returns.
            await db.rollback()

    return results


def _extract_ttfr(field_value: dict | None) -> tuple[float | None, bool | None]:
    """Native 'Initial Response' SLA field -> (elapsed_hours, breached)."""
    if not field_value:
        return None, None
    cycles = field_value.get("completedCycles") or []
    if not cycles:
        return None, None
    latest = cycles[-1]
    elapsed_ms = (latest.get("elapsedTime") or {}).get("millis")
    if elapsed_ms is None:
        return None, None
    return round(elapsed_ms / 3_600_000, 1), bool(latest.get("breached"))


def _extract_sla_state(field_value: dict | None) -> dict | None:
    """Real, live Initial-Response SLA state for the queue table — distinct
    from _extract_ttfr() above, which only ever reads completedCycles and so
    comes back empty for a ticket that hasn't had its first response yet
    (the common "still waiting" case). Confirmed live (DSD-31977):
    ongoingCycle carries a real remainingTime/breached pair down to the
    minute while the clock is still ticking. Prefers ongoingCycle when
    present (the ticket's current, live state); falls back to the most
    recent completedCycles entry (the clock already finished, response
    already happened) otherwise. None when the field carries neither."""
    if not field_value:
        return None
    ongoing = field_value.get("ongoingCycle")
    if ongoing:
        remaining_ms = (ongoing.get("remainingTime") or {}).get("millis")
        goal_ms = (ongoing.get("goalDuration") or {}).get("millis")
        return {
            "completed": False,
            "breached": bool(ongoing.get("breached")),
            "remaining_minutes": round(remaining_ms / 60_000) if remaining_ms is not None else None,
            "goal_minutes": round(goal_ms / 60_000) if goal_ms is not None else None,
        }
    cycles = field_value.get("completedCycles") or []
    if cycles:
        latest = cycles[-1]
        elapsed_ms = (latest.get("elapsedTime") or {}).get("millis")
        return {
            "completed": True,
            "breached": bool(latest.get("breached")),
            "elapsed_minutes": round(elapsed_ms / 60_000) if elapsed_ms is not None else None,
            "goal_minutes": None,
        }
    return None


def _extract_customer_name(field_value: dict | None) -> str | None:
    """Native 'Customer' picklist -> plain name, stripping Jira's '|<id>' suffix."""
    if not field_value:
        return None
    raw = field_value.get("value", "")
    return raw.split("|")[0].strip() or None


def _extract_request_type(field_value: dict | None) -> str | None:
    """Native Jira Service Desk 'Request Type' picklist -> plain name."""
    if not field_value:
        return None
    return (field_value.get("requestType") or {}).get("name") or None


def _extract_vms_links(issuelinks: list[dict]) -> list[str]:
    # Deduped — Jira can return more than one issuelink entry pointing at the
    # same target key (confirmed live via the DSD- sibling extractor below).
    keys = []
    seen = set()
    for link in issuelinks or []:
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        key = other["key"]
        if key.startswith("VMS-") and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def _extract_related_case_keys(issuelinks: list[dict], self_key: str) -> list[str]:
    """DSD-to-DSD issuelinks (e.g. "Relates") — a real signal that multiple
    customers hit the same underlying issue, confirmed live (DSD-30697
    relates to 6 other DSD tickets) but previously discarded entirely by
    _extract_vms_links()'s VMS-only key filter. Dedupes — confirmed live
    that Jira can return more than one issuelink entry pointing at the same
    target key (different link-type rows), which would otherwise repeat a
    ref in the comma-joined column."""
    keys = []
    seen = set()
    for link in issuelinks or []:
        other = link.get("outwardIssue") or link.get("inwardIssue")
        if not other:
            continue
        key = other["key"]
        if key.startswith("DSD-") and key != self_key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


_VMS_BUG_SYNC_TTL_MINUTES = 15

_VMS_BUG_FIELDS = "issuetype,status,fixVersions,labels,customfield_10010,assignee,created,resolutiondate"


async def _prefetch_vms_bug_fields(client: httpx.AsyncClient, db, vms_refs: set[str]) -> dict[str, dict | None]:
    """Concurrently fetches raw Jira `fields` for every vms_ref that still
    needs a fresh sync (same _VMS_BUG_SYNC_TTL_MINUTES freshness check
    _sync_vms_bug() applies) — pure network I/O, `db` is only ever used for
    ONE batched read here, never touched concurrently (same "batch read,
    concurrent fetch, no concurrent write" shape as _cached_comments_batch()
    below — a single AsyncSession can't be used concurrently). _sync_vms_bug()
    still does every actual DB read/write sequentially, using this dict as
    its data source instead of doing its own live GET. Confirmed live this
    is what collapses what were dozens of sequential live-Jira round-trips
    (the direct cause of poll_and_upsert() routinely taking 3.5-4 minutes,
    against its own 5-minute schedule) into one concurrent batch, with zero
    change to which bugs actually get synced or how."""
    if not vms_refs:
        return {}
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=_VMS_BUG_SYNC_TTL_MINUTES)
    fresh = (
        await db.execute(select(VmsBug.jira_ref).where(VmsBug.jira_ref.in_(vms_refs), VmsBug.last_synced_at >= cutoff))
    ).scalars().all()
    needs_fetch = vms_refs - set(fresh)
    if not needs_fetch:
        return {}

    async def _fetch_one(ref: str) -> tuple[str, dict | None]:
        try:
            resp = await client.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{ref}",
                headers=_HEADERS,
                params={"fields": _VMS_BUG_FIELDS},
            )
            resp.raise_for_status()
            return ref, resp.json().get("fields", {})
        except Exception as exc:
            logger.warning("VMS bug prefetch failed for %s: %s", ref, exc)
            return ref, None

    results = await asyncio.gather(*(_fetch_one(ref) for ref in needs_fetch))
    return dict(results)


async def _sync_vms_bug(
    client: httpx.AsyncClient, db, vms_ref: str, prefetched: dict[str, dict | None] | None = None,
) -> VmsBug | None:
    """Fetch a linked VMS issue and upsert it. Returns None if it's a Sub-task.

    Skips the live Jira call entirely when an existing row was already
    synced within _VMS_BUG_SYNC_TTL_MINUTES — confirmed live this session
    that this was called unconditionally for every linked bug on every
    poll, with no such check at all. That was masked while _fetch_raw()
    only ever saw the top 200 most-recently-updated tickets; now that
    pagination surfaces the real, much larger ticket volume, the same
    handful of frequently-linked bugs (a popular defect many customers hit)
    were getting re-fetched from Jira on every single 5-minute poll cycle
    regardless of whether anything about them had actually changed. Safe to
    skip without re-checking the Sub-task exclusion below — a VmsBug row is
    only ever created after that check already passed once (see the
    early-return further down), so an existing row is guaranteed to be a
    real bug, never a sub-task. The skip check itself is just a cheap,
    indexed local SELECT — it's the live Jira HTTP call this avoids.

    `prefetched`, when given (see _prefetch_vms_bug_fields above), supplies
    the fields dict instead of this function doing its own live GET —
    everything below this point behaves identically either way."""
    existing = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == vms_ref))).scalar_one_or_none()
    if existing and existing.last_synced_at and \
            existing.last_synced_at >= datetime.now(timezone.utc) - timedelta(minutes=_VMS_BUG_SYNC_TTL_MINUTES):
        return existing

    if prefetched is not None and vms_ref in prefetched:
        fields = prefetched[vms_ref]
        if fields is None:
            return None  # the concurrent prefetch already tried and failed for this ref
    else:
        try:
            resp = await client.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{vms_ref}",
                headers=_HEADERS,
                params={"fields": _VMS_BUG_FIELDS},
            )
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("VMS bug fetch failed for %s: %s", vms_ref, exc)
            return None
        fields = resp.json().get("fields", {})
    issue_type = fields.get("issuetype", {}).get("name", "")
    if issue_type not in _VMS_BUG_ISSUE_TYPES:
        return None  # Sub-task or something unexpected — not "the real bug"

    # Reuses the row already fetched by the skip-check above (`existing`)
    # instead of a second, redundant SELECT for the same jira_ref.
    bug = existing
    is_new = bug is None
    if bug is None:
        bug = VmsBug(jira_ref=vms_ref)
        db.add(bug)

    old_status = bug.status if not is_new else None
    old_sprint_name = bug.sprint_name if not is_new else None

    bug.issue_type = issue_type
    bug.status = fields.get("status", {}).get("name", "")
    fix_versions = fields.get("fixVersions") or []
    bug.fix_version = fix_versions[0]["name"] if fix_versions else None
    bug.labels = ",".join(fields.get("labels") or [])

    # Real Jira Software sprint field — can return a single dict or a list
    # (board-scoped); sampled payloads show a single dict, but defend
    # against the list shape by taking the last (most recent) entry.
    sprint = fields.get("customfield_10010")
    if isinstance(sprint, list):
        sprint = sprint[-1] if sprint else None
    bug.sprint_name = sprint.get("name") if sprint else None
    bug.sprint_state = sprint.get("state") if sprint else None
    assignee = fields.get("assignee")
    bug.assignee = assignee.get("displayName") if assignee else None

    bug.jira_created_at = _parse_dt(fields.get("created"))
    bug.jira_resolved_at = _parse_dt(fields.get("resolutiondate"))

    # Lifecycle timeline — no history existed before this was added, so only
    # transitions from here on are ever recorded (not a backfill).
    if not is_new and old_status != bug.status:
        db.add(AuditLog(
            actor="system", action="bug.status_changed", target_type="bug", target_id=vms_ref,
            detail=f"{old_status} -> {bug.status}",
        ))
    if not is_new and old_sprint_name != bug.sprint_name and bug.sprint_name is not None:
        db.add(AuditLog(
            actor="system", action="bug.sprint_changed", target_type="bug", target_id=vms_ref,
            detail=f"{old_sprint_name or 'none'} -> {bug.sprint_name}",
        ))

    bug.last_synced_at = datetime.utcnow()
    return bug


async def _fetch_all_pages(jql: str, fields: str = _FIELDS) -> list[dict]:
    """Shared, fully-paginated JQL fetch for the three regular poll passes
    below. Confirmed live this session: each of the three previously did a
    single unpaginated maxResults=200 request — with real open DSD volume
    at 500+, any ticket that hadn't been touched recently enough to rank in
    the top 200 by "updated DESC" was silently invisible to the regular
    poll forever (no jira_unmatched row, no Case, no Upgrade bridge, no
    matter how real or important) — confirmed concretely on 19 real,
    still-open sys-admin upgrade tickets that had zero trace anywhere in
    this app. Mirrors the exact nextPageToken loop already used everywhere
    else in this file (e.g. team_open_stats's own _fetch_raw)."""
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    issues: list[dict] = []
    page_token: str | None = None
    async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
        while True:
            params = {"jql": jql, "maxResults": 100, "fields": fields}
            if page_token:
                params["nextPageToken"] = page_token
            resp = await client.get(url, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
            issues.extend(data.get("issues", []))
            if data.get("isLast", True):
                break
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return issues


async def _fetch_raw() -> list[dict]:
    jql = 'project = "DSD" AND statusCategory != Done ORDER BY updated DESC'
    return await _fetch_all_pages(jql)


async def _fetch_recently_resolved() -> list[dict]:
    """A ticket that flips to a Done-category status simply stops appearing
    in the open-tickets JQL above — without this second pass, the local
    Case row is never marked resolved and just sits stale at its last-known
    open status forever, which is why resolved-ticket stats/TTR silently
    starved."""
    jql = 'project = "DSD" AND statusCategory = Done AND resolutiondate >= -95d ORDER BY updated DESC'
    return await _fetch_all_pages(jql)


async def _fetch_pending_upgrade() -> list[dict]:
    """Was originally scoped to just status = "Pending Upgrade", which
    carries Jira's own statusCategory=Done but never a resolutiondate
    (confirmed live, 10/10 sampled) — falling in the gap between _fetch_raw
    (excludes it, it IS Done-category) and _fetch_recently_resolved
    (requires resolutiondate, which never exists here). Confirmed live
    this session that "Pending Upgrade" isn't the only status with this
    property — a real ticket (DSD-28935) moved to status "Resolved" with
    resolutiondate still None, falling through all three passes exactly
    the same way and staying invisible to every regular-poll reconciliation
    (including the Upgrade.request_type refresh that depends on the poll
    ever touching a ticket at all). Generalized to catch ANY Done-category
    status missing a resolutiondate, not just this one hardcoded value —
    the function/counter names below keep their original "pending_upgrade"
    label for continuity with existing call sites, but the real scope is
    "Done-category tickets that would otherwise never be reconciled
    again." No date window is used or needed — status-based, not
    date-based, same as _fetch_raw."""
    jql = 'project = "DSD" AND statusCategory = Done AND resolutiondate is EMPTY ORDER BY updated DESC'
    return await _fetch_all_pages(jql)


# Simple in-memory TTL cache for the live team-stats queries below — these
# back a dashboard that gets re-rendered/toggled repeatedly by one user, not
# a real-time feed, so there's no reason to re-hit Jira (and re-page through
# hundreds of issues) on every click or reload. TTL is configurable
# (settings.jira_stats_cache_ttl_seconds, default 3600s/1h) rather than hardcoded
# so it can be tuned without a code change if Jira throttling ever becomes a
# real concern — see _cache_get for how it's applied.
_stats_cache: dict[tuple, tuple[float, dict]] = {}

# Real wall-clock time of the last actual Jira fetch behind each cache key —
# separate from _stats_cache's expiry bookkeeping so every existing
# _dedup_fetch call site keeps its current return shape unchanged. Lets a
# caller that already knows its own cache key (e.g. daily_ops_stats(), which
# calls four _dedup_fetch-backed functions) report an honest "as of" time
# instead of silently showing a snapshot that could be up to
# jira_stats_cache_ttl_seconds (default 3600s/1h) stale — confirmed live this
# session as the real cause of "I closed cases but the stats still say 0."
_stats_fetched_at: dict[tuple, datetime] = {}


def stats_fetched_at(key: tuple) -> datetime | None:
    """Real UTC timestamp of the last actual (non-cached) fetch for this
    cache key, or None if it's never been fetched. `key` must match the
    exact cache_key tuple the target function builds internally — see each
    function's own `cache_key = (...)` line."""
    return _stats_fetched_at.get(key)

# In-flight request de-duplication: My Desk's single page load fires
# desk/summary and desk/team in parallel, and both call team_open_stats()
# with identical arguments at the same instant — without this, both would
# race past the completed-result cache above (which only helps a *second*,
# later request) and each pay for the full paginated Jira fetch, doubling
# the live round-trips on every single page load. Concurrent callers for
# the same key now await one shared fetch instead of starting their own.
_stats_inflight: dict[tuple, asyncio.Future] = {}


def _cache_get(key: tuple) -> dict | None:
    entry = _stats_cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if time.monotonic() > expires_at:
        del _stats_cache[key]
        return None
    return value


def _cache_set(key: tuple, value: dict) -> None:
    _stats_cache[key] = (time.monotonic() + settings.jira_stats_cache_ttl_seconds, value)
    _stats_fetched_at[key] = datetime.now(timezone.utc)


async def _dedup_fetch(key: tuple, fetch_fn) -> dict:
    """Run `fetch_fn()` at most once per cache key across concurrent callers."""
    cached = _cache_get(key)
    if cached is not None:
        return cached

    existing = _stats_inflight.get(key)
    if existing is not None:
        return await existing

    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    _stats_inflight[key] = fut
    try:
        result = await fetch_fn()
        _cache_set(key, result)
        fut.set_result(result)
        return result
    except Exception as exc:
        fut.set_exception(exc)
        raise
    finally:
        _stats_inflight.pop(key, None)


_TEAM_RESOLVED_FIELDS = "assignee,resolutiondate,created,customfield_10054,comment,summary,customfield_10047"


async def team_resolved_stats(
    db,
    team: list[str],
    *,
    days: int | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Real per-engineer resolved-case count + TTR, queried live from Jira.

    Deliberately bypasses the local `cases` table: that table only holds
    tickets a human has manually mapped to a customer via the Jira Mapping
    screen (anything else sits in `jira_unmatched` forever), so it covers a
    small fraction of real DSD tickets — confirmed live, the local table
    showed 2 tickets resolved by Asaph this month against a real count of
    11. Workload/TTR is a per-assignee question, not a per-customer one, so
    it doesn't need that mapping at all — go straight to Jira.

    Pass either `days` (a rolling N-day window, ending now) or `start`/`end`
    (a fixed calendar-date range, `end` exclusive) — never both. The
    calendar form exists so "last month" means an actual stable month you
    can compare against, not a shifting 30-day lookback.

    by_engineer also carries a fresh/backlog split of TTR/TTFR — reuses
    _tag_resolved_freshness() (see its docstring for the full reasoning,
    shared with team_daily_resolved()'s Resolved-count split): a batch of
    old tickets closed together doesn't just inflate the resolved count,
    it also drags stale created→resolved/first-response durations into
    this window's median, making current responsiveness look worse (or
    better) than it really is. `_fresh` / `_backlog` variants split the
    same underlying durations by whether the ticket was actually worked in
    this window. Only computed for the team-filtered subset (not
    `total_resolved`'s unfiltered project-wide set) — restricting the
    comment-fetch cost to the ~55% share that's actually team-relevant,
    same optimization already proven in team_daily_resolved().

    `tickets_by_engineer` carries the real per-ticket detail (ref/title/
    customer/days-to-resolve) behind each engineer's resolved count — same
    "stop discarding the already-fetched issue" pattern as team_open_stats'
    by_status / team_created_stats' tickets_by_engineer. Powers Team Load
    Split's drillable Resolved column.
    """
    if start is not None and end is not None:
        date_range = f'resolutiondate >= "{start.isoformat()}" AND resolutiondate < "{end.isoformat()}"'
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    elif days is not None:
        date_range = f"resolutiondate >= -{days}d"
        window_start = datetime.now(timezone.utc) - timedelta(days=days)
    else:
        raise ValueError("team_resolved_stats requires either `days` or `start`+`end`")
    jql = f'project = "DSD" AND statusCategory = Done AND {date_range}'

    cache_key = ("resolved", tuple(sorted(team)), days, start, end)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {
                    "jql": jql, "maxResults": 100, "fields": _TEAM_RESOLVED_FIELDS,
                    "expand": "changelog",
                }
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            team_issues = [i for i in issues if (i["fields"].get("assignee") or {}).get("displayName") in team]
            fresh_by_key = await _tag_resolved_freshness(db, client, team_issues, window_start)

        counts = {name: 0 for name in team}
        hours_by_name: dict[str, list[float]] = {name: [] for name in team}
        ttfr_by_name: dict[str, list[float]] = {name: [] for name in team}
        hours_by_name_fresh: dict[str, list[float]] = {name: [] for name in team}
        hours_by_name_backlog: dict[str, list[float]] = {name: [] for name in team}
        ttfr_by_name_fresh: dict[str, list[float]] = {name: [] for name in team}
        ttfr_by_name_backlog: dict[str, list[float]] = {name: [] for name in team}
        fresh_resolved_by_name: dict[str, int] = {name: 0 for name in team}
        all_hours: list[float] = []
        all_ttfr_hours: list[float] = []
        # Real per-ticket detail behind each engineer's resolved count — the
        # issue is already fully fetched to build the counts/medians above,
        # this just stops discarding it. Powers Team Load Split's drillable
        # Resolved column and Command Center's Resolved tile.
        tickets_by_engineer: dict[str, list[dict]] = {name: [] for name in team}
        for issue in issues:
            f = issue["fields"]
            name = (f.get("assignee") or {}).get("displayName")
            created = _parse_dt(f.get("created"))
            resolved = _parse_dt(f.get("resolutiondate"))
            hours = (resolved - created).total_seconds() / 3600 if created and resolved else None
            if hours is not None:
                all_hours.append(hours)
            ttfr_hours, _ = _extract_ttfr(f.get("customfield_10054"))
            if ttfr_hours is not None:
                all_ttfr_hours.append(ttfr_hours)
            if name in counts:
                counts[name] += 1
                if hours is not None:
                    hours_by_name[name].append(hours)
                if ttfr_hours is not None:
                    ttfr_by_name[name].append(ttfr_hours)
                fresh = fresh_by_key.get(issue["key"], False)
                if fresh:
                    fresh_resolved_by_name[name] += 1
                bucket_hours = hours_by_name_fresh if fresh else hours_by_name_backlog
                bucket_ttfr = ttfr_by_name_fresh if fresh else ttfr_by_name_backlog
                if hours is not None:
                    bucket_hours[name].append(hours)
                if ttfr_hours is not None:
                    bucket_ttfr[name].append(ttfr_hours)
                tickets_by_engineer[name].append({
                    "jira_ref": issue["key"],
                    "title": f.get("summary") or "",
                    "assignee_name": name,
                    "customer_name": _extract_customer_name(f.get("customfield_10047")),
                    "days_open": round(hours / 24) if hours is not None else None,
                })

        def _median(hrs: list[float]) -> float | None:
            return round(statistics.median(hrs), 1) if hrs else None

        return {
            "total_resolved": len(issues),
            "total_ttr_median_hours": _median(all_hours),
            "total_ttfr_median_hours": _median(all_ttfr_hours),
            "by_engineer": {
                name: {
                    "resolved": counts[name],
                    "ttr_median_hours": _median(hours_by_name[name]),
                    # Per-engineer TTFR, scoped to THIS window's resolved
                    # tickets — added because desk_team() was silently using
                    # team_open_stats' unwindowed, all-currently-open-tickets
                    # TTFR for "You vs The Team" regardless of which window
                    # was selected (confirmed live: switching Week/Month/
                    # Quarter/Year never changed this number). desk_team()'s
                    # dict-merge order means this now wins over that stale
                    # value with no other code change needed.
                    "ttfr_median_hours": _median(ttfr_by_name[name]),
                    "ttr_median_hours_fresh": _median(hours_by_name_fresh[name]),
                    "ttr_median_hours_backlog": _median(hours_by_name_backlog[name]),
                    "ttfr_median_hours_fresh": _median(ttfr_by_name_fresh[name]),
                    "ttfr_median_hours_backlog": _median(ttfr_by_name_backlog[name]),
                    "fresh_resolved": fresh_resolved_by_name[name],
                }
                for name in team
            },
            "tickets_by_engineer": tickets_by_engineer,
        }

    return await _dedup_fetch(cache_key, _fetch)


async def team_created_stats(
    team: list[str],
    *,
    days: int | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    """Real per-engineer + team-total "cases logged" count, queried live from
    Jira — how many tickets were CREATED in the window, regardless of
    current status (a ticket created 3 days ago and already resolved by now
    still counts as logged this week). Deliberately NOT filtered by
    statusCategory, unlike team_resolved_stats — mirrors that function's
    exact days/start/end signature and local-table-bypass reasoning
    (Case.created_at only covers tickets a human has manually mapped to a
    customer).

    `tickets_by_engineer` carries the real per-ticket detail (ref/title/
    customer/age) behind each engineer's count — the issue list is already
    fully fetched to build the counts, this just stops discarding it, same
    pattern as team_open_stats' by_status / team_daily_resolved's
    tickets_by_day. Powers Team Load Split's drillable Created column."""
    if start is not None and end is not None:
        date_range = f'created >= "{start.isoformat()}" AND created < "{end.isoformat()}"'
    elif days is not None:
        date_range = f"created >= -{days}d"
    else:
        raise ValueError("team_created_stats requires either `days` or `start`+`end`")
    jql = f'project = "DSD" AND {date_range}'

    cache_key = ("created", tuple(sorted(team)), days, start, end)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": "assignee,summary,customfield_10047,created"}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        now = datetime.now(timezone.utc)
        counts = {name: 0 for name in team}
        tickets_by_engineer: dict[str, list[dict]] = {name: [] for name in team}
        for issue in issues:
            f = issue["fields"]
            name = (f.get("assignee") or {}).get("displayName")
            if name in counts:
                counts[name] += 1
                created = _parse_dt(f.get("created"))
                days_open = round((now - created).total_seconds() / 86400) if created else None
                tickets_by_engineer[name].append({
                    "jira_ref": issue["key"],
                    "title": f.get("summary") or "",
                    "assignee_name": name,
                    "customer_name": _extract_customer_name(f.get("customfield_10047")),
                    "days_open": days_open,
                })

        return {
            "total_created": len(issues),
            "by_engineer": {name: {"created": counts[name]} for name in team},
            "tickets_by_engineer": tickets_by_engineer,
        }

    return await _dedup_fetch(cache_key, _fetch)


async def team_daily_resolved(db, team: list[str], days: int = 30) -> dict:
    """Real per-day, per-engineer resolved-case counts, queried live from Jira.

    Deliberately does ONE ranged fetch for the whole window and buckets the
    results by calendar day locally, rather than looping team_resolved_stats
    once per day — the latter would mean N live paginated Jira queries
    (confirmed ~4-5s/page, ~30s cold each) for a backfill, which is slow and
    wasteful when the same JQL fetch already returns resolutiondate per issue.
    Powers the Resolved dimension of daily_ops_stats() — real Jira history,
    no new local table needed. See team_daily_assigned() immediately below
    for the equivalent Assigned dimension.

    Returns {"by_day": {date: {name: count}}, "fresh_by_day": {date: {name:
    count}}, "tickets_by_day": {date: [{jira_ref, title, assignee_name,
    customer_name, fresh}]}}. See _tag_resolved_freshness()'s docstring for
    the full fresh/backlog-clearance reasoning — shared with
    team_resolved_stats()'s TTFR/TTR split.
    """
    # Team-scoped in the JQL itself now (not just filtered client-side after
    # fetching) — the fresh/backlog computation added a per-issue comment
    # fetch, and confirmed live this function alone took 18s at 30 days when
    # it fetched (and then discarded) every project-wide resolved ticket
    # rather than just the 3 team members' ~55% share.
    team_clause = " OR ".join(f'assignee = "{n}"' for n in team)
    jql = f'project = "DSD" AND statusCategory = Done AND resolutiondate >= -{days}d AND ({team_clause})'
    cache_key = ("daily_resolved", tuple(sorted(team)), days)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {
                    "jql": jql, "maxResults": 100,
                    "fields": "assignee,resolutiondate,created,summary,customfield_10047,comment",
                    "expand": "changelog",
                }
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            window_start = datetime.now(timezone.utc) - timedelta(days=days)
            fresh_by_key = await _tag_resolved_freshness(db, client, issues, window_start)

        by_day: dict[str, dict[str, int]] = {}
        fresh_by_day: dict[str, dict[str, int]] = {}
        tickets_by_day: dict[str, list[dict]] = {}
        for issue in issues:
            f = issue["fields"]
            name = (f.get("assignee") or {}).get("displayName")
            if name not in team:
                continue
            resolved = _parse_dt(f.get("resolutiondate"))
            if not resolved:
                continue
            fresh = fresh_by_key.get(issue["key"], False)

            day_key = resolved.date().isoformat()
            by_day.setdefault(day_key, {n: 0 for n in team})
            by_day[day_key][name] += 1
            if fresh:
                fresh_by_day.setdefault(day_key, {n: 0 for n in team})
                fresh_by_day[day_key][name] += 1
            tickets_by_day.setdefault(day_key, []).append({
                "jira_ref": issue["key"],
                "title": f.get("summary", ""),
                "assignee_name": name,
                "customer_name": _extract_customer_name(f.get("customfield_10047")),
                "fresh": fresh,
            })
        return {"by_day": by_day, "fresh_by_day": fresh_by_day, "tickets_by_day": tickets_by_day}

    return await _dedup_fetch(cache_key, _fetch)


async def team_daily_created(team: list[str], days: int = 30) -> dict:
    """Real per-day, per-engineer "opened" (created) counts, queried live from
    Jira. Mirrors team_daily_resolved()'s exact one-ranged-fetch-then-bucket-
    locally approach, but keys off `created` instead of `resolutiondate` and
    is deliberately NOT filtered by statusCategory — a ticket opened and
    already resolved by now still counts as opened that day, same reasoning
    as team_created_stats(). Powers the Opened dimension of daily_ops_stats().

    Returns {"by_day": {date: {name: count}}, "tickets_by_day": {date:
    [{jira_ref, title, assignee_name, customer_name}]}} — see
    team_daily_resolved()'s docstring for why the ticket list exists
    (drillable Opened Tickets panel).
    """
    jql = f'project = "DSD" AND created >= -{days}d'
    cache_key = ("daily_created", tuple(sorted(team)), days)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": "assignee,created,summary,customfield_10047"}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        by_day: dict[str, dict[str, int]] = {}
        tickets_by_day: dict[str, list[dict]] = {}
        for issue in issues:
            f = issue["fields"]
            name = (f.get("assignee") or {}).get("displayName")
            if name not in team:
                continue
            created = _parse_dt(f.get("created"))
            if not created:
                continue
            day_key = created.date().isoformat()
            by_day.setdefault(day_key, {n: 0 for n in team})
            by_day[day_key][name] += 1
            tickets_by_day.setdefault(day_key, []).append({
                "jira_ref": issue["key"],
                "title": f.get("summary", ""),
                "assignee_name": name,
                "customer_name": _extract_customer_name(f.get("customfield_10047")),
            })
        return {"by_day": by_day, "tickets_by_day": tickets_by_day}

    return await _dedup_fetch(cache_key, _fetch)


async def team_daily_assigned(team: list[str], days: int = 30) -> dict:
    """Real per-day, per-engineer assignment counts, from Jira's own
    changelog — confirmed live that this Jira instance supports the history
    JQL operator (`assignee CHANGED TO "name" AFTER <date>` returns real,
    correct per-engineer results), and that `expand=changelog` on /search
    returns the exact transition timestamp for each assignee change.

    Deliberately NOT built on the local `cases` table or an app-side
    AuditLog event (an earlier version of this feature was) — both
    structurally undercount, the former because it only covers tickets a
    human has manually mapped to a customer (confirmed elsewhere in this
    file: ~10x undercount), the latter because it's forward-only from
    whenever it shipped. This is real Jira history, same "always go
    straight to Jira" reasoning as team_open_stats/team_resolved_stats.

    The changelog embedded in a /search result IS capped (confirmed live:
    40 of 77 total history entries on the worst sampled ticket, 12 of 1000
    sampled issues affected) — but unlike the comment field, it's
    newest-first (confirmed live: the first returned entry is *later* than
    the last), so truncation only drops OLDER entries. A day-bucketed query
    over a reasonable window (30-90d) is safe without a per-ticket fallback
    fetch the way comments needed one.

    Returns {"by_day": {date: {name: count}}, "fresh_by_day": {date: {name:
    count}}} — fresh/backlog split mirrors Resolved's (see
    team_daily_resolved()'s docstring), but the question here is "is this
    genuinely new incoming work or an old ticket being reassigned/rebalanced
    onto someone": fresh = the reassigned ticket was itself CREATED inside
    this window; backlog = an older ticket just changed hands. No comment
    fetch needed for this one — `created` is a plain field on the same
    already-fetched issue, not a separate round trip.
    """
    jql = f'project = "DSD" AND assignee CHANGED AFTER -{days}d'
    cache_key = ("daily_assigned", tuple(sorted(team)), days)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": "assignee,created", "expand": "changelog"}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        window_start = datetime.now(timezone.utc) - timedelta(days=days)

        by_day: dict[str, dict[str, int]] = {}
        fresh_by_day: dict[str, dict[str, int]] = {}
        for issue in issues:
            issue_created = _parse_dt(issue["fields"].get("created"))
            fresh = issue_created is not None and issue_created >= window_start
            for history in issue.get("changelog", {}).get("histories", []):
                created = _parse_dt(history.get("created"))
                if not created:
                    continue
                for item in history.get("items", []):
                    if item.get("field") != "assignee":
                        continue
                    to_name = item.get("toString")
                    if to_name not in team:
                        continue
                    day_key = created.date().isoformat()
                    by_day.setdefault(day_key, {n: 0 for n in team})
                    by_day[day_key][to_name] += 1
                    if fresh:
                        fresh_by_day.setdefault(day_key, {n: 0 for n in team})
                        fresh_by_day[day_key][to_name] += 1
        return {"by_day": by_day, "fresh_by_day": fresh_by_day}

    return await _dedup_fetch(cache_key, _fetch)


async def team_daily_replies_comments(db, team: list[str], days: int = 30) -> dict[str, dict[str, dict[str, int]]]:
    """Real per-day, per-engineer count of public replies (jsdPublic=True —
    customer-facing) vs internal comments (jsdPublic=False), from Jira.

    Unlike Assigned/Resolved, there's no JQL history operator for comments
    (confirmed: Jira doesn't expose comment-author/date as a searchable
    changelog-style field) — so this has to be candidate-set + targeted
    fetch: pull every ticket touched in the window (project-wide, not just
    per-assignee, since anyone can comment on anyone else's ticket), then
    use _cached_comments_batch() (the same DB-backed cache team_open_stats
    uses) to get each candidate's real comments and bucket by day/author/
    jsdPublic. Bounded by "how many tickets got touched in the window", not
    "every open ticket."
    """
    jql = f'project = "DSD" AND updated >= -{days}d'
    cache_key = ("daily_replies_comments", tuple(sorted(team)), days)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": "comment"}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            comments_by_key = await _cached_comments_batch(db, client, issues)

        window_start = datetime.now(timezone.utc) - timedelta(days=days)
        by_day: dict[str, dict[str, dict[str, int]]] = {}
        for comments in comments_by_key.values():
            for c in comments:
                author = (c.get("author") or {}).get("displayName")
                if author not in team:
                    continue
                created = _parse_dt(c.get("created"))
                if not created or created < window_start:
                    continue
                day_key = created.date().isoformat()
                by_day.setdefault(day_key, {n: {"replies": 0, "comments": 0} for n in team})
                kind = "replies" if c.get("jsdPublic") is True else "comments"
                by_day[day_key][author][kind] += 1
        return by_day

    return await _dedup_fetch(cache_key, _fetch)


_TEAM_OPEN_FIELDS = "assignee,created,comment,customfield_10054,status,summary,customfield_10047,priority,labels,customfield_10014"


async def team_open_stats(db, team: list[str], *, since: datetime | None = None) -> dict:
    """Real per-engineer open-ticket count/age/TTFR, queried live from Jira.

    `db` is used only to persist comment fetches into the local CaseComment
    cache (see _cached_comments()) — a durable, DB-backed layer beneath
    _dedup_fetch's in-memory cache, so a restart (which wipes the in-memory
    cache) doesn't force a full re-fetch of every high-comment-count
    ticket's comments. Safe to thread through the closure below even under
    _dedup_fetch's concurrent-caller dedup: whichever caller's await chain
    actually triggers the fetch keeps its own session open for the fetch's
    full duration regardless of how many other callers are just awaiting
    the same in-flight result.

    Same root cause as team_resolved_stats: the local `cases` table only
    covers tickets a human has manually mapped to a customer, which
    undercounts real open workload badly — confirmed live, 566 real open
    DSD tickets exist against 59 in the local table (Gisele alone carries
    177 real open tickets against a locally-shown 18). Workload/TTFR is a
    per-assignee question, not a per-customer one, so go straight to Jira.

    `since`, when passed, additionally computes a *windowed* view of the
    open set — total_open_in_window/by_engineer[name]["open_in_window"]/etc
    — restricted to tickets whose `created` falls on or after `since` and
    are still open right now. This exists specifically for Team Load
    Split's donut/table (see desk_team()): the always-live total_open/
    by_engineer[name]["open"] fields below are an honest "how much do you
    currently have on your plate," but they let anyone who has accumulated
    a large backlog over months/years look artificially dominant on every
    single period toggle (day/week/month all show the identical, ever-
    growing live number) — visually rewarding holding old tickets over
    actually resolving them. "Created within the selected window, still
    open" answers the fairer question instead: of what actually arrived in
    this window, how much is still sitting with you. The unwindowed fields
    are untouched and keep meaning "right now" for every other existing
    reader (Open Load, the Unassigned/needs-triage flag, the Open Load
    narrative's "current queue" framing) — this is additive, not a
    replacement.
    """
    # "Pending Upgrade" is Done-category in Jira (confirmed live via the
    # project's status scheme) but isn't genuinely resolved from the
    # customer's side — these are defects already fixed in a release,
    # waiting on the customer to actually upgrade and receive the fix. Fetch
    # them alongside the real open set so by_status (below) can represent
    # them as still-open work, but keep them OUT of the existing aggregates
    # (total_open/by_engineer/etc, used by Team Load Split and Open Load
    # elsewhere) so this doesn't silently change well-established numbers
    # that other views/baselines already rely on — see the per-issue gate
    # a few lines down.
    # Callers (desk_team()'s period_start) pass naive UTC datetimes —
    # `created` below is always tz-aware (parsed from Jira's own offset
    # ISO strings), so normalize `since` to match or the >= comparison
    # raises TypeError: can't compare offset-naive and offset-aware datetimes.
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)

    jql = 'project = "DSD" AND (statusCategory != Done OR status = "Pending Upgrade")'
    _PENDING_UPGRADE = "Pending Upgrade"

    # Cache only the raw Jira fetch (issues + comments) — the expensive,
    # network-bound part — keyed just on `team`, not `since`. The
    # aggregation below is pure in-memory Python and re-runs on every call
    # so different callers requesting different windows (desk_team() gets
    # hit with day/week/month/quarter/year, often within the same 5-minute
    # cache TTL) don't each force a fresh, costly re-fetch just to get a
    # different post-processing pass over identical underlying issues.
    cache_key = ("open_raw", tuple(sorted(team)))

    async def _fetch_raw() -> tuple[list[dict], dict[str, list[dict]]]:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": _TEAM_OPEN_FIELDS}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            # Batch, not per-issue — _cached_comments_batch() does one read,
            # concurrent real fetches only for tickets that need one (no-op
            # Jira-wise both for the ~83% under the embedded 20-comment cap
            # AND for any over-cap ticket already cached locally with
            # nothing new since last time), then one write. NOT
            # asyncio.gather(_cached_comments(...) for issue in issues) —
            # confirmed live that throws InvalidRequestError, a single
            # AsyncSession can't be used concurrently.
            comments_by_key = await _cached_comments_batch(db, client, issues)
        return issues, comments_by_key

    issues, comments_by_key = await _dedup_fetch(cache_key, _fetch_raw)

    now = datetime.now(timezone.utc)
    today_start = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc)

    counts = {name: 0 for name in team}
    ages_by_name: dict[str, list[float]] = {name: [] for name in team}
    ttfr_by_name: dict[str, list[float]] = {name: [] for name in team}
    updated_today_by_name = {name: 0 for name in team}
    all_ages: list[float] = []
    all_ttfr: list[float] = []
    updated_today_total = 0
    unassigned_open = 0
    other_open = 0
    total_open_count = 0
    # Real per-status ticket detail across EVERY open project ticket
    # (not just the named team) — this is the same raw fetch, just not
    # discarded after the aggregate counts are built. Command Center's
    # "Case Mix by Status" used to be built from the local `cases` table
    # instead, which confirmed-live badly undercounts specific statuses
    # (2 of 151 real "Defect / Enhancement submitted" tickets were
    # locally mapped) since most tickets never get manually linked to a
    # customer record until someone actively works them.
    by_status: dict[str, list[dict]] = {}

    # Windowed ("created on/after `since`, still open") mirrors of the
    # unwindowed accumulators above — see the docstring for why.
    counts_window = {name: 0 for name in team}
    ages_by_name_window: dict[str, list[float]] = {name: [] for name in team}
    all_ages_window: list[float] = []
    unassigned_open_window = 0
    other_open_window = 0
    total_open_window = 0
    # Real per-ticket detail behind each engineer's windowed open count —
    # same shape as by_status' entries (this is the same per-issue loop),
    # just grouped by assignee instead of status. Powers Team Load Split's
    # drillable Open/Still-Open column.
    tickets_by_engineer_window: dict[str, list[dict]] = {name: [] for name in team}

    for issue in issues:
        f = issue["fields"]
        name = (f.get("assignee") or {}).get("displayName")
        created = _parse_dt(f.get("created"))
        age_days = (now - created).total_seconds() / 86400 if created else None
        ttfr_hours, ttfr_breached = _extract_ttfr(f.get("customfield_10054"))
        in_window = since is not None and created is not None and created >= since

        status_name = (f.get("status") or {}).get("name") or "Unknown"
        request_type = _extract_request_type(f.get("customfield_10014"))
        last_reply_by, last_reply_at = _last_reply(comments_by_key.get(issue["key"], []))
        by_status.setdefault(status_name, []).append({
            "jira_ref": issue["key"],
            "title": f.get("summary") or "",
            "assignee_name": name,
            "customer_name": _extract_customer_name(f.get("customfield_10047")),
            "days_open": round(age_days) if age_days is not None else None,
            "ttfr_breached": bool(ttfr_breached),
            "priority": _map_priority((f.get("priority") or {}).get("name", "Severity 3")),
            "case_type": _map_type(status_name, f.get("labels") or [], request_type),
            "created": f.get("created"),
            "sla": _extract_sla_state(f.get("customfield_10054")),
            # Who replied most recently ("customer" or a real team display
            # name) and when — sourced from the same comments_by_key batch
            # already fetched above, zero extra Jira calls. Covers every
            # open ticket here, matched-to-a-local-Case or not, so the My
            # Desk Queue Table's "last update" column has full coverage.
            "last_reply_by": last_reply_by,
            "last_reply_at": last_reply_at.isoformat() if last_reply_at else None,
        })

        # Pending-Upgrade tickets are excluded from every aggregate below
        # (total_open/by_engineer/ages/ttfr/updated-today) — they still
        # land in by_status above for Case Mix/Aged Cases/SLA Breaching,
        # but Open Load, Team Load Split, and every other existing
        # consumer of this function keep exactly the numbers they had
        # before this change.
        if status_name != _PENDING_UPGRADE:
            total_open_count += 1
            if in_window:
                total_open_window += 1

            # "Updated today" means the assignee themselves commented
            # today — not Jira's raw `updated` timestamp, which also
            # bumps for the SLA-breach bot, customer replies, and other
            # engineers commenting on someone else's ticket. Confirmed
            # live this was wildly overcounting: of one engineer's 16
            # tickets flagged "updated" today, only 2 actually had a
            # same-day comment from that engineer — the rest were the
            # SLA bot (Bernhard Hafting) or other parties. Uses the
            # pre-fetched full comment list (see comments_by_key above)
            # since the embedded field caps at 20 oldest-first comments
            # — without it, "updated today" is structurally blind on the
            # ~17% of tickets busy enough to hit that cap (confirmed live).
            comments = comments_by_key[issue["key"]]
            is_updated_today = any(
                (c.get("author") or {}).get("displayName") == name and
                (created_at := _parse_dt(c.get("created"))) and created_at >= today_start
                for c in comments
            ) if name else False

            if age_days is not None:
                all_ages.append(age_days)
                if in_window:
                    all_ages_window.append(age_days)
            if ttfr_hours is not None:
                all_ttfr.append(ttfr_hours)
            if is_updated_today:
                updated_today_total += 1

            if not name:
                unassigned_open += 1
                if in_window:
                    unassigned_open_window += 1
            elif name not in counts:
                other_open += 1
                if in_window:
                    other_open_window += 1
            else:
                counts[name] += 1
                if age_days is not None:
                    ages_by_name[name].append(age_days)
                if ttfr_hours is not None:
                    ttfr_by_name[name].append(ttfr_hours)
                if is_updated_today:
                    updated_today_by_name[name] += 1
                if in_window:
                    counts_window[name] += 1
                    if age_days is not None:
                        ages_by_name_window[name].append(age_days)
                    tickets_by_engineer_window[name].append({
                        "jira_ref": issue["key"],
                        "title": f.get("summary") or "",
                        "assignee_name": name,
                        "customer_name": _extract_customer_name(f.get("customfield_10047")),
                        "days_open": round(age_days) if age_days is not None else None,
                    })

    def _mean_median(vals: list[float]) -> tuple[float | None, float | None]:
        if not vals:
            return None, None
        return round(statistics.mean(vals), 1), round(statistics.median(vals), 1)

    def _median(vals: list[float]) -> float | None:
        return round(statistics.median(vals), 1) if vals else None

    total_age_mean, total_age_median = _mean_median(all_ages)
    total_age_mean_w, total_age_median_w = _mean_median(all_ages_window)
    by_engineer = {}
    for name in team:
        age_mean, age_median = _mean_median(ages_by_name[name])
        age_mean_w, age_median_w = _mean_median(ages_by_name_window[name])
        by_engineer[name] = {
            "open": counts[name],
            "open_age_mean_days": age_mean,
            "open_age_median_days": age_median,
            "updated_today": updated_today_by_name[name],
            "ttfr_median_hours": _median(ttfr_by_name[name]),
            "open_in_window": counts_window[name],
            "open_age_mean_days_in_window": age_mean_w,
            "open_age_median_days_in_window": age_median_w,
        }

    return {
        "total_open": total_open_count,
        "total_open_age_mean_days": total_age_mean,
        "total_open_age_median_days": total_age_median,
        "total_updated_today": updated_today_total,
        "total_ttfr_median_hours": _median(all_ttfr),
        "unassigned_open": unassigned_open,
        "other_open": other_open,
        "by_engineer": by_engineer,
        "by_status": by_status,
        "total_open_in_window": total_open_window,
        "total_open_age_mean_days_in_window": total_age_mean_w,
        "total_open_age_median_days_in_window": total_age_median_w,
        "unassigned_open_in_window": unassigned_open_window,
        "other_open_in_window": other_open_window,
        "tickets_by_engineer_in_window": tickets_by_engineer_window,
    }


async def _build_customer_match_maps(db) -> tuple[dict[int, "Customer"], dict[str, "Customer"], dict[str, int]]:
    """Shared name-matching setup, factored out of poll_and_upsert()'s inline
    version so real_open_counts_by_customer()/real_resolved_stats() don't
    each rebuild it — same normalized-name-first, CustomerNameAlias-fallback
    precedence, see _resolve_customer_by_name_or_alias()."""
    all_customers = (await db.execute(select(Customer))).scalars().all()
    customers_by_id = {c.id: c for c in all_customers}
    customers_by_normalized: dict[str, Customer] = {}
    for c in all_customers:
        norm = _normalize_company_name(c.name)
        customers_by_normalized[norm] = None if norm in customers_by_normalized else c  # type: ignore[assignment]
    aliases = (await db.execute(select(CustomerNameAlias))).scalars().all()
    by_alias: dict[str, int] = {a.alias_name.strip().lower(): a.customer_id for a in aliases}
    return customers_by_id, customers_by_normalized, by_alias


async def customer_last_case_dates(db, since: date) -> dict[int, date]:
    """Real, live-Jira last-support-case date per LOCAL customer_id — backs
    the Quiet (6mo) / Dormant (12mo) engagement flags on Customer
    Intelligence. Reuses the exact same normalized-name + CustomerNameAlias
    resolution as real_open_counts_by_customer() above.

    `since` bounds the scan to ~13 months back (comfortably past the
    12-month Dormant threshold) rather than the full multi-year history —
    a customer with no real activity in that window simply keeps whatever
    last_case_activity_at is already stored (see
    scheduler.py::_customer_engagement_refresh()), which correctly
    continues aging. Confirmed live: JQL's relative `-Ny` date syntax
    silently returns 0 results, so `since` must be passed as an explicit
    `YYYY-MM-DD` string, not a relative expression."""
    customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)

    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    jql = f'project = "DSD" AND customfield_10047 is not EMPTY AND created >= "{since.isoformat()}"'
    latest_by_customer: dict[int, date] = {}
    page_token: str | None = None
    async with httpx.AsyncClient(auth=_auth(), timeout=30, follow_redirects=True) as client:
        while True:
            params = {"jql": jql, "maxResults": 100, "fields": "customfield_10047,created"}
            if page_token:
                params["nextPageToken"] = page_token
            resp = await client.get(url, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
            for issue in data.get("issues", []):
                name = _extract_customer_name(issue["fields"].get("customfield_10047"))
                customer = _resolve_customer_by_name_or_alias(name, customers_by_normalized, by_alias, customers_by_id)
                if not customer:
                    continue
                created = _parse_dt(issue["fields"].get("created"))
                if not created:
                    continue
                created_date = created.date()
                if customer.id not in latest_by_customer or created_date > latest_by_customer[customer.id]:
                    latest_by_customer[customer.id] = created_date
            if data.get("isLast", True):
                break
            page_token = data.get("nextPageToken")
            if not page_token:
                break

    return latest_by_customer


async def real_open_counts_by_customer(db) -> dict[int, dict]:
    """Real, live-Jira open-ticket counts grouped by LOCAL customer_id —
    reuses team_open_stats()'s already-fetched, already-cached `by_status`
    data (no new Jira fetch of its own) instead of the local `cases` table,
    which undercounts real per-customer open volume the same way it
    undercounts everything else built on it this session (confirmed live:
    a real customer showed 13 open locally vs. 95 real). Matches each open
    ticket's real Customer field to a local Customer row using the exact
    same normalized-name + CustomerNameAlias precedence poll_and_upsert()
    already established — see _resolve_customer_by_name_or_alias().

    Excludes "Pending Upgrade" tickets, matching team_open_stats()'s own
    total_open_count exclusion (Done-category in Jira, not genuinely open
    from the customer's side).

    Returns {customer_id: {"open_count": int, "customer_name": str}} —
    only customers with at least one real, matched open ticket appear
    (unmatched tickets are silently dropped here, same as everywhere else
    real Jira data gets reconciled against the local customer list — this
    function answers "how many opens per KNOWN customer," not a general
    ticket audit).
    """
    stats = await team_open_stats(db, list(_LANES_SUPPORT_TEAM))
    customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)

    counts: dict[int, int] = {}
    for status_name, tickets in stats["by_status"].items():
        if status_name == "Pending Upgrade":
            continue
        for t in tickets:
            customer = _resolve_customer_by_name_or_alias(
                t["customer_name"], customers_by_normalized, by_alias, customers_by_id,
            )
            if customer:
                counts[customer.id] = counts.get(customer.id, 0) + 1

    return {
        cid: {"open_count": n, "customer_name": customers_by_id[cid].name}
        for cid, n in counts.items()
    }


async def _fetch_resolved_tickets_raw(days: int) -> dict:
    """Cached raw fetch of every real resolved DSD ticket in the window —
    project-wide, no assignee filter (unlike team_resolved_stats(), which
    got team-scoped for the fresh/backlog cost optimization and no longer
    suits an unteamed "all resolved tickets" question). No db access here
    deliberately, so this stays safely memoizable via _dedup_fetch across
    requests/db-sessions — customer-name matching against the local
    Customer table happens in real_resolved_stats() below, outside the cache.
    """
    jql = f'project = "DSD" AND statusCategory = Done AND resolutiondate >= -{days}d'
    cache_key = ("real_resolved_raw", days)

    async def _fetch() -> dict:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        issues: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            while True:
                params = {
                    "jql": jql, "maxResults": 100,
                    "fields": "resolutiondate,created,customfield_10047",
                }
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                issues.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break
        return {"issues": issues}

    return await _dedup_fetch(cache_key, _fetch)


async def real_resolved_stats(db, days: int = 90) -> dict:
    """Real, live-Jira resolved-ticket stats — bypasses the local `cases`
    table for the same undercount reason as everywhere else this session
    (real per-customer resolved attribution needs the same fix
    real_open_counts_by_customer() already applied to open counts).

    Returns {window_days, total_resolved_90d, resolved_this_week,
    resolved_this_month, ttr_median_hours, top_resolved_accounts:
    [{customer_name, count}], weekly_trend: [{week_ending, count}]} — same
    shape the local-table version already returned, so this is a drop-in
    data-source swap, not a contract change.
    """
    raw = await _fetch_resolved_tickets_raw(days)
    issues = raw["issues"]

    today = datetime.now(timezone.utc).date()
    week_start = today - timedelta(days=7)
    month_start = today - timedelta(days=30)

    ttr_hours: list[float] = []
    resolved_this_week = 0
    resolved_this_month = 0
    by_customer_name: dict[str, int] = {}
    resolved_dates: list[date] = []

    for issue in issues:
        f = issue["fields"]
        resolved = _parse_dt(f.get("resolutiondate"))
        if not resolved:
            continue
        created = _parse_dt(f.get("created"))
        if created:
            ttr_hours.append((resolved - created).total_seconds() / 3600)
        rdate = resolved.date()
        resolved_dates.append(rdate)
        if rdate >= week_start:
            resolved_this_week += 1
        if rdate >= month_start:
            resolved_this_month += 1
        cust_name = _extract_customer_name(f.get("customfield_10047"))
        if cust_name:
            by_customer_name[cust_name] = by_customer_name.get(cust_name, 0) + 1

    weekly_trend = []
    for i in range(12, -1, -1):
        w_start = today - timedelta(days=(i + 1) * 7)
        w_end = today - timedelta(days=i * 7)
        count = sum(1 for d in resolved_dates if w_start <= d < w_end)
        weekly_trend.append({"week_ending": w_end.isoformat(), "count": count})

    customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)
    by_customer_id: dict[int, int] = {}
    for name, count in by_customer_name.items():
        customer = _resolve_customer_by_name_or_alias(name, customers_by_normalized, by_alias, customers_by_id)
        if customer:
            by_customer_id[customer.id] = by_customer_id.get(customer.id, 0) + count
    top_resolved_accounts = sorted(
        ({"customer_name": customers_by_id[cid].name, "count": n} for cid, n in by_customer_id.items()),
        key=lambda r: -r["count"],
    )[:10]

    return {
        "window_days": days,
        "total_resolved_90d": len(issues),
        "resolved_this_week": resolved_this_week,
        "resolved_this_month": resolved_this_month,
        "ttr_median_hours": round(statistics.median(ttr_hours), 1) if ttr_hours else None,
        "top_resolved_accounts": top_resolved_accounts,
        "weekly_trend": weekly_trend,
    }


_DEFECT_STATUSES = ("Defect / Enhancement submitted", "Critical Defect Submitted")


async def support_defect_dev_status(team: list[str]) -> list[dict]:
    """Real, live cross-check: every open DSD defect-status ticket assigned
    to the named support team, alongside its actual linked VMS dev bug's
    real status/assignee/sprint/fix_version — the exact manual investigation
    this function replaces (walked through live for the user: 15 of one
    engineer's defect tickets, 11 with a real linked bug, only 2 actually
    being worked).

    Deliberately excludes "Pending Upgrade" status — that population is
    already the job of releases.py::pending_upgrade_queue() (even if it only
    sees the subset that went through the local sys-admin Upgrade-case
    flow); this covers the still-open defect statuses that have no local
    ingestion path at all (confirmed live: 2 of 151 real "Defect /
    Enhancement submitted" tickets ever get locally mapped), so a live fetch
    is the only way to answer this accurately.

    A dedicated call, not folded into team_open_stats() — that function is
    the hot path for every Command Center/My Desk load; this is Release
    Intelligence's own on-demand cross-check and shouldn't add a second
    live-Jira round trip to a page loaded far more often.
    """
    assignee_list = ",".join(f'"{n}"' for n in team)
    status_list = ",".join(f'"{s}"' for s in _DEFECT_STATUSES)
    jql = f'project = "DSD" AND assignee in ({assignee_list}) AND status in ({status_list})'
    fields = "assignee,status,summary,issuelinks,customfield_10047,created,resolution"
    cache_key = ("defect_dev_status", tuple(sorted(team)))

    async def _fetch() -> list[dict]:
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        tickets: list[dict] = []
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            page_token: str | None = None
            while True:
                params = {"jql": jql, "maxResults": 100, "fields": fields}
                if page_token:
                    params["nextPageToken"] = page_token
                resp = await client.get(url, headers=_HEADERS, params=params)
                resp.raise_for_status()
                data = resp.json()
                tickets.extend(data.get("issues", []))
                if data.get("isLast", True):
                    break
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            now = datetime.now(timezone.utc)
            rows = []
            all_bug_refs: set[str] = set()
            for issue in tickets:
                f = issue["fields"]
                created = _parse_dt(f.get("created"))
                bug_refs = _extract_vms_links(f.get("issuelinks", []))
                all_bug_refs.update(bug_refs)
                rows.append({
                    "jira_ref": issue["key"],
                    "title": f.get("summary") or "",
                    "assignee_name": (f.get("assignee") or {}).get("displayName"),
                    "customer_name": _extract_customer_name(f.get("customfield_10047")),
                    "days_open": round((now - created).total_seconds() / 86400) if created else None,
                    "resolution": (f.get("resolution") or {}).get("name"),
                    "bug_ref": bug_refs[0] if bug_refs else None,
                })

            # Batch-fetch every distinct linked bug's real detail in one
            # more paginated search — mirrors _sync_vms_bug()'s field
            # parsing exactly, just for many issues at once instead of one.
            bugs_by_ref: dict[str, dict] = {}
            if all_bug_refs:
                bug_jql = f'key in ({",".join(sorted(all_bug_refs))})'
                bug_page_token: str | None = None
                while True:
                    params = {
                        "jql": bug_jql, "maxResults": 100,
                        "fields": "status,fixVersions,customfield_10010,assignee",
                    }
                    if bug_page_token:
                        params["nextPageToken"] = bug_page_token
                    resp = await client.get(url, headers=_HEADERS, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    for bug_issue in data.get("issues", []):
                        bf = bug_issue["fields"]
                        sprint = bf.get("customfield_10010")
                        if isinstance(sprint, list):
                            sprint = sprint[-1] if sprint else None
                        fix_versions = bf.get("fixVersions") or []
                        bug_assignee = bf.get("assignee")
                        bugs_by_ref[bug_issue["key"]] = {
                            "vms_ref": bug_issue["key"],
                            "status": bf.get("status", {}).get("name", ""),
                            "dev_assignee": bug_assignee.get("displayName") if bug_assignee else None,
                            "sprint_name": sprint.get("name") if sprint else None,
                            "fix_version": fix_versions[0]["name"] if fix_versions else None,
                        }
                    if data.get("isLast", True):
                        break
                    bug_page_token = data.get("nextPageToken")
                    if not bug_page_token:
                        break

        for row in rows:
            bug_ref = row.pop("bug_ref")
            row["bug"] = bugs_by_ref.get(bug_ref) if bug_ref else None
        return rows

    return await _dedup_fetch(cache_key, _fetch)


async def customer_case_stats(customer_name: str, months: int = 12, known_option_value: str | None = None) -> dict:
    """Real, live-Jira case stats for a single customer — bypasses the local
    `cases` table entirely, same "only manually-mapped tickets live there"
    reasoning as team_open_stats/team_resolved_stats. Confirmed live for a
    real customer (Saga Welco AS): the local table held 23 of 1,353 real
    tickets ever, 13 of them non-Closed against a real 95 currently open —
    a ~7x undercount on the exact number a support-signals/customer-drill
    screen is supposed to answer.

    The Customer field (customfield_10047) is a Jira single-select whose
    stored option VALUE is literally "Name|<id>" (not a separate name/id
    pair) — confirmed live. JQL's `~` contains-operator does not work on
    select-type fields at all (confirmed live: `cf[10047] ~ "Saga"` returns
    0 matches with no error, on a field known to have real matches), so an
    exact `cf[10047] = "..."` match is required — but the exact `|<id>`
    suffix isn't discoverable via any option-listing endpoint this token has
    permission for (`/field/{id}/context` and `/customField/{id}/option`
    both 403/404 under a non-admin token).

    Pass `known_option_value` (Customer.jira_customer_field_value, once
    discovered and persisted by the caller — see customers.py's
    case_summary()) to skip discovery entirely and go straight to the real
    query. Without it, falls back to discovering the real option string by
    scanning recent tickets that have the field populated (paginated,
    newest-first, bounded to ~20 pages) until _normalize_company_name()
    matches the target.

    That discovery fallback is NOT reliable as the sole mechanism long-term
    — confirmed live: a real, genuinely active customer (95 open tickets)
    intermittently returned matched=False a few hours after resolving
    cleanly, purely because *other* customers' tickets had since been
    updated more recently, pushing this one's out of the ~2000-ticket
    recency window the scan searches. The option value itself never
    changes once assigned (it's a fixed picklist option) — persisting it
    after the first successful discovery is what actually makes this
    reliable, not a longer scan window.

    Returns {"matched": bool, "jira_customer_value": str | None,
    "logged_months": int, "open_count": int, "by_case_type": {...},
    "by_priority": {...}, "oldest_days": int, "open_tickets": [...]}."""
    cache_key = ("customer_cases", _normalize_company_name(customer_name), months, known_option_value)

    async def _fetch() -> dict:
        target_norm = _normalize_company_name(customer_name)
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        option_value: str | None = known_option_value

        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            if option_value is None:
                page_token: str | None = None
                for _ in range(20):  # bounded scan — ~2000 tickets, newest-first
                    params = {
                        "jql": 'project = "DSD" AND customfield_10047 is not EMPTY ORDER BY updated DESC',
                        "maxResults": 100, "fields": "customfield_10047",
                    }
                    if page_token:
                        params["nextPageToken"] = page_token
                    resp = await client.get(url, headers=_HEADERS, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    for issue in data.get("issues", []):
                        name = _extract_customer_name(issue["fields"].get("customfield_10047"))
                        if name and _normalize_company_name(name) == target_norm:
                            option_value = issue["fields"]["customfield_10047"]["value"]
                            break
                    if option_value or data.get("isLast", True):
                        break
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break

            if option_value is None:
                return {
                    "matched": False, "jira_customer_value": None, "logged_months": 0,
                    "open_count": 0, "by_case_type": {}, "by_priority": {}, "oldest_days": 0,
                    "open_tickets": [], "monthly_counts": [], "top_topics": [],
                    "recurring_topics": [], "volume_spike": None,
                }

            base_jql = f'project = "DSD" AND cf[10047] = "{option_value}"'

            async def _fetch_all(jql: str, fields: str) -> list[dict]:
                out: list[dict] = []
                pt: str | None = None
                while True:
                    p = {"jql": jql, "maxResults": 100, "fields": fields}
                    if pt:
                        p["nextPageToken"] = pt
                    r = await client.get(url, headers=_HEADERS, params=p)
                    r.raise_for_status()
                    d = r.json()
                    out.extend(d.get("issues", []))
                    if d.get("isLast", True):
                        break
                    pt = d.get("nextPageToken")
                    if not pt:
                        break
                return out

            logged_issues = await _fetch_all(f"{base_jql} AND created >= -{months * 30}d", "summary,created,components")
            open_issues = await _fetch_all(
                f"{base_jql} AND statusCategory != Done",
                "summary,status,priority,labels,customfield_10014,created",
            )

        now = datetime.now(timezone.utc)
        by_case_type: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        open_tickets = []
        oldest_days = 0
        for issue in open_issues:
            f = issue["fields"]
            raw_status = f["status"]["name"]
            labels = f.get("labels") or []
            request_type = _extract_request_type(f.get("customfield_10014"))
            case_type = _map_type(raw_status, labels, request_type)
            priority = _map_priority((f.get("priority") or {}).get("name", "Severity 3"))
            created = _parse_dt(f.get("created"))
            days_open = (now - created).days if created else 0
            oldest_days = max(oldest_days, days_open)
            by_case_type[case_type] = by_case_type.get(case_type, 0) + 1
            by_priority[priority] = by_priority.get(priority, 0) + 1
            open_tickets.append({
                "jira_ref": issue["key"], "title": f.get("summary", ""),
                "priority": priority, "days_open": days_open,
            })

        # Real monthly volume + topic trend, from the same logged_issues
        # fetch already made for the count above — no second live-Jira
        # round trip. `components` is the real, ready-made topic signal
        # confirmed live against real DSD tickets (Voyages, EUETS, API,
        # Invoices, etc.) — far more specific than the coarse case_type
        # bucket, and needs no new classification logic.
        monthly_counts: dict[str, int] = {}
        topic_counts: dict[str, int] = {}
        for issue in logged_issues:
            lf = issue["fields"]
            created = _parse_dt(lf.get("created"))
            if created:
                month_key = created.strftime("%Y-%m")
                monthly_counts[month_key] = monthly_counts.get(month_key, 0) + 1
            for comp in lf.get("components", []):
                name = comp.get("name")
                if name:
                    topic_counts[name] = topic_counts.get(name, 0) + 1

        # Capped BEFORE deriving recurring_topics, not after — a customer
        # with dozens of real topics (a high-volume account like Saga Welco
        # AS, 342 tickets/year) would otherwise show "32 recurring topics"
        # in the text while only 8 rows are ever rendered, a real, caught
        # inconsistency between the two numbers.
        top_topics_full = sorted(
            [{"topic": t, "count": c} for t, c in topic_counts.items()],
            key=lambda x: -x["count"],
        )
        top_topics = top_topics_full[:8]
        recurring_topics = [t for t in top_topics if t["count"] >= 3]

        # Volume spike — the most recent real calendar month vs. the average
        # of the prior months in the same window. Needs at least 2 prior
        # months of real data to mean anything; a spike is only flagged
        # when the recent month is both a meaningful multiple of the prior
        # average AND a real, non-trivial count (avoids flagging noise like
        # "1 case last month vs 0 before").
        sorted_months = sorted(monthly_counts.keys())
        volume_spike = None
        if len(sorted_months) >= 3:
            recent_month = sorted_months[-1]
            recent_count = monthly_counts[recent_month]
            prior_months = sorted_months[:-1]
            prior_avg = sum(monthly_counts[m] for m in prior_months) / len(prior_months)
            if recent_count >= 3 and prior_avg > 0 and recent_count >= prior_avg * 1.5:
                volume_spike = {
                    "month": recent_month, "count": recent_count,
                    "prior_average": round(prior_avg, 1),
                }

        return {
            "matched": True,
            "jira_customer_value": option_value,
            "logged_months": len(logged_issues),
            "open_count": len(open_issues),
            "by_case_type": by_case_type,
            "by_priority": by_priority,
            "oldest_days": oldest_days,
            "open_tickets": sorted(open_tickets, key=lambda t: -t["days_open"]),
            "monthly_counts": [{"month": m, "count": monthly_counts[m]} for m in sorted_months],
            "top_topics": top_topics,
            "recurring_topics": recurring_topics,
            "volume_spike": volume_spike,
        }

    return await _dedup_fetch(cache_key, _fetch)


# Confirmed live: several auto-created Upgrade rows were unconditionally
# hardcoded to "PROD" even when the source ticket was explicitly about a
# TEST/DEV tenant (e.g. DSD-31674 "SFL-web-test move to the new AWS infra",
# DSD-31856 "TEST environment: Upgrade to match PROD version, refresh
# database") — the active board showed a TEST refresh as if it were a PROD
# upgrade. No structured environment field is fetched for these tickets
# (`_FIELDS` doesn't request `components`), so this is a title-keyword
# heuristic, same honesty bar as `_SSO_KEYWORD_PATTERN` — deliberately
# conservative: only overrides to TEST/DEV when the title mentions one of
# them WITHOUT also mentioning prod/production, since a title mentioning
# both (e.g. "upgrade production... we just upgraded test") is genuinely
# ambiguous and defaults to PROD rather than guessing.
_ENV_TEST_PATTERN = re.compile(r"\btest\b", re.IGNORECASE)
_ENV_DEV_PATTERN = re.compile(r"\bdev\b", re.IGNORECASE)
_ENV_PROD_PATTERN = re.compile(r"\bprod(uction)?\b", re.IGNORECASE)


def _detect_upgrade_environment(title: str, components: list[str] | None = None) -> str:
    """Component first — the real, authoritative signal (same
    _UPGRADE_COMPONENTS mapping sync_completed_upgrades() already uses) —
    falling back to a title-keyword guess only when no recognized
    component is set. Confirmed live this session: a real ticket (DSD-30865,
    component "TEST / DEV Upgrade") got auto-filed as PROD because its
    title ("Ref to case DSD-30185") carried no env keyword at all — the
    title-only heuristic had no real signal to work with even though the
    ticket carried one all along."""
    if components:
        for comp, env in _UPGRADE_COMPONENTS.items():
            if comp in components:
                return env
    if _ENV_PROD_PATTERN.search(title):
        return "PROD"
    if _ENV_TEST_PATTERN.search(title):
        return "TEST"
    if _ENV_DEV_PATTERN.search(title):
        return "DEV"
    return "PROD"


async def _refresh_upgrade_request_type(db, jira_ref: str, request_type: str | None) -> None:
    """Upgrade.request_type is otherwise only ever set once — at creation
    time in _ensure_upgrade_from_ticket() or via the Suggested-promotion/
    duplicate-fold logic — and never refreshed afterward, unlike
    Case.request_type, which _apply_case_update() already refreshes on
    every poll. Confirmed live this session: several real Upgrade rows
    stayed visible on the Kanban long after their linked ticket's real
    Jira classification moved away from genuine sys-admin (DSD-30695,
    DSD-28935, and others), because nothing ever re-checked — only found
    via a manual, on-demand drift check. Refreshing this on every regular
    poll means the EXISTING Kanban filter (pipeline_summary()'s
    request_type == sys-admin check) naturally, automatically drops a
    ticket the instant it stops qualifying — no more manual
    drift-check-and-cancel cycles needed for any ticket the poll still
    touches. Scoped to active (non-terminal) rows only — a Verified
    Done/Cancelled row's history shouldn't retroactively change."""
    result = await db.execute(
        select(Upgrade).where(Upgrade.jira_ref == jira_ref, Upgrade.stage.notin_(("Verified Done", "Cancelled")))
    )
    upgrade = result.scalar_one_or_none()
    if upgrade is not None and upgrade.request_type != request_type:
        upgrade.request_type = request_type


# Same element-wise parser as upgrade_supervision.py::_version_tuple /
# releases.py::_version_tuple — kept as its own small copy here rather than
# imported, matching the established per-layer convention (see either of
# those two docstrings for why).
_UPGRADE_VERSION_NUM = re.compile(r"\d+")


def _upgrade_version_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    parts = _UPGRADE_VERSION_NUM.findall(v)
    return tuple(int(p) for p in parts) if parts else None


async def _ensure_upgrade_from_ticket(
    db, jira_ref: str, customer_id: int, title: str = "", request_type: str | None = None,
    components: list[str] | None = None,
) -> None:
    """Auto-create an Upgrade pipeline row (stage=Requested) the moment a
    ticket is classified as an upgrade/sys-admin request with a resolved
    customer. Without this, a ticket can be correctly labeled case_type=
    Upgrade yet still be totally invisible on the actual Upgrade pipeline
    (Command Centre / Operations > Upgrades) — which is where this work is
    meant to be coordinated. `to_version` has no reliable structured source
    on the ticket itself, so it defaults to the current latest release (a
    real, useful starting guess) — expected to be corrected once someone
    reviews the card, same as any other manually-entered upgrade."""
    existing = await db.execute(select(Upgrade).where(Upgrade.jira_ref == jira_ref))
    if existing.scalar_one_or_none():
        return

    latest = await db.execute(select(Release).where(Release.is_latest == True))  # noqa: E712
    latest_release = latest.scalar_one_or_none()
    environment = _detect_upgrade_environment(title, components)

    # Confirmed live: without this check, every new ticket for a customer
    # who's already behind version spawns another parallel Requested row —
    # found 11 customers with 2-10 duplicate active rows all targeting the
    # same environment/version, none ever advanced past Requested. One
    # active tracking row per customer+environment is enough; the new
    # ticket is still fully visible via the Related Cases cross-reference
    # on that existing row (customer-scoped, not upgrade-row-scoped).
    active_existing = await db.execute(
        select(Upgrade).where(
            Upgrade.customer_id == customer_id,
            Upgrade.environment == environment,
            Upgrade.stage.notin_(("Verified Done", "Cancelled")),
        )
    )
    active_upgrade = active_existing.scalars().first()
    if active_upgrade:
        # A "Suggested" row (created by Release Intelligence's "Recommend
        # Upgrade" — a proactive nudge, not yet a real customer request) has
        # no jira_ref at all. When a genuine sys-admin ticket for the same
        # customer+environment shows up, this IS that suggestion turning
        # into the real thing — promote the row in place (attach the real
        # ticket, advance the stage) rather than silently suppressing the
        # new ticket the way an already-Requested duplicate would be.
        if active_upgrade.stage == "Suggested":
            active_upgrade.jira_ref = jira_ref
            active_upgrade.stage = "Requested"
            active_upgrade.request_type = request_type
            if latest_release and active_upgrade.to_version != latest_release.version:
                active_upgrade.to_version = latest_release.version
            db.add(AuditLog(
                actor="system", action="upgrade.suggestion_fulfilled", target_type="customer", target_id=str(customer_id),
                detail=f"Suggested upgrade fulfilled by real ticket {jira_ref}",
            ))
            return

        # A row anchored to a ticket that was never itself a genuine
        # sys-admin/upgrade-installation request (e.g. one created from the
        # Pending-Upgrade reconciliation pass, whose own request_type is
        # something else like "Support Request") gets RE-ANCHORED to a real
        # request-type ticket once one shows up, instead of just having its
        # request_type field quietly bumped while still pointing at the
        # wrong ticket. Confirmed live and wrong the old way: Sea Tank
        # Chartering AS's tracking row stayed pinned to DSD-30695 (Pending
        # Upgrade status, request_type "Support Request") while the real
        # ask, DSD-30857 (request_type "Upgrade or Installation Request",
        # which Jira itself links as literally *containing* DSD-30695), sat
        # suppressed underneath it — backwards from what a support engineer
        # needs to see and click through to. Only re-anchors when the
        # EXISTING row isn't already itself genuine — two equally-genuine
        # sys-admin tickets for the same customer+env still fold into
        # whichever was there first, unchanged below, to avoid churn.
        if request_type == _SYS_ADMIN_REQUEST_TYPE and active_upgrade.request_type != _SYS_ADMIN_REQUEST_TYPE:
            db.add(AuditLog(
                actor="system", action="upgrade.reanchored_to_genuine_request", target_type="customer", target_id=str(customer_id),
                detail=f"{active_upgrade.jira_ref} (request_type={active_upgrade.request_type or 'none'}) re-anchored to genuine request {jira_ref}",
            ))
            active_upgrade.jira_ref = jira_ref
            active_upgrade.request_type = request_type
            if latest_release and active_upgrade.to_version != latest_release.version:
                active_upgrade.to_version = latest_release.version
            return

        # Otherwise: a real duplicate of an already-genuine (or already
        # re-anchored) row — keep the existing jira_ref, just refresh
        # to_version so the one real tracking row doesn't go stale.
        if latest_release and active_upgrade.to_version != latest_release.version:
            active_upgrade.to_version = latest_release.version
        db.add(AuditLog(
            actor="system", action="upgrade.duplicate_suppressed", target_type="customer", target_id=str(customer_id),
            detail=f"{jira_ref} folded into existing {active_upgrade.jira_ref}",
        ))
        return

    # Before creating a fresh row, check whether the customer's real,
    # live-synced tenant version already meets or exceeds what this row
    # would target — confirmed live this is a real, repeating loop without
    # it: cancelling a superseded row (see upgrade_supervision.py::
    # superseded_upgrades) just caused the very next poll to auto-create a
    # REPLACEMENT row from a different real open sys-admin ticket for the
    # SAME customer, immediately superseded on arrival too (Saga Welco AS:
    # DSD-28511 auto-created here targeting 8.30.1-R while their real
    # synced PROD tenant was already 8.30.2-R, confirmed via CustomerTenantInfo).
    # A customer with N real open sys-admin tickets and a stale
    # latest_release would otherwise respawn a stale row N times, one
    # cancel at a time. Skips creation entirely (not "create then
    # auto-cancel") so the ticket never briefly appears as active work.
    if latest_release:
        tenant_result = await db.execute(
            select(CustomerTenantInfo).where(
                CustomerTenantInfo.customer_id == customer_id,
                CustomerTenantInfo.environment == environment,
            )
        )
        tenant_info = tenant_result.scalar_one_or_none()
        real_vt = _upgrade_version_tuple(tenant_info.release) if tenant_info else None
        target_vt = _upgrade_version_tuple(latest_release.version)
        if real_vt is not None and target_vt is not None and real_vt >= target_vt:
            db.add(AuditLog(
                actor="system", action="upgrade.already_satisfied_skipped",
                target_type="customer", target_id=str(customer_id),
                detail=f"{jira_ref} wants {latest_release.version} but real synced tenant is already {tenant_info.release}",
            ))
            return

    db.add(Upgrade(
        customer_id=customer_id,
        jira_ref=jira_ref,
        environment=environment,
        to_version=latest_release.version if latest_release else "TBD",
        upgrade_type="Small",
        stage="Requested",
        source="Sys-admin request (auto)",
        request_type=request_type,
    ))
    db.add(AuditLog(
        actor="system", action="upgrade.auto_started", target_type="customer", target_id=str(customer_id),
        detail=f"from {jira_ref}",
    ))


# Unlike Upgrade tickets, there's no authoritative Jira Request Type for an
# SSO request (confirmed live: the 2 real SSO-titled tickets carry two
# different, non-distinctive Request Types) — this is a title-keyword
# heuristic instead. Confirmed precise against real data: matches exactly
# those 2 tickets and zero others across all 90 Support-type cases.
_SSO_KEYWORD_PATTERN = re.compile(r"\bsso\b|single sign|saml", re.IGNORECASE)


async def _ensure_sso_from_ticket(db, jira_ref: str, customer_id: int) -> None:
    """Auto-start SSO onboarding (stage=Not Started) the moment a real
    customer ticket's title mentions SSO/Single Sign-On/SAML — mirrors
    _ensure_upgrade_from_ticket()'s "resolve a customer, then just create
    the real row" precedent. Since the detection signal here is a heuristic
    (not an authoritative field), the created row is tagged with its source
    ticket rather than looking indistinguishable from a manually-logged one."""
    existing = await db.execute(select(SSOOnboarding).where(SSOOnboarding.customer_id == customer_id))
    if existing.scalar_one_or_none():
        return  # one record per customer — already tracked, don't duplicate
    db.add(SSOOnboarding(
        customer_id=customer_id,
        stage="Not Started",
        source_jira_ref=jira_ref,
        notes=f"Auto-started from {jira_ref} (title mentioned SSO/SAML).",
    ))
    db.add(AuditLog(
        actor="system", action="sso.auto_started", target_type="customer", target_id=str(customer_id),
        detail=f"from {jira_ref}",
    ))


async def _ensure_training_gap_from_ticket(db, jira_ref: str, customer_id: int, title: str) -> None:
    """Mirrors _ensure_sso_from_ticket()'s exact "resolve a customer, then
    just create the real row, tag it with its source ticket" shape — for
    the real, already-classified case_type == "Training Gap" tickets
    confirmed live this session (e.g. DSD-26357, "FuelEU Compliance and
    Smarter Voyage Management – Here's What's New"). Unlike SSOOnboarding,
    TrainingGap has no one-per-customer constraint (a customer can have
    multiple real gaps), so the dedup check is per-ticket, not per-customer
    — the same real Training Gap ticket should never spawn two rows if the
    poll reconciles it again."""
    from app.services.training_priority import guess_training_area

    existing = await db.execute(select(TrainingGap).where(TrainingGap.source_case_ref == jira_ref))
    if existing.scalar_one_or_none():
        return
    db.add(TrainingGap(
        customer_id=customer_id,
        area=guess_training_area(title),
        description=title,
        source_case_ref=jira_ref,
    ))
    db.add(AuditLog(
        actor="system", action="training_gap.auto_logged", target_type="customer", target_id=str(customer_id),
        detail=f"from {jira_ref}: {title}",
    ))


async def _apply_case_update(
    db, case: Case, fields: dict, vms_client: httpx.AsyncClient,
    customers_by_id: dict | None = None, customers_by_normalized: dict | None = None,
    vms_prefetch: dict[str, dict | None] | None = None,
) -> None:
    raw_status = fields.get("status", {}).get("name", "")
    labels: list[str] = fields.get("labels") or []
    # Sequential call (never inside asyncio.gather with this same `db`) —
    # safe to use the DB-backed cache here too, which has the added benefit
    # of keeping CaseComment warm for every locally-mapped case automatically
    # as part of the regular 5-minute poll, not just when a bulk aggregate
    # function happens to run.
    comments: list[dict] = await _cached_comments(db, vms_client, case.jira_ref, fields.get("comment"), case_id=case.id)
    assignee = fields.get("assignee")
    customer_name = _extract_customer_name(fields.get("customfield_10047"))
    request_type = _extract_request_type(fields.get("customfield_10014"))

    # Confirmed live this was a real gap: every other field on this row gets
    # kept live on every poll, but title was only ever set at creation
    # (Case(...) construction, 3 call sites) — never refreshed here. A
    # ticket whose Jira summary changes after first sync (confirmed real:
    # DSD-31688 went from an upgrade-sounding title to an unrelated balance
    # defect) kept a permanently stale, misleading local title forever,
    # which is what led to a real bad manual Upgrade row being created
    # against it.
    new_title = fields.get("summary")
    if new_title:
        case.title = new_title

    case.raw_status = raw_status or None
    new_status = _map_status(raw_status)
    if new_status != case.status:
        case.status_changed_at = datetime.utcnow()
        db.add(AuditLog(
            actor="system", action="case.status_changed", target_type="case",
            target_id=case.jira_ref, detail=f"{case.status} -> {new_status}",
        ))
    case.status = new_status

    old_priority = case.priority
    new_priority = _map_priority(fields.get("priority", {}).get("name", "Severity 3"))
    if new_priority == "High" and old_priority != "High":
        db.add(AuditLog(
            actor="system", action="case.high_priority", target_type="case",
            target_id=case.jira_ref, detail=f"{old_priority} -> {new_priority}",
        ))
    case.priority = new_priority

    case.days_open = _days_from_created(fields.get("created", ""))
    case.case_type = _map_type(raw_status, labels, request_type)
    case.request_type = request_type

    old_assigned_to = case.assigned_to
    new_assigned_to = assignee.get("displayName") if assignee else None
    if new_assigned_to != old_assigned_to:
        db.add(AuditLog(
            actor="system", action="case.assigned_to_changed", target_type="case",
            target_id=case.jira_ref, detail=f"{old_assigned_to or 'Unassigned'} -> {new_assigned_to or 'Unassigned'}",
        ))
    case.assigned_to = new_assigned_to
    case.comment_count = (fields.get("comment") or {}).get("total", 0)
    case.jira_customer_name = customer_name

    # Cases only ever get matched to a customer_id once, at first sync — if
    # that assignment was ever wrong (confirmed live: 2 real cases traced
    # back to arbitrary demo-seed jira_ref-to-customer links that happened
    # to collide with real Jira tickets belonging to a *different* real
    # customer), nothing ever re-checked it against the authoritative
    # jira_customer_name this poller has been correctly capturing all
    # along. Auto-correct here, but only to an exact/normalized-name match
    # — never a fuzzy guess — and leave an audit trail.
    if customer_name and customers_by_id and customers_by_normalized:
        current = customers_by_id.get(case.customer_id)
        if current:
            normalized_real = _normalize_company_name(customer_name)
            if _normalize_company_name(current.name) != normalized_real:
                correct = customers_by_normalized.get(normalized_real)
                if correct and correct.id != case.customer_id:
                    db.add(AuditLog(
                        actor="system", action="case.customer_corrected", target_type="case",
                        target_id=case.jira_ref,
                        detail=f"{current.name} -> {correct.name} (per Jira Customer field)",
                    ))
                    case.customer_id = correct.id

    if case.case_type == "Upgrade":
        await _ensure_upgrade_from_ticket(
            db, case.jira_ref, case.customer_id, fields.get("summary", ""), request_type,
            [c["name"] for c in fields.get("components", [])],
        )

    # Jira is authoritative for when the ticket actually opened — a case
    # seeded/demo-created locally has a created_at that reflects when the
    # *row* was inserted, not the real ticket age, which corrupts every
    # duration metric (TTFR/TTR/first-move) derived from it.
    jira_created = _parse_dt(fields.get("created"))
    if jira_created:
        case.created_at = jira_created

    resolutiondate = _parse_dt(fields.get("resolutiondate"))
    if resolutiondate:
        case.resolved_at = resolutiondate

    first_reply = _first_public_reply_at(comments)
    if first_reply and not case.first_public_reply_at:
        case.first_public_reply_at = first_reply

    ttfr_hours, ttfr_breached = _extract_ttfr(fields.get("customfield_10054"))
    case.ttfr_hours = ttfr_hours
    case.ttfr_breached = ttfr_breached

    mention = _last_human_mention(comments)
    if mention:
        name, mentioned_at = mention
        is_new_mention = case.last_mention_at is None or mentioned_at > case.last_mention_at
        if is_new_mention:
            case.last_mention_name = name
            case.last_mention_at = mentioned_at
            if name == TEAM_LEAD and case.escalated_at is None:
                case.escalated_at = mentioned_at
                db.add(AuditLog(
                    actor="system", action="case.escalated", target_type="case",
                    target_id=case.jira_ref, detail=f"mentioned {name}",
                ))

    vms_keys = _extract_vms_links(fields.get("issuelinks", []))
    linked_refs: list[str] = []
    for vms_ref in vms_keys:
        bug = await _sync_vms_bug(vms_client, db, vms_ref, vms_prefetch)
        if bug:
            linked_refs.append(bug.jira_ref)
    if linked_refs:
        case.linked_vms_ref = linked_refs[0]  # unchanged, backward-compat
        case.linked_vms_refs = ",".join(linked_refs)

    related_case_keys = _extract_related_case_keys(fields.get("issuelinks", []), case.jira_ref)
    case.related_case_refs = ",".join(related_case_keys) if related_case_keys else None

    if _SSO_KEYWORD_PATTERN.search(fields.get("summary", "")):
        await _ensure_sso_from_ticket(db, case.jira_ref, case.customer_id)

    if case.case_type == "Training Gap":
        await _ensure_training_gap_from_ticket(db, case.jira_ref, case.customer_id, fields.get("summary", ""))


async def ensure_case_synced(db, jira_ref: str) -> Case | None:
    """On-demand, single-issue live fetch + lazy local sync — the same
    'resolve customer, then create the real row' precedent as
    poll_and_upsert()'s first pass and the Jira-Mapping auto-bridge, just
    triggered by a user opening a not-yet-synced ticket instead of waiting
    for the next 5-minute poll. Reuses _apply_case_update() for the actual
    population, so a lazily-created case ends up identical to one that
    arrived via a normal poll — mentions, escalation, related-case-refs,
    VMS-bug-linkage, all of it, not a second/weaker representation.

    Returns None if the ticket doesn't exist in Jira, or its customer can't
    be resolved (the same rare edge case the Jira-Mapping page already
    surfaces honestly elsewhere) — never fabricates a match."""
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{jira_ref}"
    async with httpx.AsyncClient(auth=_auth(), timeout=20) as client:
        try:
            resp = await client.get(url, headers=_HEADERS, params={"fields": _FIELDS})
            resp.raise_for_status()
        except Exception as exc:
            logger.warning("ensure_case_synced: live fetch failed for %s: %s", jira_ref, exc)
            return None

        fields = resp.json().get("fields", {})
        customer_name = _extract_customer_name(fields.get("customfield_10047"))
        customers_by_id, customers_by_normalized, by_alias = await _build_customer_match_maps(db)
        resolved = _resolve_customer_by_name_or_alias(customer_name, customers_by_normalized, by_alias, customers_by_id)
        if not resolved:
            return None

        raw_status = fields.get("status", {}).get("name", "")
        case = Case(
            customer_id=resolved.id, jira_ref=jira_ref, title=fields.get("summary", ""),
            case_type="Support", environment="PROD", status=_map_status(raw_status),
        )
        db.add(case)
        await _apply_case_update(db, case, fields, client, customers_by_id, customers_by_normalized)
        await db.commit()
        return case


def _comment_rows_to_entries(rows: list[CaseComment]) -> list[dict]:
    return [
        {"author": r.author, "created": r.created, "text": r.text, "public": r.public}
        for r in sorted(rows, key=lambda r: r.created or datetime.min)
    ]


async def fetch_case_activity(db, case_id: int, jira_ref: str) -> list[dict] | None:
    """Real Jira comment/activity history for one ticket — the actual
    conversation, not Sedna-Ops' own AuditLog trail (that stays on the
    separate Timeline tab, unchanged).

    Thin wrapper over the shared _cached_comments() core (also used by
    every bulk aggregate function in this file) — cached in CaseComment,
    keyed by jira_ref (case_id is stored as a back-reference only, so a
    ticket cached here by a bulk function before it ever had a local Case
    row still gets recognized once one exists). Old comments never change,
    so this does the cheapest possible Jira call first — GET
    .../issue/{ref}?fields=comment, a real `total` count with no extra
    round trip — before ever falling through to a full fetch. This is the
    "query latest, do nothing if no news" behavior requested — most
    tab-opens after the first do zero further Jira comment fetches.

    Returns None only when there's no cache to fall back on AND the live
    fetch failed — a transient Jira hiccup on an already-cached ticket still
    returns the real cached history rather than erroring the panel."""
    async def _stored_entries() -> list[dict]:
        stored = (await db.execute(select(CaseComment).where(CaseComment.jira_ref == jira_ref))).scalars().all()
        return _comment_rows_to_entries(stored)

    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/issue/{jira_ref}"
    async with httpx.AsyncClient(auth=_auth(), timeout=20) as client:
        try:
            resp = await client.get(url, headers=_HEADERS, params={"fields": "comment"})
            resp.raise_for_status()
            embedded = resp.json().get("fields", {}).get("comment") or {}
        except Exception as exc:
            logger.warning("fetch_case_activity: freshness check failed for %s: %s", jira_ref, exc)
            entries = await _stored_entries()
            return entries or None

        try:
            await _cached_comments(db, client, jira_ref, embedded, case_id=case_id)
        except Exception as exc:
            logger.warning("fetch_case_activity: full fetch failed for %s: %s", jira_ref, exc)
            entries = await _stored_entries()
            return entries or None

    return await _stored_entries()


async def _upsert_jira_unmatched(
    db, key: str, fields: dict, ticket_case_type: str, customer_name: str | None, request_type: str | None,
) -> None:
    """Create or refresh a JiraUnmatched row for a ticket with no local Case
    (or no resolvable customer). Factored out of the first poll pass so the
    third (Pending Upgrade) pass can reuse it instead of duplicating it."""
    title = fields.get("summary", "")
    issue_type = fields.get("issuetype", {}).get("name", "")
    existing = await db.execute(select(JiraUnmatched).where(JiraUnmatched.jira_ref == key))
    unmatched = existing.scalar_one_or_none()
    if unmatched is None:
        db.add(JiraUnmatched(
            jira_ref=key,
            title=title,
            issue_type=issue_type,
            case_type=ticket_case_type,
            priority=_map_priority(fields.get("priority", {}).get("name", "Severity 3")),
            labels=",".join(fields.get("labels") or []),
            days_open=_days_from_created(fields.get("created", "")),
            jira_customer_name=customer_name,
            request_type=request_type,
            first_seen_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        ))
    else:
        unmatched.last_seen_at = datetime.utcnow()
        unmatched.days_open = _days_from_created(fields.get("created", ""))
        unmatched.jira_customer_name = customer_name
        unmatched.request_type = request_type
        unmatched.case_type = ticket_case_type


def _resolve_customer_by_name_or_alias(
    customer_name: str | None,
    customers_by_normalized: dict[str, Customer],
    by_alias: dict[str, int],
    customers_by_id: dict[int, Customer],
) -> Customer | None:
    """Exact/normalized name match first; CustomerNameAlias only as a
    last-resort fallback (mirrors routers/upgrades.py's established
    precedence) — never overrides an already-successful direct match."""
    if not customer_name:
        return None
    customer = customers_by_normalized.get(_normalize_company_name(customer_name))
    if customer is not None:
        return customer
    alias_customer_id = by_alias.get(customer_name.strip().lower())
    return customers_by_id.get(alias_customer_id) if alias_customer_id else None


# How often poll_and_upsert()'s three main loops explicitly yield the event
# loop (see the `asyncio.sleep(0)` calls below) — see that comment for why.
_POLL_YIELD_EVERY = 10


async def poll_and_upsert() -> dict[str, int]:
    """
    Sync open DSD Support tickets into the local cases table.
    Returns {updated, skipped, errors}.
    """
    if not settings.jira_enabled:
        logger.debug("Jira polling disabled — set JIRA_BASE_URL + JIRA_API_TOKEN")
        return {"updated": 0, "skipped": 0, "errors": 0}

    try:
        raw = await _fetch_raw()
    except httpx.HTTPStatusError as exc:
        logger.error("Jira HTTP %s", exc.response.status_code)
        return {"updated": 0, "skipped": 0, "errors": 1}
    except Exception as exc:
        logger.error("Jira fetch failed: %s", exc)
        return {"updated": 0, "skipped": 0, "errors": 1}

    updated = skipped = 0
    support_case_created = 0
    async with AsyncSessionLocal() as db, httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as vms_client:
        all_customers = (await db.execute(select(Customer))).scalars().all()
        customers_by_id = {c.id: c for c in all_customers}
        customers_by_normalized: dict[str, Customer] = {}
        for c in all_customers:
            norm = _normalize_company_name(c.name)
            # Same collision guard as the upgrade sync: two different real
            # customers normalizing to the same string means neither is a
            # safe auto-correction target.
            customers_by_normalized[norm] = None if norm in customers_by_normalized else c  # type: ignore[assignment]

        # CustomerNameAlias was previously only consulted by the separate
        # upgrade-sync path (routers/upgrades.py) — confirmed live this never
        # reached the general poll, so real aliases already on file (KGJS,
        # White Lake Shipping Ltd -> Balena, etc.) had zero effect on Case
        # matching or the Support-ticket auto-bridge. Wired in here too, at
        # the same fallback precedence already established there (exact/
        # normalized match first, alias only when both fail).
        aliases = (await db.execute(select(CustomerNameAlias))).scalars().all()
        by_alias: dict[str, int] = {a.alias_name.strip().lower(): a.customer_id for a in aliases}

        # Prewarm the two things that were showing up as dozens of
        # sequential live-Jira round-trips per poll (confirmed live this
        # session as the direct cause of poll_and_upsert() routinely taking
        # 3.5-4 minutes against its own 5-minute schedule, which stalled
        # concurrent requests like Command Center's scorecard/daily-ops):
        # comments (via the already-proven _cached_comments_batch(), used
        # elsewhere in this file) and linked VMS bugs (via
        # _prefetch_vms_bug_fields() above). Both do exactly one batched DB
        # read + one concurrent Jira fetch + one batched DB write — `db` is
        # never touched from more than one coroutine at a time. Every
        # sequential _apply_case_update() call below is unchanged; it just
        # now finds a warm cache instead of doing its own live fetch.
        await _cached_comments_batch(db, vms_client, raw)
        raw_vms_refs = {ref for issue in raw for ref in _extract_vms_links(issue["fields"].get("issuelinks", []))}
        raw_vms_prefetch = await _prefetch_vms_bug_fields(vms_client, db, raw_vms_refs)

        for _i, issue in enumerate(raw):
            # Confirmed live this session: even with the prefetch batching
            # above, a poll processing hundreds of tickets back-to-back on
            # this app's single uvicorn worker (one process, one event
            # loop, shared with every HTTP request) can still leave a
            # concurrent request — e.g. Command Center's scorecard —
            # waiting ~47s for its turn, well past the frontend's 30s
            # timeout. A bare `await` on I/O should yield control back to
            # the loop on its own, but a long, tight run of many small
            # ready-callbacks in a row can still crowd out other pending
            # tasks in practice. `asyncio.sleep(0)` is the standard,
            # zero-cost way to force an explicit yield point without
            # actually pausing this loop.
            if _i % _POLL_YIELD_EVERY == 0:
                await asyncio.sleep(0)
            key = issue["key"]
            fields = issue["fields"]
            raw_status = fields.get("status", {}).get("name", "")
            labels: list[str] = fields.get("labels") or []
            assignee = fields.get("assignee")
            customer_name = _extract_customer_name(fields.get("customfield_10047"))
            request_type = _extract_request_type(fields.get("customfield_10014"))
            await _refresh_upgrade_request_type(db, key, request_type)

            result = await db.execute(select(Case).where(Case.jira_ref == key))
            case = result.scalar_one_or_none()

            if case is None:
                ticket_case_type = _map_type(raw_status, labels, request_type)
                resolved = _resolve_customer_by_name_or_alias(
                    customer_name, customers_by_normalized, by_alias, customers_by_id
                )

                # Support/Defect/Training Gap tickets have no purpose-built
                # pipeline table the way Upgrade (Upgrade) and SSO
                # (SSOOnboarding) do — Case is the only local representation
                # for them, so a resolved customer is enough to create the
                # real row directly, mirroring the third (Pending Upgrade)
                # pass's exact pattern below instead of leaving it in
                # jira_unmatched forever (confirmed live: 82 of 124 unmatched
                # refs already had a resolvable customer name and just sat
                # there until someone manually clicked "Assign").
                if resolved and ticket_case_type != "Upgrade":
                    existing_unmatched = await db.execute(
                        select(JiraUnmatched).where(JiraUnmatched.jira_ref == key)
                    )
                    unmatched_row = existing_unmatched.scalar_one_or_none()
                    if unmatched_row is not None and unmatched_row.dismissed:
                        # A human explicitly dismissed this ref — respect
                        # that decision, don't resurrect it as a Case.
                        unmatched_row.last_seen_at = datetime.utcnow()
                        unmatched_row.days_open = _days_from_created(fields.get("created", ""))
                        skipped += 1
                        continue

                    new_case = Case(
                        customer_id=resolved.id,
                        jira_ref=key,
                        title=fields.get("summary", ""),
                        case_type=ticket_case_type,
                        environment="PROD",
                        # Set up front so _apply_case_update's status-change
                        # diff doesn't fire a spurious audit entry for a case
                        # that was never previously "Active".
                        status=_map_status(raw_status),
                    )
                    db.add(new_case)
                    await _apply_case_update(db, new_case, fields, vms_client, customers_by_id, customers_by_normalized, raw_vms_prefetch)
                    if unmatched_row is not None:
                        await db.delete(unmatched_row)
                    support_case_created += 1
                    continue

                await _upsert_jira_unmatched(db, key, fields, ticket_case_type, customer_name, request_type)

                # No local Case yet, but if the ticket is an upgrade/sys-admin
                # request AND Jira already has a real customer on it (e.g. the
                # user triaged it directly in Jira), it can still get a real
                # Upgrade pipeline row now — no need to wait for someone to
                # separately click "Assign to customer" on this screen too.
                if ticket_case_type == "Upgrade" and resolved:
                    await _ensure_upgrade_from_ticket(
                        db, key, resolved.id, fields.get("summary", ""), request_type,
                        [c["name"] for c in fields.get("components", [])],
                    )

                # Same reasoning, orthogonal signal — a ticket can be
                # classified anything and still separately mention SSO.
                if _SSO_KEYWORD_PATTERN.search(fields.get("summary", "")) and resolved:
                    await _ensure_sso_from_ticket(db, key, resolved.id)

                if ticket_case_type == "Training Gap" and resolved:
                    await _ensure_training_gap_from_ticket(db, key, resolved.id, fields.get("summary", ""))

                skipped += 1
                continue

            await _apply_case_update(db, case, fields, vms_client, customers_by_id, customers_by_normalized, raw_vms_prefetch)
            updated += 1

        # Second pass: tickets that flipped to Done since the last poll no
        # longer appear in the query above at all, so their local Case row
        # would otherwise be stuck at its last-seen open status forever with
        # resolved_at never set. Only reconciles cases we already matched —
        # a resolved ticket support never touched locally isn't worth
        # surfacing as a new unmatched row.
        resolved_updated = 0
        try:
            resolved_raw = await _fetch_recently_resolved()
        except Exception as exc:
            logger.error("Jira resolved-ticket fetch failed: %s", exc)
            resolved_raw = []

        # Same prewarm as the first pass, above — see that comment.
        await _cached_comments_batch(db, vms_client, resolved_raw)
        resolved_vms_refs = {ref for issue in resolved_raw for ref in _extract_vms_links(issue["fields"].get("issuelinks", []))}
        resolved_vms_prefetch = await _prefetch_vms_bug_fields(vms_client, db, resolved_vms_refs)

        for _i, issue in enumerate(resolved_raw):
            if _i % _POLL_YIELD_EVERY == 0:  # see the first pass's comment above
                await asyncio.sleep(0)
            key = issue["key"]
            fields = issue["fields"]
            await _refresh_upgrade_request_type(db, key, _extract_request_type(fields.get("customfield_10014")))
            result = await db.execute(select(Case).where(Case.jira_ref == key))
            case = result.scalar_one_or_none()
            if case is None:
                continue
            await _apply_case_update(db, case, fields, vms_client, customers_by_id, customers_by_normalized, resolved_vms_prefetch)
            resolved_updated += 1

        # Third pass: "Pending Upgrade" is Done-category but never carries a
        # resolutiondate (confirmed live), so it matches neither the raw
        # open-ticket query above nor the resolved-ticket query just above
        # it — without this, a ticket that reaches this status is frozen
        # forever, including its VMS bug linkage. Reconciles cases already
        # matched, AND (confirmed live: 46 of 48 real Pending Upgrade
        # tickets have no local Case row at all) creates a real Case for any
        # ticket that resolves to a real customer, so this genuinely-real,
        # already-fixed-and-waiting work stops being invisible everywhere in
        # Sedna Ops. Falls back to JiraUnmatched (not silently dropped) when
        # the customer can't be resolved.
        pending_upgrade_reconciled = 0
        pending_upgrade_created = 0
        pending_upgrade_unmatched = 0
        try:
            pending_upgrade_raw = await _fetch_pending_upgrade()
        except Exception as exc:
            logger.error("Jira pending-upgrade fetch failed: %s", exc)
            pending_upgrade_raw = []

        # Same prewarm as the first pass, above — see that comment.
        await _cached_comments_batch(db, vms_client, pending_upgrade_raw)
        pending_vms_refs = {ref for issue in pending_upgrade_raw for ref in _extract_vms_links(issue["fields"].get("issuelinks", []))}
        pending_vms_prefetch = await _prefetch_vms_bug_fields(vms_client, db, pending_vms_refs)

        for _i, issue in enumerate(pending_upgrade_raw):
            if _i % _POLL_YIELD_EVERY == 0:  # see the first pass's comment above
                await asyncio.sleep(0)
            key = issue["key"]
            fields = issue["fields"]
            request_type = _extract_request_type(fields.get("customfield_10014"))
            await _refresh_upgrade_request_type(db, key, request_type)

            result = await db.execute(select(Case).where(Case.jira_ref == key))
            case = result.scalar_one_or_none()
            if case is not None:
                await _apply_case_update(db, case, fields, vms_client, customers_by_id, customers_by_normalized, pending_vms_prefetch)
                pending_upgrade_reconciled += 1
                continue

            raw_status = fields.get("status", {}).get("name", "")
            labels: list[str] = fields.get("labels") or []
            customer_name = _extract_customer_name(fields.get("customfield_10047"))
            ticket_case_type = _map_type(raw_status, labels, request_type)
            resolved = _resolve_customer_by_name_or_alias(
                customer_name, customers_by_normalized, by_alias, customers_by_id
            )

            if resolved:
                new_case = Case(
                    customer_id=resolved.id,
                    jira_ref=key,
                    title=fields.get("summary", ""),
                    case_type=ticket_case_type,
                    environment="PROD",
                    # Set up front so _apply_case_update's status-change diff
                    # doesn't fire a spurious audit entry for a case that was
                    # never previously "Active".
                    status=_map_status(raw_status),
                )
                db.add(new_case)
                await _apply_case_update(db, new_case, fields, vms_client, customers_by_id, customers_by_normalized, pending_vms_prefetch)
                pending_upgrade_created += 1
            else:
                await _upsert_jira_unmatched(db, key, fields, ticket_case_type, customer_name, request_type)
                pending_upgrade_unmatched += 1

        await db.commit()

    logger.info(
        "Jira poll done — updated=%d skipped=%d resolved_reconciled=%d pending_upgrade_reconciled=%d "
        "pending_upgrade_created=%d pending_upgrade_unmatched=%d support_case_created=%d",
        updated, skipped, resolved_updated, pending_upgrade_reconciled,
        pending_upgrade_created, pending_upgrade_unmatched, support_case_created,
    )
    return {
        "updated": updated, "skipped": skipped, "errors": 0,
        "resolved_reconciled": resolved_updated,
        "pending_upgrade_reconciled": pending_upgrade_reconciled,
        "pending_upgrade_created": pending_upgrade_created,
        "pending_upgrade_unmatched": pending_upgrade_unmatched,
        "support_case_created": support_case_created,
    }


# Real upgrade-tracking tickets are flagged with a Jira *component* —
# "PROD Upgrade" / "TEST / DEV Upgrade" — confirmed live and durable
# (unlike the "Pending Upgrade" *status*, which turned out to mean "a fix
# is available but the customer hasn't upgraded to receive it yet", not
# "this ticket is itself an upgrade project" — components stay on the
# ticket regardless of status, so they're the correct signal here).
_UPGRADE_COMPONENTS = {"PROD Upgrade": "PROD", "TEST / DEV Upgrade": "TEST"}
_UPGRADE_FIELDS = "summary,status,resolutiondate,created,customfield_10047,components"

_VERSION_PATTERN = re.compile(r"\b\d+\.\d+(?:\.\d+)?\b")

_COMPANY_SUFFIXES = re.compile(
    r"\b(ltd|limited|llc|gmbh|inc|incorporated|corp|corporation|co|company|"
    r"as|a s|sa|s a|bv|b v|kg|srl|plc|nv|oy|ab|aps)\b\.?",
    re.I,
)


def _normalize_company_name(name: str) -> str:
    """Exact-match-only normalization (no fuzzy ratio) — lowercase, strip
    punctuation, drop common legal suffixes. Two names that normalize the
    same are treated as the same company; anything less than that is left
    unmatched rather than guessed."""
    value = name.lower()
    value = re.sub(r"[^a-z0-9 ]", " ", value)
    value = _COMPANY_SUFFIXES.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()


async def resolve_customer_contacts(customer_ids: list[int], db) -> list[dict]:
    """Real Jira Service Management contacts for a set of customers — the
    data-gathering half of a customer broadcast (e.g. a maintenance-window
    notice), confirmed to recur every 2-3 months. No send capability exists
    or is planned here; this only assembles who to actually contact.

    Confirmed live: email exposure through Jira's API is PARTIAL by design —
    only genuine JSM portal-customer accounts show a real emailAddress;
    internal/licensed-type accounts on the customer's side never do,
    whether looked up via organization membership or an issue's reporter
    field (checked both — same restriction either way, so there's no
    fallback query that closes this gap). Callers should surface
    email_count vs member_count so a human knows which customers need
    manual contact-sourcing rather than silently under-notifying.
    """
    customers_result = await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))
    customers = customers_result.scalars().all()

    async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
        base = f"{settings.jira_base_url.rstrip('/')}/rest/servicedeskapi"

        # Fetch every real Organization once (small, ~60 total) rather than
        # searching per-customer — no server-side search-by-name endpoint
        # exists for this resource.
        orgs: list[dict] = []
        start = 0
        while True:
            resp = await client.get(f"{base}/organization", headers=_HEADERS, params={"limit": 50, "start": start})
            resp.raise_for_status()
            data = resp.json()
            orgs.extend(data.get("values", []))
            if data.get("isLastPage", True):
                break
            start += 50
        orgs_by_normalized_name = {_normalize_company_name(o["name"]): o for o in orgs}

        async def _resolve_one(customer: Customer) -> dict:
            org = orgs_by_normalized_name.get(_normalize_company_name(customer.name))
            if not org:
                return {
                    "customer_id": customer.id, "customer_name": customer.name,
                    "jira_org_matched": False, "org_name": None,
                    "contacts": [], "email_count": 0, "member_count": 0,
                }
            resp = await client.get(f"{base}/organization/{org['id']}/user", headers=_HEADERS, params={"limit": 50})
            resp.raise_for_status()
            members = resp.json().get("values", [])
            contacts = [{"name": m.get("displayName"), "email": m.get("emailAddress")} for m in members]
            return {
                "customer_id": customer.id, "customer_name": customer.name,
                "jira_org_matched": True, "org_name": org["name"],
                "contacts": contacts,
                "email_count": sum(1 for c in contacts if c["email"]),
                "member_count": len(contacts),
            }

        return list(await asyncio.gather(*(_resolve_one(c) for c in customers)))


def _extract_target_version(summary: str) -> str | None:
    match = _VERSION_PATTERN.search(summary or "")
    return match.group(0) if match else None


async def _fetch_upgrade_tickets() -> list[dict]:
    jql = (
        'project = "DSD" AND component in ("PROD Upgrade", "TEST / DEV Upgrade") '
        'AND status = "Resolved" ORDER BY resolutiondate DESC'
    )
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    issues: list[dict] = []
    page_token: str | None = None
    async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
        while True:
            params = {"jql": jql, "maxResults": 100, "fields": _UPGRADE_FIELDS}
            if page_token:
                params["nextPageToken"] = page_token
            resp = await client.get(url, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
            issues.extend(data.get("issues", []))
            if data.get("isLast", True):
                break
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    return issues


async def check_upgrade_request_type_drift() -> list[dict]:
    """Detect (never mutate) Upgrade rows whose stored request_type no
    longer matches the linked ticket's real, current Jira value — the
    stored value is only ever set once (at creation/promotion in
    _ensure_upgrade_from_ticket) and never refreshed afterward, unlike
    Case.request_type which does refresh on every regular poll. Confirmed
    live twice this session: DSD-30760 was created as a genuine sys-admin
    request but its real request_type later changed to "Support Request"
    (and its status moved to "Pending Upgrade") with nothing in the app
    noticing — it stayed visible on the Upgrade board long after it
    stopped being one.

    Only checks rows currently classified sys-admin (request_type ==
    _SYS_ADMIN_REQUEST_TYPE) — those are the ones a drift AWAY from that
    value would incorrectly keep visible on the Kanban. _ensure_upgrade_
    from_ticket's Suggested-promotion and re-anchor-to-genuine-request
    paths both always move jira_ref and request_type together, so a row
    classified sys-admin now always has jira_ref pointing at a ticket that
    really was (at least at anchor time) that type — any mismatch this
    finds is a genuine drift (the ticket's own request_type changed since),
    not a legitimate fold artifact. Still detect-only, not auto-corrected —
    same "detect and let you approve" pattern as suggested_transitions()."""
    if not settings.jira_enabled:
        return []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Upgrade)
            .where(
                Upgrade.stage.notin_(("Verified Done", "Cancelled")),
                Upgrade.jira_ref.is_not(None),
                Upgrade.request_type == _SYS_ADMIN_REQUEST_TYPE,
            )
            .options(joinedload(Upgrade.customer))
        )
        candidates = result.scalars().all()
        if not candidates:
            return []

        refs = sorted({u.jira_ref for u in candidates})
        url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
        jql = f'key in ({",".join(refs)})'
        live_by_ref: dict[str, dict] = {}
        try:
            async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
                page_token: str | None = None
                while True:
                    params = {"jql": jql, "maxResults": 100, "fields": "summary,customfield_10014"}
                    if page_token:
                        params["nextPageToken"] = page_token
                    resp = await client.get(url, headers=_HEADERS, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                    for issue in data.get("issues", []):
                        f = issue["fields"]
                        live_by_ref[issue["key"]] = {
                            "title": f.get("summary") or "",
                            "request_type": _extract_request_type(f.get("customfield_10014")),
                        }
                    page_token = data.get("nextPageToken")
                    if not page_token:
                        break
        except Exception as exc:
            logger.error("Upgrade request_type drift check failed: %s", exc)
            return []

        drifted = []
        for u in candidates:
            live = live_by_ref.get(u.jira_ref)
            if live and live["request_type"] != _SYS_ADMIN_REQUEST_TYPE:
                drifted.append({
                    "id": u.id,
                    "jira_ref": u.jira_ref,
                    "title": live["title"],
                    "customer_id": u.customer_id,
                    "customer_name": u.customer.name if u.customer else None,
                    "customer_tier": u.customer.tier if u.customer else None,
                    "stored_request_type": u.request_type,
                    "live_request_type": live["request_type"],
                })
        return drifted


_VERSION_NAME_RE = re.compile(r"^\d+\.\d+(\.\d+)?$")


async def _jira_fix_version_counts(client: httpx.AsyncClient) -> tuple[dict[str, int], dict[str, int]] | None:
    """Per fixVersion name: (bugs fixed, improvements shipped), counted
    straight from Jira — every Done VMS issue with a fixVersion (~9k,
    paginated). Bugs = issuetype Bug; improvements = everything else except
    Sub-tasks (they'd double-count their parent). Replaces counting the
    local VmsBug table, which only ever holds bugs linked from customer
    cases — confirmed 2026-10-08 it showed 0 for patch releases that fix
    1–8 bugs each in Jira (e.g. 8.31.2–8.31.8). None if Jira fails, so the
    caller keeps the existing counts rather than zeroing them."""
    bugs: dict[str, int] = {}
    improvements: dict[str, int] = {}
    token = None
    try:
        while True:
            params = {"jql": "project = VMS AND statusCategory = Done AND fixVersion is not EMPTY",
                      "fields": "issuetype,fixVersions", "maxResults": 100}
            if token:
                params["nextPageToken"] = token
            resp = await client.get(f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql",
                                    headers=_HEADERS, params=params)
            resp.raise_for_status()
            body = resp.json()
            for issue in body.get("issues", []):
                f = issue.get("fields", {})
                kind = (f.get("issuetype") or {}).get("name", "")
                if kind == "Sub-task":
                    continue
                target = bugs if kind == "Bug" else improvements
                for fv in f.get("fixVersions") or []:
                    name = (fv.get("name") or "").strip()
                    target[name] = target.get(name, 0) + 1
            token = body.get("nextPageToken")
            if not token or body.get("isLast"):
                break
    except Exception as exc:
        logger.warning("Fix-version count fetch failed: %s", exc)
        return None
    return bugs, improvements


async def sync_release_versions_from_jira() -> dict:
    """On-demand — pulls the real project/VMS/versions objects from Jira
    and upserts a local Release row for every one that's actually released
    with a real releaseDate. This is the one honest source for real
    release dates: releasenotes.dataloy.com carries real version numbers
    and real bug-fix content but no dates anywhere on the site (checked
    live). Never fabricates a date — a version with no real releaseDate on
    Jira is skipped, not backfilled with a guess."""
    if not settings.jira_enabled:
        return {"synced": 0, "skipped_no_date": 0, "error": "Jira not configured"}

    from app.models.release import Release
    from app.database import AsyncSessionLocal

    try:
        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            resp = await client.get(
                f"{settings.jira_base_url.rstrip('/')}/rest/api/3/project/VMS/versions",
                headers=_HEADERS,
            )
            resp.raise_for_status()
            versions = resp.json()
            fix_counts = await _jira_fix_version_counts(client)
    except Exception as exc:
        logger.warning("Release version sync failed: %s", exc)
        return {"synced": 0, "skipped_no_date": 0, "error": str(exc)}

    synced = skipped = 0
    async with AsyncSessionLocal() as db:
        for v in versions:
            name = (v.get("name") or "").strip()
            if not v.get("released") or not v.get("releaseDate") or not _VERSION_NAME_RE.match(name):
                skipped += 1
                continue
            try:
                released_at = datetime.strptime(v["releaseDate"], "%Y-%m-%d").date()
            except ValueError:
                skipped += 1
                continue

            version_str = f"{name}-R"
            existing = (await db.execute(select(Release).where(Release.version == version_str))).scalar_one_or_none()

            if fix_counts is not None:
                defect_count = fix_counts[0].get(name, 0)
                improvement_count = fix_counts[1].get(name, 0)
            else:  # Jira count fetch failed — keep what's there rather than zeroing
                defect_count = existing.defects_fixed if existing else 0
                improvement_count = existing.improvements if existing else 0

            if existing:
                existing.released_at = released_at
                existing.defects_fixed = defect_count
                existing.improvements = improvement_count
                if v.get("description"):
                    existing.notes = v["description"]
            else:
                db.add(Release(
                    version=version_str, released_at=released_at, defects_fixed=defect_count,
                    improvements=improvement_count, notes=v.get("description") or "", is_latest=False,
                ))
            synced += 1

        # Recompute is_latest across every real row now that new ones may
        # have landed — same "one true latest" invariant every other
        # Release-reading function in this app already assumes.
        all_releases = (await db.execute(select(Release))).scalars().all()
        if all_releases:
            newest = max(all_releases, key=lambda r: r.released_at)
            for r in all_releases:
                r.is_latest = r.id == newest.id

        await db.commit()

    return {"synced": synced, "skipped_no_date": skipped, "fix_counts_from_jira": fix_counts is not None}


async def sync_completed_upgrades() -> dict:
    """On-demand only (support-triggered button, not scheduled) — this is a
    much heavier full-history JQL scan than the regular 5-minute poll, run
    when someone actually wants the Upgrade pipeline/limits refreshed."""
    if not settings.jira_enabled:
        return {"created": 0, "updated": 0, "unmatched_customers": [], "errors": 1}

    try:
        issues = await _fetch_upgrade_tickets()
    except Exception as exc:
        logger.error("Upgrade-ticket fetch failed: %s", exc)
        return {"created": 0, "updated": 0, "unmatched_customers": [], "errors": 1}

    created = updated = 0
    unmatched_customers: set[str] = set()
    touched_customer_ids: set[int] = set()

    async with AsyncSessionLocal() as db:
        customers = (await db.execute(select(Customer))).scalars().all()
        by_name = {c.name.strip().lower(): c for c in customers}
        by_normalized_name: dict[str, Customer] = {}
        for c in customers:
            key_norm = _normalize_company_name(c.name)
            # Only keep it if the normalized form is unique — two different
            # real companies colliding onto the same normalized string is
            # exactly the false-match trap from the earlier bulk-match pass
            # this session (fuzzy-matched two different Tankers/Chartering
            # companies onto one "LARMA TANKERS"-style row); safer to drop
            # both than guess.
            if key_norm in by_normalized_name:
                by_normalized_name[key_norm] = None  # type: ignore[assignment]
            else:
                by_normalized_name[key_norm] = c

        aliases = (await db.execute(select(CustomerNameAlias))).scalars().all()
        by_alias = {a.alias_name.strip().lower(): a.customer_id for a in aliases}
        customers_by_id = {c.id: c for c in customers}

        unmatched_ref_samples: dict[str, list[str]] = {}

        for issue in issues:
            key = issue["key"]
            fields = issue["fields"]
            customer_name = _extract_customer_name(fields.get("customfield_10047"))
            if not customer_name:
                continue
            customer = by_name.get(customer_name.strip().lower())
            if customer is None:
                # Fall back to exact match after stripping common legal
                # suffixes/punctuation only — e.g. "Zodiac Maritime Limited"
                # (Jira) == "Zodiac Maritime Ltd." (local). Deliberately not
                # a fuzzy/ratio match: that's what produced a wrong match
                # earlier this session.
                customer = by_normalized_name.get(_normalize_company_name(customer_name))
            if customer is None:
                # A human explicitly linked this exact string to a customer
                # via the unmatched-upgrade-customers resolution screen.
                alias_customer_id = by_alias.get(customer_name.strip().lower())
                if alias_customer_id:
                    customer = customers_by_id.get(alias_customer_id)
            if not customer:
                unmatched_customers.add(customer_name)
                unmatched_ref_samples.setdefault(customer_name, []).append(key)
                continue

            components = {c["name"] for c in fields.get("components", [])}
            environment = next((env for comp, env in _UPGRADE_COMPONENTS.items() if comp in components), "PROD")
            extracted_version = _extract_target_version(fields.get("summary", ""))
            resolved = _parse_dt(fields.get("resolutiondate"))
            jira_created = _parse_dt(fields.get("created"))

            result = await db.execute(select(Upgrade).where(Upgrade.jira_ref == key))
            row = result.scalar_one_or_none()
            if row is None:
                new_row = Upgrade(
                    customer_id=customer.id, jira_ref=key, environment=environment,
                    to_version=extracted_version or "Unknown", stage="Verified Done", source="Jira sync",
                    date_done=resolved, verified_at=resolved,
                )
                if jira_created:
                    new_row.created_at = jira_created
                db.add(new_row)
                created += 1
            else:
                if jira_created:
                    row.created_at = jira_created
                row.customer_id = customer.id
                row.environment = environment
                # Never let this sweep downgrade an already-known target
                # version to "Unknown" — confirmed live this was a real,
                # destructive bug: _ensure_upgrade_from_ticket() sets a real
                # to_version (the latest release at creation time) when a
                # sys-admin ticket is first opened, and this sweep used to
                # unconditionally overwrite it with "Unknown" the moment the
                # ticket resolved, purely because the ticket's own summary
                # text rarely mentions a version number (Seatrans Chemicals
                # AS / DSD-31856: a real TEST upgrade to 8.31.3-R was
                # displayed as "Unknown" after this exact overwrite). Only
                # ever replace to_version when the summary actually yields
                # one, or the existing value is itself unset/"Unknown" —
                # never regress a genuine value to a worse one.
                if extracted_version or not row.to_version or row.to_version == "Unknown":
                    row.to_version = extracted_version or row.to_version or "Unknown"
                row.verified_at = resolved
                row.stage = "Verified Done"
                row.date_done = resolved
                updated += 1
            touched_customer_ids.add(customer.id)

        # upgrades_used is meant to be "used against the plan's per-year
        # allowance" (dataloy-systems.com/plans). Two real corrections here
        # (caught by the user spot-checking Saga Welco AS at an implausible
        # 16/12 on the first pass):
        #  1. The allowance year should track each customer's own
        #     subscription anniversary (renewal_date), not the calendar
        #     year — only 6/537 real customers have a renewal_date set
        #     today, so most fall back to calendar-year honestly.
        #  2. Only PROD counts against the allowance. TEST/DEV upgrades are
        #     low-risk staging work, not the disruptive production change
        #     the free-upgrade limit exists to bound — counting them
        #     inflated Saga Welco's 2026 tally from a real 9 PROD upgrades
        #     to a misleading 16. History (all environments) still stays
        #     in the `upgrades` table/UI for "what version are they on and
        #     how often do they touch it" — only this allowance count
        #     narrows to PROD.
        # Recompute for every customer with *any* Upgrade history, not just
        # ones this particular sync touched — otherwise customers whose only
        # rows are pre-existing (seed/manual) data keep a stale, arbitrary
        # upgrades_used number forever.
        all_customer_ids_with_upgrades = {
            row[0] for row in (await db.execute(select(Upgrade.customer_id).distinct())).all()
        }
        recompute_ids = touched_customer_ids | all_customer_ids_with_upgrades

        today = date.today()
        for customer_id in recompute_ids:
            customer = next((c for c in customers if c.id == customer_id), None)
            if not customer:
                continue

            if customer.renewal_date:
                try:
                    anniversary = customer.renewal_date.replace(year=today.year)
                except ValueError:
                    anniversary = customer.renewal_date.replace(year=today.year, day=28)  # Feb 29 in a non-leap year
                if anniversary > today:
                    try:
                        anniversary = anniversary.replace(year=anniversary.year - 1)
                    except ValueError:
                        anniversary = anniversary.replace(year=anniversary.year - 1, day=28)
                year_start = datetime(anniversary.year, anniversary.month, anniversary.day, tzinfo=timezone.utc)
            else:
                year_start = datetime(today.year, 1, 1, tzinfo=timezone.utc)

            count_result = await db.execute(
                select(Upgrade).where(
                    Upgrade.customer_id == customer_id,
                    Upgrade.stage == "Verified Done",
                    Upgrade.environment == "PROD",
                    Upgrade.date_done >= year_start,
                )
            )
            customer.upgrades_used = len(count_result.scalars().all())

        # Persist unmatched names so a human can resolve them once via the
        # dedicated screen instead of re-triaging the same list every sync.
        # Dismissed rows are left alone (not silently un-dismissed) but still
        # get their ticket_count/last_seen_at refreshed for the record.
        for name, refs in unmatched_ref_samples.items():
            row = (await db.execute(
                select(UnmatchedUpgradeCustomer).where(UnmatchedUpgradeCustomer.customer_name == name)
            )).scalar_one_or_none()
            if row is None:
                db.add(UnmatchedUpgradeCustomer(
                    customer_name=name, ticket_count=len(refs),
                    sample_jira_refs=",".join(refs[:5]),
                ))
            else:
                row.ticket_count = len(refs)
                row.sample_jira_refs = ",".join(refs[:5])
                row.last_seen_at = datetime.utcnow()

        await db.commit()

    logger.info(
        "Upgrade sync done — created=%d updated=%d unmatched_customers=%d",
        created, updated, len(unmatched_customers),
    )
    return {
        "created": created,
        "updated": updated,
        "customers_recomputed": len(recompute_ids),
        "unmatched_customers": sorted(unmatched_customers),
        "errors": 0,
    }
