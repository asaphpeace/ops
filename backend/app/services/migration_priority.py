"""Rule-based, three-dimension customer prioritization for the Migration
Priority view — infrastructure/migration status, incident remediation
exposure, and defect/version exposure, combined per customer. Pure
computation, no LLM involved here; see services/ollama_supervisor.py for
the separate, optional one-sentence narration layer built on top of this
(migration_priority_candidates() there feeds this same data through the
already-proven narrate-one-at-a-time / JSON-mode / reference-validated
pattern).

Defect signal, revised after a real accuracy check against live data: the
first version of this module counted "any Done bug with a fix_version
ahead of the customer's current version" — a coarse, blanket number that
mostly just restated how far behind a customer's version was, and looked
scarier than it was informative (e.g. Navigare showed "107 defects
exposed" almost entirely from that noise). The real, concrete signal is
narrower and already exists elsewhere in this app: a Case with
case_type="Upgrade", status="Closed", and a linked_vms_ref IS a defect
THIS customer personally reported that was fixed and is sitting
undelivered pending their actual upgrade — the same population Release
Intelligence's "Pending Upgrade Queue" panel already tracks. Checked by
hand against Klaveness Chartering's real 9 such cases before trusting
this: 2 linked to a VmsBug that was actually Rejected (not a real fix —
the case only *looks* like a pending fix), and 2 more pointed at the same
underlying bug reported twice — so the honest count was 6 distinct real
fixes, not 9. `pending_upgrade_defects` below is deduped by VmsBug ref and
excludes anything not linked to a real status="Done" bug for exactly this
reason. The old blanket count is kept as `theoretical_exposure` — real,
but explicitly secondary and excluded from the score — for a customer who
wants the fuller fleet-safety picture, labeled honestly as "known fixes
this customer hasn't personally reported," not "defects affecting them."

Explainable, documented scoring — a plain weighted sum, not an opaque
model, matching this app's own established convention (e.g.
TIER_UPGRADE_LIMITS in routers/customers.py). Incident severity is now
weighted (a Critical incident matters more than a Low one) rather than a
flat +3 regardless of severity — the earlier version tracked severity for
display only and never actually used it in scoring, which contradicted
the "business-risk-weighted" premise:

    priority_score = tier_weight
                    + (2 if infra == "Old" else 0)
                    + SEVERITY_WEIGHT[worst open incident's severity]  (0 if none)
                    + min(len(pending_upgrade_defects), 5)

Scoped to real VMS customers with a real PROD CustomerTenantInfo.release
on file — the same honest, modest population (44/576 customers overall,
~53 real VMS customers) that version_exposure()/customers_below_latest()
already work from in routers/releases.py. Never falls back to the fake
Customer.prod_version field."""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.case import Case
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.incident import Incident
from app.models.incident_remediation import IncidentRemediation
from app.models.migration_project import MigrationProject
from app.models.release import Release
from app.models.vms_bug import VmsBug

# Same element-wise parser as routers/releases.py::_version_tuple — kept as
# its own small copy here rather than imported, since that one lives in the
# router layer and this is a service the router imports FROM (same
# reasoning services/upgrade_supervision.py already documents for its own
# copy of this exact helper).
_VERSION_NUM = re.compile(r"\d+")


def _version_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    parts = _VERSION_NUM.findall(v)
    return tuple(int(p) for p in parts) if parts else None


TIER_WEIGHT = {"Premier": 3, "Strategic": 2, "Scale": 1}
SEVERITY_WEIGHT = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}


def _remediation_covered(r: IncidentRemediation) -> bool:
    """Mirrors routers/incidents.py::_derive_remediation_status()'s "is this
    customer actually taken care of" check exactly (Verified-Done upgrade /
    manually resolved / a real accepted-risk-or-workaround mitigation) —
    kept as its own small copy rather than imported, for the same
    router-vs-service direction reason as _version_tuple above."""
    if r.upgrade and r.upgrade.stage == "Verified Done":
        return True
    if r.manually_resolved:
        return True
    if r.mitigation_type in ("accepted_risk", "workaround_applied"):
        return True
    return False


