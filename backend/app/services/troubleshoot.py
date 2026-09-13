"""Troubleshoot — resolve a pasted ticket ref or symptom description to a
real Case/VmsBug and report real, already-computed facts about it (status,
fix version, fleet exposure, whether a Release is logged, whether a
Platform Incident already tracks it). Every field returned is a real,
verifiable fact; the only generated text is one optional, tightly-scoped
narration sentence, and even that degrades to nothing if Ollama isn't
configured or its answer can't be parsed.

Deliberately does NOT attempt to reproduce, replay, restore a "world
snapshot", or bisect versions — a black-box observer of a proprietary VMS
cannot honestly produce those claims. This only ever reports what's already
true and already computed elsewhere in this app (version_exposure(),
cases_by_bug_ref(), the real Incident table) — see the plan this was
specced from for the full reasoning.
"""
from sqlalchemy import select, text
from sqlalchemy.orm import joinedload

from app.models.case import Case
from app.models.incident import Incident
from app.models.vms_bug import VmsBug
from app.routers.releases import _exposure_for_bug, _exposure_prep
from app.services.bug_linkage import cases_by_bug_ref
from app.services.ollama_context import _REF_PATTERN
from app.services.ollama_supervisor import _ollama_chat, _parse_summary

# Only source types that resolve to a single real Case/VmsBug — a matching
# ops note or campaign has no one entity for this screen to show.
_FULLTEXT_ENTITY_TYPES = ("case", "case_comment", "vms_bug")


async def _resolve_fulltext(db, query: str) -> tuple[str, Case | None, VmsBug | None] | None:
    """Same ranking idea as ollama_context.py's _fulltext_fallback() (top
    ts_rank hit over ollama_search_index), scoped to entity-resolvable
    source types and returning the resolved row instead of prompt text —
    this screen needs structured facts, not prose. Does not modify or
    duplicate the shared full-text index; it's the same table, same rank
    function, just a narrower type filter and a different projection."""
    row = (
        await db.execute(
            text(
                "SELECT source_type, source_ref "
                "FROM ollama_search_index "
                "WHERE content_tsv @@ plainto_tsquery('english', :q) "
                "AND source_type = ANY(:types) "
                "ORDER BY ts_rank(content_tsv, plainto_tsquery('english', :q)) DESC LIMIT 1"
            ),
            {"q": query, "types": list(_FULLTEXT_ENTITY_TYPES)},
        )
    ).first()
    if not row:
        return None
    if row.source_type == "vms_bug":
        bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == row.source_ref))).scalar_one_or_none()
        return ("fulltext", None, bug) if bug else None
    # "case" -> source_ref is the bare jira_ref; "case_comment" -> source_ref
    # is "<jira_ref>#<comment_id>" (confirmed in ollama_search_index.py) —
    # either way the real jira_ref is the part before any "#".
    jira_ref = row.source_ref.split("#")[0]
    case = (
        await db.execute(select(Case).where(Case.jira_ref == jira_ref).options(joinedload(Case.customer)))
    ).scalar_one_or_none()
    return ("fulltext", case, None) if case else None


async def _resolve(db, query: str) -> tuple[str, Case | None, VmsBug | None]:
    """Three-tier resolution, same order as ollama_context.py's
    assemble_context() (ref match -> fulltext fallback — the customer-name
    tier is skipped here, since a bare customer name has no single
    case/bug for this screen to diagnose) — reusing the real ref pattern
    and lazy-sync path directly rather than re-deriving them. A literal ref
    that doesn't resolve returns not_found directly rather than silently
    falling through to an unrelated fulltext match."""
    ref_match = _REF_PATTERN.search(query)
    if ref_match:
        ref = ref_match.group(0).upper()
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
            return ("case_ref", case, None) if case else ("not_found", None, None)
        bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == ref))).scalar_one_or_none()
        return ("vms_ref", None, bug) if bug else ("not_found", None, None)

    resolved = await _resolve_fulltext(db, query)
    return resolved if resolved else ("not_found", None, None)


async def _narrate(bug_out: dict) -> str | None:
    """One bounded call, scoped to exactly the facts already resolved in
    investigate() — same one-candidate-at-a-time design as
    narrate_fixed_but_open() in ollama_supervisor.py, which is why no
    separate reference-validation guard is needed here: there is nothing
    else in the prompt for the model to invent a ref about."""
    n_reported = len(bug_out["reported_customers"])
    n_silent = len(bug_out["silently_exposed_customers"])
    release_note = (
        f"A matching Release {bug_out['matched_release']} is logged."
        if bug_out["matched_release"] else "No matching Release is logged yet."
    )
    prompt = (
        f"A VMS bug {bug_out['vms_ref']} has status {bug_out['status']}, fix version "
        f"{bug_out['fix_version'] or 'not set'}. {n_reported} customer(s) reported it, "
        f"{n_silent} more are on affected versions but haven't. {release_note} "
        "Write ONE short sentence summarizing this for a support engineer — no invented "
        'details. Reply with ONLY this exact JSON object, nothing else: '
        '{"summary": "your sentence here"}'
    )
    return _parse_summary(await _ollama_chat(prompt, purpose="troubleshoot"))


