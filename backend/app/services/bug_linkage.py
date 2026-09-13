from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models.case import Case


async def cases_by_bug_ref(db, bug_refs: set[str] | None = None) -> dict[str, list[Case]]:
    """Every real Case linked to a VMS bug, keyed by bug ref. Splits the
    comma-joined linked_vms_refs (falling back to the singular linked_vms_ref)
    so a case's SECOND linked bug is never dropped — replaces several call
    sites that previously matched on linked_vms_ref alone and silently missed
    a case whose queried bug wasn't its first link (confirmed live: DSD-28129
    links both VMS-19447 and VMS-22680, but linked_vms_ref only ever holds
    the first)."""
    query = select(Case).where(Case.linked_vms_ref.isnot(None)).options(joinedload(Case.customer))
    cases = (await db.execute(query)).scalars().all()
    out: dict[str, list[Case]] = {}
    for c in cases:
        refs = [r for r in (c.linked_vms_refs or c.linked_vms_ref or "").split(",") if r]
        for ref in refs:
            if bug_refs is not None and ref not in bug_refs:
                continue
            out.setdefault(ref, []).append(c)
    return out