async def migration_priority(db: AsyncSession) -> dict:
    vms_customer_ids = set(
        (await db.execute(select(Customer.id).where(Customer.product.ilike("%VMS%")))).scalars().all()
    )
    if not vms_customer_ids:
        return {"customers": [], "vms_customer_count": 0, "covered_count": 0}

    prod_rows = (
        await db.execute(select(CustomerTenantInfo).where(
            CustomerTenantInfo.environment == "PROD",
            CustomerTenantInfo.customer_id.in_(vms_customer_ids),
            CustomerTenantInfo.release.isnot(None),
        ))
    ).scalars().all()
    if not prod_rows:
        return {"customers": [], "vms_customer_count": len(vms_customer_ids), "covered_count": 0}

    customer_ids = {r.customer_id for r in prod_rows}
    customers_by_id = {
        c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
    }
    migrations_by_customer = {
        m.customer_id: m
        for m in (
            await db.execute(select(MigrationProject).where(MigrationProject.customer_id.in_(customer_ids)))
        ).scalars().all()
    }

    latest = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    latest_tuple = _version_tuple(latest.version) if latest else None

    done_bugs = (
        await db.execute(select(VmsBug).where(VmsBug.status == "Done", VmsBug.fix_version.isnot(None)))
    ).scalars().all()

    # Real, customer-specific "defect that was addressed, not yet delivered"
    # signal — see module docstring for why this replaced a blanket version
    # comparison. Fetched once for every candidate customer, not per-row.
    pending_upgrade_cases = (
        await db.execute(
            select(Case).where(
                Case.case_type == "Upgrade",
                Case.status == "Closed",
                Case.linked_vms_ref.isnot(None),
                Case.customer_id.in_(customer_ids),
            )
        )
    ).scalars().all()
    linked_refs = {c.linked_vms_ref for c in pending_upgrade_cases}
    bugs_by_ref = {
        b.jira_ref: b
        for b in (await db.execute(select(VmsBug).where(VmsBug.jira_ref.in_(linked_refs)))).scalars().all()
    } if linked_refs else {}

    # Deduped by VmsBug ref per customer — two cases can report the same
    # underlying defect (confirmed live on Klaveness Chartering: DSD-28094
    # and DSD-29562 both link VMS-21173). Only a bug with a real, shipped
    # fix (status == "Done") counts — a case can sit at raw_status
    # "Pending Upgrade" while its linked bug was actually Rejected (also
    # confirmed live: 2 of Klaveness's 9 cases), which is not a real
    # "defect addressed" and would otherwise overstate the count.
    pending_defects_by_customer: dict[int, dict[str, dict]] = {}
    for c in pending_upgrade_cases:
        bug = bugs_by_ref.get(c.linked_vms_ref)
        if not bug or bug.status != "Done" or not bug.fix_version:
            continue
        entry = pending_defects_by_customer.setdefault(c.customer_id, {})
        if c.linked_vms_ref not in entry:
            entry[c.linked_vms_ref] = {
                "case_jira_ref": c.jira_ref, "case_title": c.title,
                "vms_ref": c.linked_vms_ref, "fix_version": bug.fix_version,
            }

    open_incidents = (
        await db.execute(select(Incident).where(Incident.status == "Open", Incident.source == "product"))
    ).scalars().all()
    incidents_by_id = {i.id: i for i in open_incidents}

    remediations = []
    if incidents_by_id:
        remediations = (
            await db.execute(
                select(IncidentRemediation)
                .where(
                    IncidentRemediation.incident_id.in_(incidents_by_id.keys()),
                    IncidentRemediation.customer_id.in_(customer_ids),
                )
                .options(joinedload(IncidentRemediation.upgrade))
            )
        ).scalars().all()

    outstanding_by_customer: dict[int, list[dict]] = {}
    for r in remediations:
        if _remediation_covered(r):
            continue
        inc = incidents_by_id.get(r.incident_id)
        if not inc:
            continue
        outstanding_by_customer.setdefault(r.customer_id, []).append(
            {"incident_id": inc.id, "title": inc.title, "severity": inc.severity}
        )

    results = []
    for row in prod_rows:
        cust = customers_by_id.get(row.customer_id)
        if not cust:
            continue
        version_tuple = _version_tuple(row.release)

        migration = migrations_by_customer.get(cust.id)
        migration_stage = migration.stage if migration else "Not Started"
        migration_tracked = migration is not None

        pending_defects = list(pending_defects_by_customer.get(cust.id, {}).values())
        pending_refs = {d["vms_ref"] for d in pending_defects}

        # Secondary, explicitly-labeled fleet-wide signal — real bugs this
        # customer hasn't personally reported, kept OUT of the score (see
        # module docstring) and never double-counted against pending_defects.
        theoretical_exposure = []
        if version_tuple:
            for b in done_bugs:
                if b.jira_ref in pending_refs:
                    continue
                t = _version_tuple(b.fix_version)
                if t and t > version_tuple:
                    theoretical_exposure.append({"vms_ref": b.jira_ref, "fix_version": b.fix_version})

        open_remediations = outstanding_by_customer.get(cust.id, [])
        worst_severity = max(
            (SEVERITY_WEIGHT.get(r["severity"], 0) for r in open_remediations), default=0,
        )

        tier_weight = TIER_WEIGHT.get(cust.tier, 0)
        infra_weight = 2 if cust.infra == "Old" else 0
        defect_weight = min(len(pending_defects), 5)
        priority_score = tier_weight + infra_weight + worst_severity + defect_weight

        results.append({
            "customer_id": cust.id,
            "customer_name": cust.name,
            "customer_tier": cust.tier,
            "infra": cust.infra,
            "migration_stage": migration_stage,
            "migration_tracked": migration_tracked,
            "current_version": row.release,
            "latest_version": latest.version if latest else None,
            "is_behind_latest": bool(version_tuple and latest_tuple and version_tuple < latest_tuple),
            "open_incident_remediations": open_remediations,
            "pending_upgrade_defects": pending_defects,
            "pending_upgrade_defect_count": len(pending_defects),
            "theoretical_exposure": theoretical_exposure,
            "theoretical_exposure_count": len(theoretical_exposure),
            "priority_score": priority_score,
            "score_breakdown": {
                "tier_weight": tier_weight, "infra_weight": infra_weight,
                "incident_severity_weight": worst_severity, "defect_weight": defect_weight,
            },
        })

    results.sort(key=lambda r: r["priority_score"], reverse=True)
    return {
        "customers": results,
        "vms_customer_count": len(vms_customer_ids),
        "covered_count": len(customer_ids),
    }