async def investigate(db, query: str) -> dict:
    resolution_path, case, bug = await _resolve(db, query)
    steps: list[dict] = []

    if resolution_path == "not_found":
        steps.append({
            "label": "Searched",
            "detail": "No matching case, bug, or note found for this — try pasting the exact "
                      "Jira ref (e.g. DSD-12345 or VMS-12345).",
        })
        return {"resolution_path": resolution_path, "case": None, "bug": None, "incident": None,
                "steps": steps, "narration": None}

    if resolution_path == "case_ref":
        steps.append({"label": "Matched input", "detail": f"Recognized as a direct case reference — found {case.jira_ref}."})
    elif resolution_path == "vms_ref":
        steps.append({"label": "Matched input", "detail": f"Recognized as a direct VMS bug reference — found {bug.jira_ref}."})
    else:
        target = case.jira_ref if case else bug.jira_ref
        steps.append({"label": "Matched input", "detail": f"No exact ref match — the closest real match found via full-text search was {target}."})

    case_out = None
    if case:
        case_out = {
            "jira_ref": case.jira_ref,
            "title": case.title,
            "status": case.status,
            "customer_name": case.customer.name if case.customer else case.jira_customer_name,
            "days_open": case.days_open,
        }
        steps.append({"label": "Case", "detail": f"{case.jira_ref}: \"{case.title}\" — status {case.status}, {case.days_open}d open."})
        # linked_vms_refs (comma-joined), not linked_vms_ref alone — a case
        # can link more than one real bug (confirmed live: DSD-28129 links
        # both VMS-19447 and VMS-22680) and this tool's whole point is not
        # to silently drop evidence the way the mockup it was specced
        # against did.
        linked_refs = [r for r in (case.linked_vms_refs or case.linked_vms_ref or "").split(",") if r]
        if not bug and linked_refs:
            bug = (await db.execute(select(VmsBug).where(VmsBug.jira_ref == linked_refs[0]))).scalar_one_or_none()
        if not bug:
            steps.append({"label": "Linked bug", "detail": "No linked VMS bug on this case yet."})
        elif len(linked_refs) > 1:
            steps.append({
                "label": "Other linked bugs",
                "detail": f"This case also links {len(linked_refs) - 1} more real bug(s): {', '.join(linked_refs[1:])}.",
            })

    bug_out = None
    incident_out = None
    if bug:
        steps.append({
            "label": "Bug status",
            "detail": f"{bug.jira_ref} — {bug.status}, fix version {bug.fix_version or 'not yet set'}, "
                      f"sprint {bug.sprint_name or '—'}, assignee {bug.assignee or 'unassigned'}.",
        })

        reported = (await cases_by_bug_ref(db, {bug.jira_ref})).get(bug.jira_ref, [])
        prep = await _exposure_prep(db)
        exposure = _exposure_for_bug(bug, reported, prep)

        if not bug.fix_version:
            steps.append({"label": "Release check", "detail": "No fix version set yet — can't check against logged Releases."})
        elif exposure["matched_release"]:
            steps.append({"label": "Release check", "detail": f"Fix version {bug.fix_version} matches logged Release {exposure['matched_release']}."})
        else:
            steps.append({"label": "Release check", "detail": f"Fix version {bug.fix_version} has no matching logged Release yet — fixed, not yet formally released."})

        n_reported = len(exposure["reported_customers"])
        n_silent = len(exposure["silently_exposed_customers"])
        if n_reported or n_silent:
            steps.append({
                "label": "Fleet exposure",
                "detail": f"{n_reported} customer{'s' if n_reported != 1 else ''} reported it; "
                          f"{n_silent} more {'are' if n_silent != 1 else 'is'} on affected versions and haven't.",
            })
        else:
            steps.append({"label": "Fleet exposure", "detail": "No real customer exposure found (either unreported, or no fix version to compare tenant versions against)."})

        incident = (
            await db.execute(select(Incident).where(Incident.linked_vms_ref == bug.jira_ref))
        ).scalars().first()
        if incident:
            incident_out = {"id": incident.id, "title": incident.title, "status": incident.status, "phase": incident.phase}
            steps.append({"label": "Platform incident", "detail": f"Tracked by Incident #{incident.id} — {incident.status}, phase {incident.phase}."})
        else:
            steps.append({"label": "Platform incident", "detail": "No Platform Incident is tracking this bug yet."})

        bug_out = {
            "vms_ref": bug.jira_ref,
            "status": bug.status,
            "fix_version": bug.fix_version,
            "sprint_name": bug.sprint_name,
            "assignee": bug.assignee,
            "matched_release": exposure["matched_release"],
            "reported_customers": exposure["reported_customers"],
            "silently_exposed_customers": exposure["silently_exposed_customers"],
        }

    narration = await _narrate(bug_out) if bug_out else None

    return {
        "resolution_path": resolution_path,
        "case": case_out,
        "bug": bug_out,
        "incident": incident_out,
        "steps": steps,
        "narration": narration,
    }
