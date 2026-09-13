"""
Parses a manually-exported AWS inventory (EC2/RDS/CloudWatch JSON, produced
by scripts/aws-export.sh) and matches each resource to a real customer.

No live boto3/AWS credential is ever used here — this app is never granted
one. The user runs the export script locally against their own AWS
credentials and pastes the resulting JSON into the Engineering >
Infrastructure import screen; this module only ever parses what it's
handed.

Matching is deliberately optimistic-but-unconfirmed: no real AWS resource
naming convention has ever been observed against this codebase (there was
no AWS integration of any kind before this), so a real, materially higher
unmatched rate than tenant_discovery.py sees for Dataloy subdomains is
expected on first import — the manual resolution screen this feeds is
load-bearing, not a nice-to-have.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.services.tenant_info import _squash_company_name


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_ec2(raw: dict | list) -> list[dict]:
    """Accepts either the real `aws ec2 describe-instances` shape
    ({"Reservations": [{"Instances": [...]}]}) or an already-flattened
    list of instance dicts — defensive against the user pasting either
    the raw CLI output or a pre-flattened export."""
    if isinstance(raw, dict) and "Reservations" in raw:
        instances = [i for r in raw.get("Reservations", []) for i in r.get("Instances", [])]
    elif isinstance(raw, list):
        instances = raw
    else:
        instances = []

    out = []
    for inst in instances:
        tags = {t.get("Key"): t.get("Value") for t in inst.get("Tags", []) if t.get("Key")}
        out.append({
            "resource_type": "EC2",
            "resource_id": inst.get("InstanceId"),
            "name": tags.get("Name"),
            "instance_type": inst.get("InstanceType"),
            "engine": None,
            "engine_version": None,
            "state": (inst.get("State") or {}).get("Name"),
            "endpoint_or_ip": inst.get("PublicIpAddress") or inst.get("PrivateIpAddress"),
            "launched_at": _parse_dt(inst.get("LaunchTime")),
            "raw": inst,
        })
    return [r for r in out if r["resource_id"]]


def parse_rds(raw: dict | list) -> list[dict]:
    """Accepts either the real `aws rds describe-db-instances` shape
    ({"DBInstances": [...]}) or an already-flattened list."""
    if isinstance(raw, dict) and "DBInstances" in raw:
        instances = raw.get("DBInstances", [])
    elif isinstance(raw, list):
        instances = raw
    else:
        instances = []

    out = []
    for inst in instances:
        out.append({
            "resource_type": "RDS",
            "resource_id": inst.get("DBInstanceIdentifier"),
            "name": inst.get("DBInstanceIdentifier"),
            "instance_type": inst.get("DBInstanceClass"),
            "engine": inst.get("Engine"),
            "engine_version": inst.get("EngineVersion"),
            "state": inst.get("DBInstanceStatus"),
            "endpoint_or_ip": (inst.get("Endpoint") or {}).get("Address"),
            "launched_at": _parse_dt(inst.get("InstanceCreateTime")),
            "raw": inst,
        })
    return [r for r in out if r["resource_id"]]


def parse_cloudwatch(raw: list) -> dict[tuple[str, str], dict]:
    """Keyed by (resource_type, resource_id), from the shape
    scripts/aws-export.sh produces: a flat list of
    {"resource_type", "resource_id", "data": {"Datapoints": [...]}}.
    Returns the single most recent datapoint's Average CPU + the full raw
    payload per resource — a snapshot, not a time-series."""
    out: dict[tuple[str, str], dict] = {}
    for entry in raw or []:
        rtype = entry.get("resource_type")
        rid = entry.get("resource_id")
        if not rtype or not rid:
            continue
        datapoints = (entry.get("data") or {}).get("Datapoints", [])
        latest = max(datapoints, key=lambda d: d.get("Timestamp", ""), default=None)
        out[(rtype, rid)] = {
            "captured_at": _parse_dt(latest["Timestamp"]) if latest else datetime.now(timezone.utc),
            "cpu_utilization_pct": latest.get("Average") if latest else None,
            "raw": entry,
        }
    return out


async def build_match_maps(db: AsyncSession) -> tuple[dict[str, Customer], dict[str, Customer]]:
    """Two lookup maps, built once per import: squashed customer name ->
    Customer, and CustomerTenantInfo.subdomain -> Customer. Mirrors the
    exact by_normalized_name / by_alias map-building pattern already used
    throughout services/jira.py and tenant_discovery.py."""
    customers = (await db.execute(select(Customer))).scalars().all()
    by_name: dict[str, Customer] = {}
    for c in customers:
        key = _squash_company_name(c.name)
        if key:
            by_name.setdefault(key, c)

    tenant_rows = (await db.execute(select(CustomerTenantInfo))).scalars().all()
    by_id = {c.id: c for c in customers}
    by_subdomain: dict[str, Customer] = {}
    for t in tenant_rows:
        cust = by_id.get(t.customer_id)
        if cust and t.subdomain:
            by_subdomain.setdefault(_squash_company_name(t.subdomain), cust)

    return by_name, by_subdomain


def match_candidate(name: str | None, by_name: dict[str, Customer], by_subdomain: dict[str, Customer]) -> Customer | None:
    """Best-effort candidate only — never trusted without a human Accept
    (see routers/engineering.py's confirm-match endpoint). Tries the
    resource's Name tag / DB identifier squashed against both known
    customer names and known real tenant subdomains, since an AWS resource
    is at least as likely to be named after the subdomain ("seatrans-prod")
    as the company name."""
    if not name:
        return None
    squashed = _squash_company_name(name)
    if not squashed:
        return None
    # Strip a trailing -prod/-test/-dev suffix before matching against
    # subdomain, since real subdomains are usually bare or -prod/-test
    # suffixed themselves (generate_tenant_candidates' own convention).
    for suffix in ("prod", "test", "dev"):
        if squashed.endswith(suffix) and len(squashed) > len(suffix):
            trimmed = squashed[: -len(suffix)]
            if trimmed in by_subdomain:
                return by_subdomain[trimmed]
    if squashed in by_subdomain:
        return by_subdomain[squashed]
    if squashed in by_name:
        return by_name[squashed]
    return None
