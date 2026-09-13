"""Version-driven training recommendations — real customers behind on
real, feature-bearing master releases (not just "old version," which was
already the mistake corrected once this session on Migration Priority's
defect signal). Reuses the same honest, validated customer population
CustomerTenantInfo-based endpoints already work from (version_exposure(),
customers_below_latest(), migration_priority()).

Pure rule-based join — no LLM here. The judgment call (which topic_area a
feature maps to, and why a customer should care) is a genuine language
task, handled separately by the narration layer in ollama_supervisor.py."""
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.release import Release
from app.models.release_note_feature import ReleaseNoteFeature
from app.services.release_notes import master_releases_between

_VERSION_NUM = re.compile(r"\d+")


def _version_tuple(v: str | None) -> tuple[int, ...] | None:
    if not v:
        return None
    parts = _VERSION_NUM.findall(v)
    return tuple(int(p) for p in parts) if parts else None


# Same keyword-guess mapping used for the Training-Gap Case bridge
# (services/jira.py::_ensure_training_gap_from_ticket) — reused here so a
# release-note category and a manually-logged training gap land in the
# same fixed vocabulary already shown in TrainingSession.topic_area.
TRAINING_AREA_KEYWORDS: dict[str, list[str]] = {
    "Voyage Management": ["voyage", "vessel", "port call", "pilot station", "port expense"],
    "Cargo Operations": ["cargo", "laytime", "demurrage", "bunker"],
    "Period-End Closing": ["period-end", "closing", "accrual", "p&l", "invoic"],
    "Fleet Planning": ["fleet plan", "scheduling", "estimate"],
    "Reporting & Analytics": ["report", "analytics", "dashboard", "comment"],
    "User Administration": ["user admin", "permission", "role", "attachment"],
    "Integrations": ["integration", "api", "webhook"],
}


def guess_training_area(text: str) -> str:
    lowered = text.lower()
    for area, keywords in TRAINING_AREA_KEYWORDS.items():
        if any(k in lowered for k in keywords):
            return area
    return "Other"


async def training_recommendations(db: AsyncSession) -> dict:
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

    latest = (await db.execute(select(Release).where(Release.is_latest == True))).scalar_one_or_none()  # noqa: E712
    if not latest:
        return {"customers": [], "vms_customer_count": len(vms_customer_ids), "covered_count": 0}

    all_features = (await db.execute(select(ReleaseNoteFeature))).scalars().all()
    features_by_version: dict[str, list[ReleaseNoteFeature]] = {}
    for f in all_features:
        features_by_version.setdefault(f.version, []).append(f)

    results = []
    for row in prod_rows:
        cust = customers_by_id.get(row.customer_id)
        if not cust:
            continue

        crossed_versions = master_releases_between(row.release, latest.version)
        if not crossed_versions:
            continue

        features = []
        for v in crossed_versions:
            for f in features_by_version.get(v, []):
                features.append({
                    "version": v, "ticket_id": f.ticket_id, "title": f.title,
                    "category": f.category, "description": f.description,
                    "topic_area": guess_training_area(f"{f.category or ''} {f.title}"),
                })
        if not features:
            continue  # crossed only patch-level/no-cached-feature releases — nothing to flag

        results.append({
            "customer_id": cust.id,
            "customer_name": cust.name,
            "customer_tier": cust.tier,
            "current_version": row.release,
            "latest_version": latest.version,
            "crossed_versions": crossed_versions,
            "features": features,
            "feature_count": len(features),
        })

    results.sort(key=lambda r: r["feature_count"], reverse=True)
    return {
        "customers": results,
        "vms_customer_count": len(vms_customer_ids),
        "covered_count": len(customer_ids),
    }
