"""Deterministic signal-joining for the Ollama supervisor — the "detect" half.

Everything here is plain Python/SQL, zero LLM involvement, and reuses
existing, already-proven query logic rather than re-deriving it:
cases_by_bug_ref() (bug_linkage.py), compute_alerts() (alerts.py), and
desk_briefing()'s own flags (desk.py) supply every fact — this module only
joins/groups/bounds what they already computed. services/ollama_supervisor.py
hands the bounded output of these two functions to the model to narrate;
the model never sees raw data and never does the joining itself.
"""
from sqlalchemy import select

from app.models.customer import Customer
from app.models.ops_note import OpsNote
from app.models.vms_bug import VmsBug
from app.services.bug_linkage import cases_by_bug_ref


async def _ops_notes_by_jira_ref(db) -> dict[str, list[str]]:
    """Real, manually-pasted human context (Slack discussion etc. — see
    OpsNote's own docstring for why this can't be a live sync) keyed by
    jira_ref. No Slack API access exists, so this is the only source of
    "what did a person already know/say about this" the supervisor has."""
    rows = (await db.execute(select(OpsNote).where(OpsNote.jira_ref.is_not(None)))).scalars().all()
    out: dict[str, list[str]] = {}
    for n in rows:
        out.setdefault(n.jira_ref, []).append(n.text)
    return out


async def _ops_notes_by_customer(db) -> dict[int, list[str]]:
    """Same as _ops_notes_by_jira_ref, keyed by customer_id instead — for
    cross_signal_candidates(), where a note may not be tied to one ticket."""
    rows = (await db.execute(select(OpsNote).where(OpsNote.customer_id.is_not(None)))).scalars().all()
    out: dict[int, list[str]] = {}
    for n in rows:
        out.setdefault(n.customer_id, []).append(n.text)
    return out


async def _vms_customers(db) -> dict[str, int]:
    """name -> id for real VMS customers only. Scopes the (currently slow,
    local-model) supervisor to a much smaller, more relevant candidate pool
    — same product ILIKE '%VMS%' convention already used everywhere else
    this session (Customer Intelligence stats, Trends, Release
    Intelligence) — and doubles as the real customer_id resolver for
    cross_signal_candidates(): compute_alerts()'s ticket-level signals
    (sla_breach/stale/chase_needed) only ever carry a customer_name, never
    an id, so without this every cross-signal observation sourced purely
    from ticket alerts would have customer_id=None and no click-through."""
    rows = (await db.execute(select(Customer.id, Customer.name).where(Customer.product.ilike("%VMS%")))).all()
    return {name: cid for cid, name in rows}


async def fixed_but_open_candidates(db, limit: int = 20) -> list[dict]:
    """Case.status != 'Closed' but its linked VmsBug already reached
    status == 'Done' — a real, confirmed gap: no existing endpoint checks
    this (cases_by_bug_ref()'s own consumers all ignore Case.status
    entirely). Scoped to real VMS customers only. Bounded and sorted by
    days_open desc — worst-first, same convention as digest.py's
    _MAX_ROVO_LOOKUPS."""
    done_bugs = (await db.execute(select(VmsBug).where(VmsBug.status == "Done"))).scalars().all()
    bug_by_ref = {b.jira_ref: b for b in done_bugs}
    by_bug_cases = await cases_by_bug_ref(db, set(bug_by_ref.keys()))
    ops_notes = await _ops_notes_by_jira_ref(db)

    candidates = []
    for ref, cases in by_bug_cases.items():
        bug = bug_by_ref[ref]
        for c in cases:
            if c.status == "Closed":
                continue
            if not (c.customer and c.customer.product and "VMS" in c.customer.product.upper()):
                continue
            candidates.append({
                "jira_ref": c.jira_ref,
                "customer_name": c.customer.name if c.customer else (c.jira_customer_name or "Unknown"),
                "customer_id": c.customer_id,
                "days_open": c.days_open or 0,
                "case_status": c.status,
                "vms_ref": ref,
                "fix_version": bug.fix_version,
                "ops_notes": ops_notes.get(c.jira_ref, []),
            })

    candidates.sort(key=lambda x: -x["days_open"])
    return candidates[:limit]


