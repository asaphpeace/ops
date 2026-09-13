import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.services.tenant_info import fetch_tenant_info, generate_tenant_candidates

router = APIRouter(prefix="/tenant-discovery", tags=["tenant-discovery"])

# Considerate toward real customer-owned infrastructure — never fire 100+
# probes at once. Bounds total concurrency across the whole run, not just
# per customer.
_CONCURRENCY = asyncio.Semaphore(5)


class DiscoveryRunRequest(BaseModel):
    customer_ids: list[int] | None = None  # None = every VMS customer missing PROD or TEST


class DiscoveryAcceptRequest(BaseModel):
    customer_id: int
    environment: str
    subdomain: str
    release: str | None = None
    reported_environment: str | None = None
    is_azure_installation: bool | None = None
    is_auth0_installation: bool | None = None
    is_jvms_mode: bool | None = None
    is_pure_web: bool | None = None


async def _probe_one(customer: Customer, environment: str, candidates: list[str]) -> dict:
    async with _CONCURRENCY:
        for candidate in candidates:
            result = await fetch_tenant_info(candidate)
            if not result.error:
                data = result.data or {}
                reported_env = data.get("environment")
                return {
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "environment": environment,
                    "tried": candidates,
                    "matched_candidate": candidate,
                    "release": data.get("release"),
                    "reported_environment": reported_env,
                    "env_matches_guess": bool(reported_env) and reported_env.lower() == environment.lower(),
                    "is_azure_installation": data.get("isAzureInstallation"),
                    "is_auth0_installation": data.get("isAuth0Installation"),
                    "is_jvms_mode": data.get("jvmsMode"),
                    "is_pure_web": data.get("isPureWeb"),
                    "error": None,
                }
        return {
            "customer_id": customer.id,
            "customer_name": customer.name,
            "environment": environment,
            "tried": candidates,
            "matched_candidate": None,
            "release": None,
            "reported_environment": None,
            "env_matches_guess": False,
            "error": "No candidate resolved",
        }


@router.post("/run")
async def run_discovery(data: DiscoveryRunRequest, db: AsyncSession = Depends(get_db)):
    """Pure discovery — probes real candidate subdomains for PROD/TEST but
    never writes anything to customer_tenant_info. The probe response has no
    company-identifying field (confirmed: just release/environment/etc), so
    a wrong candidate guess that happens to hit a real different company's
    tenant would look like a valid match with no way to catch it here —
    every result needs a human Accept via /tenant-discovery/accept, never
    auto-saved."""
    query = select(Customer).where(Customer.product.ilike("%VMS%"))
    if data.customer_ids is not None:
        query = query.where(Customer.id.in_(data.customer_ids))
    customers = (await db.execute(query)).scalars().all()

    existing = (await db.execute(select(CustomerTenantInfo))).scalars().all()
    existing_envs: dict[int, set[str]] = {}
    for row in existing:
        existing_envs.setdefault(row.customer_id, set()).add(row.environment)

    tasks = []
    for customer in customers:
        candidates_by_env = generate_tenant_candidates(customer.name)
        for environment, candidates in candidates_by_env.items():
            if environment in existing_envs.get(customer.id, set()):
                continue  # already has a real row for this environment — nothing to discover
            tasks.append(_probe_one(customer, environment, candidates))

    results = await asyncio.gather(*tasks) if tasks else []
    results.sort(key=lambda r: (r["matched_candidate"] is None, not r["env_matches_guess"]))
    return results


@router.post("/accept", response_model=None)
async def accept_discovery(data: DiscoveryAcceptRequest, db: AsyncSession = Depends(get_db)):
    """Persists exactly what /run already probed — never re-probes. Mirrors
    set_tenant_subdomain()'s upsert-by-(customer_id, environment) plus
    sync_tenant_info()'s post-probe field writes, so an accepted discovery
    result looks identical to a normal manual sync's outcome."""
    result = await db.execute(
        select(CustomerTenantInfo).where(
            CustomerTenantInfo.customer_id == data.customer_id,
            CustomerTenantInfo.environment == data.environment,
        )
    )
    row = result.scalar_one_or_none()
    if not row:
        row = CustomerTenantInfo(customer_id=data.customer_id, environment=data.environment, subdomain=data.subdomain)
        db.add(row)
    else:
        row.subdomain = data.subdomain

    row.release = data.release
    row.reported_environment = data.reported_environment
    row.is_azure_installation = data.is_azure_installation
    row.is_auth0_installation = data.is_auth0_installation
    row.is_jvms_mode = data.is_jvms_mode
    row.is_pure_web = data.is_pure_web
    row.last_synced_at = datetime.utcnow()
    row.last_sync_error = None

    if data.release and data.environment in ("PROD", "TEST"):
        customer = (await db.execute(select(Customer).where(Customer.id == data.customer_id))).scalar_one_or_none()
        if customer:
            if data.environment == "PROD":
                customer.prod_version = data.release
            else:
                customer.test_version = data.release

    await db.commit()
    await db.refresh(row)
    return {
        "id": row.id, "customer_id": row.customer_id, "environment": row.environment,
        "subdomain": row.subdomain, "release": row.release, "last_synced_at": row.last_synced_at,
    }