async def cross_signal_candidates(db, scope: str = "team", limit: int = 15) -> list[dict]:
    """Groups already-computed flags by customer and keeps only customers
    hit by 2+ DISTINCT signal types at once — the actual "not so obvious"
    connection, computed deterministically here, not discovered by the
    model. Reuses compute_alerts() (stale/chase_needed/sla_breach) and
    desk_briefing()'s existing flags (renewal, stalled migration, hypercare,
    bug-fix-upgrade-overdue) — zero new queries. Bounded and sorted by
    signal count desc.

    Ticket-level noise (sla_breach/stale/chase_needed) is aggregated per
    customer+type into ONE compact entry (a count + up to 2 example refs),
    not one entry per ticket — confirmed live this matters: a customer with
    dozens of breaching tickets would otherwise flood the model's input
    with volume that isn't a "connection," just noise already visible
    elsewhere (Support Signals, Team Load Split). The genuinely
    non-obvious signal is a *different kind* of flag landing on the same
    account at once — a rare account-level fact (renewal/hypercare/
    stalled-migration/overdue-bug-fix-upgrade) alongside routine ticket
    load, not the ticket count itself. Scoped to real VMS customers only —
    customer_id on every returned candidate is resolved from that same VMS
    name->id map, not from whichever flag happened to carry one, so
    click-through works regardless of which signal types a customer was
    flagged by."""
    from app.routers.desk import desk_briefing
    from app.services.alerts import compute_alerts

    vms_customers = await _vms_customers(db)
    ops_notes = await _ops_notes_by_customer(db)
    briefing = await desk_briefing(scope=scope, db=db)
    flags = briefing["flags"]

    ticket_buckets: dict[tuple[str, str], dict] = {}
    for a in await compute_alerts(db, scope=scope):
        key = (a["customer_name"], a["type"])
        bucket = ticket_buckets.setdefault(key, {"count": 0, "refs": []})
        bucket["count"] += 1
        if len(bucket["refs"]) < 2 and a.get("jira_ref"):
            bucket["refs"].append(a["jira_ref"])

    by_customer: dict[str, list[dict]] = {}

    def add(name: str | None, entry: dict) -> None:
        # "Unknown" is compute_alerts()'s own fallback for a ticket with no
        # resolved customer name — not a real, actionable grouping key.
        if not name or name == "Unknown" or name not in vms_customers:
            return
        by_customer.setdefault(name, []).append(entry)

    for (name, sig_type), bucket in ticket_buckets.items():
        add(name, {
            "type": sig_type,
            "detail": f"{bucket['count']} ticket(s), e.g. {', '.join(bucket['refs']) or 'n/a'}",
            "jira_ref": bucket["refs"][0] if bucket["refs"] else None,
        })

    for c in flags["renewal_under_60d_customers"]:
        add(c["name"], {"type": "renewal", "detail": "renewing within 60 days", "jira_ref": None})

    for m in flags["stalled_migrations"]:
        add(m.get("customer_name"), {"type": "stalled_migration", "detail": "migration stalled", "jira_ref": None})

    for c in flags["hypercare_customers"]:
        add(c["name"], {"type": "hypercare", "detail": "in hypercare", "jira_ref": None})

    for u in flags["bug_fix_upgrade_overdue"]:
        add(
            u.get("customer_name"),
            {"type": "bug_fix_upgrade_overdue", "detail": f"{u.get('days_stale')}d stale", "jira_ref": u.get("jira_ref")},
        )

    # Real, manually-known human context (e.g. Slack) — the actual "connect
    # what a person already knows with what the automated flags show"
    # moment this feature exists for. A customer with just ONE automated
    # flag plus a real ops note about them still clears the "2+ distinct
    # signals" bar below, same as any other pair of signal types.
    for name, cid in vms_customers.items():
        for note_text in ops_notes.get(cid, []):
            add(name, {"type": "ops_note", "detail": note_text[:300], "jira_ref": None})

    candidates = [
        {"customer_name": name, "customer_id": vms_customers[name], "signals": entries}
        for name, entries in by_customer.items()
        if len({e["type"] for e in entries}) >= 2
    ]
    candidates.sort(key=lambda c: -len(c["signals"]))
    return candidates[:limit]


async def migration_priority_candidates(db, limit: int = 10) -> list[dict]:
    """Bounded, top-N view of services/migration_priority.py's already-
    ranked, already-scored output — the model narrates the top of a real
    list a pure function built, it never re-derives the ranking itself.
    Only surfaces a customer when there's genuinely something to say beyond
    the bare score (an open incident remediation, real defect exposure, or
    old infra) — a customer sitting at priority_score 0 with nothing
    outstanding isn't a "connection," just a tier weight."""
    from app.services.migration_priority import migration_priority

    result = await migration_priority(db)
    candidates = [
        c for c in result["customers"]
        if c["priority_score"] > 0 and (c["open_incident_remediations"] or c["pending_upgrade_defect_count"] or c["infra"] == "Old")
    ]
    return candidates[:limit]


async def training_priority_candidates(db, limit: int = 10) -> list[dict]:
    """Bounded, top-N view of services/training_priority.py's already-
    computed, already-ranked real feature-crossing list — same "the model
    narrates a real list a pure function built" shape as
    migration_priority_candidates() above. Only includes a customer when
    real cached features exist for a version they're behind on — there's
    nothing to narrate for a customer whose crossed releases have no
    cached Synopsis content (yet)."""
    from app.services.training_priority import training_recommendations

    result = await training_recommendations(db)
    return result["customers"][:limit]
