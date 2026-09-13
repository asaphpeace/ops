from datetime import datetime, date, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.sso_onboarding import SSOOnboarding
from app.models.customer import Customer

router = APIRouter(prefix="/sso", tags=["sso"])

STAGES = ["Not Started", "Email Sent", "Awaiting Reply", "DevOps Configuring", "SSO Live"]
OVERDUE_DAYS = 7  # Email Sent or Awaiting Reply rows become overdue after this many days


def _overdue_days(record: SSOOnboarding) -> int | None:
    """Days overdue for Email Sent / Awaiting Reply — None if not applicable."""
    if record.stage not in ("Email Sent", "Awaiting Reply"):
        return None
    ref = record.reply_received_at or record.email_sent_at
    if not ref:
        return None
    now = datetime.now(timezone.utc)
    ref_aware = ref.replace(tzinfo=timezone.utc) if ref.tzinfo is None else ref
    days = (now - ref_aware).days
    return max(0, days - OVERDUE_DAYS) if days >= OVERDUE_DAYS else None


def _enrich(r: SSOOnboarding) -> dict:
    d = {col.name: getattr(r, col.name) for col in r.__table__.columns}
    if r.customer:
        d["customer_name"] = r.customer.name
        d["customer_tier"] = r.customer.tier
        d["customer_csm"] = r.customer.csm
    # Computed
    d["overdue_days"] = _overdue_days(r)
    # Auto-escalate: if Email Sent and email_sent_at > OVERDUE_DAYS, treat as Awaiting Reply display
    if r.stage == "Email Sent" and d["overdue_days"] is not None:
        d["display_stage"] = "Awaiting Reply"
    else:
        d["display_stage"] = r.stage
    return d


@router.get("")
async def list_sso(db: AsyncSession = Depends(get_db)):
    q = (
        select(SSOOnboarding)
        .options(joinedload(SSOOnboarding.customer))
        .order_by(SSOOnboarding.stage, SSOOnboarding.customer_id)
    )
    result = await db.execute(q)
    records = result.scalars().all()
    # Sort: SSO Live last (done), then by stage order, overdue first within stage
    stage_order = {s: i for i, s in enumerate(STAGES)}
    def sort_key(r):
        d = _enrich(r)
        overdue = -(d["overdue_days"] or 0)  # more overdue = higher priority
        return (stage_order.get(r.stage, 99), overdue)
    records.sort(key=sort_key)
    return [_enrich(r) for r in records]


@router.get("/stats")
async def sso_stats(db: AsyncSession = Depends(get_db)):
    q = select(SSOOnboarding).options(joinedload(SSOOnboarding.customer))
    result = await db.execute(q)
    records = result.scalars().all()
    stats = {s: 0 for s in STAGES}
    for r in records:
        stats[r.stage] = stats.get(r.stage, 0) + 1
    done = [r for r in records if r.stage == "SSO Live" and r.switchover_duration_mins]
    avg_switchover = (
        round(sum(r.switchover_duration_mins for r in done) / len(done)) if done else None
    )
    return {
        "total": len(records),
        "by_stage": stats,
        "avg_switchover_mins": avg_switchover,
    }


@router.post("")
async def create_sso(data: dict, db: AsyncSession = Depends(get_db)):
    customer_id = data.pop("customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=422, detail="customer_id required")
    cust = await db.get(Customer, customer_id)
    if not cust:
        raise HTTPException(status_code=404, detail="Customer not found")
    record = SSOOnboarding(customer_id=customer_id, **{k: v for k, v in data.items() if hasattr(SSOOnboarding, k) and k not in ("id",)})
    db.add(record)
    await db.commit()
    await db.refresh(record)
    await db.refresh(record, ["customer"])
    return _enrich(record)


@router.patch("/{sso_id}")
async def update_sso(sso_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SSOOnboarding).where(SSOOnboarding.id == sso_id).options(joinedload(SSOOnboarding.customer))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="SSO record not found")
    for key, value in data.items():
        if hasattr(record, key) and key not in ("id", "customer_id"):
            setattr(record, key, value)
    record.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(record)
    return _enrich(record)


@router.post("/{sso_id}/log-reply")
async def log_reply(sso_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    """Record the customer's reply fields and advance stage to DevOps Configuring."""
    result = await db.execute(
        select(SSOOnboarding).where(SSOOnboarding.id == sso_id).options(joinedload(SSOOnboarding.customer))
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="SSO record not found")

    # Apply provided fields
    for field in ("field_domain", "field_client_id", "field_secret", "field_reply_url", "field_app_id_uri"):
        if field in data and data[field]:
            setattr(record, field, data[field])

    if "it_contact_name" in data:
        record.it_contact_name = data["it_contact_name"]
    if "it_contact_email" in data:
        record.it_contact_email = data["it_contact_email"]

    record.reply_received_at = datetime.utcnow()
    # Advance stage only if required fields are present
    has_required = all([record.field_domain, record.field_client_id, record.field_secret, record.field_reply_url])
    if has_required:
        record.stage = "DevOps Configuring"
        record.devops_started_at = datetime.utcnow()

    record.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(record)
    return _enrich(record)


@router.post("/seed")
async def seed_sso(db: AsyncSession = Depends(get_db)):
    """Seed SSO records for existing customers based on their name."""
    from sqlalchemy import text
    # Wipe existing
    await db.execute(text("DELETE FROM sso_onboarding"))
    await db.commit()

    q = select(Customer).order_by(Customer.name)
    result = await db.execute(q)
    customers = result.scalars().all()

    now = datetime.utcnow()

    seed_map = {
        # name_fragment → (stage, has_prod, has_test, extras)
        "Global Carriers": ("SSO Live", True, True, {
            "email_sent_at": now - timedelta(days=80),
            "guest_invite_sent": True,
            "reply_received_at": now - timedelta(days=78),
            "field_domain": "globalcarriers.onmicrosoft.com",
            "field_client_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
            "field_secret": "••••••••••••••••",
            "field_reply_url": "https://sedna.globalcarriers.com/callback",
            "devops_started_at": now - timedelta(days=76),
            "switchover_at": now - timedelta(days=71),
            "switchover_duration_mins": 12,
            "it_contact_name": "Lars Hansen",
            "it_contact_email": "it@globalcarriers.com",
        }),
        "Seagull Maritime": ("SSO Live", True, True, {
            "email_sent_at": now - timedelta(days=104),
            "guest_invite_sent": True,
            "reply_received_at": now - timedelta(days=102),
            "field_domain": "seagull-maritime.onmicrosoft.com",
            "field_client_id": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "field_secret": "••••••••••••••••",
            "field_reply_url": "https://sedna.seagullmaritime.com/callback",
            "field_app_id_uri": "api://b2c3d4e5-f6a7-8901-bcde-f12345678901",
            "devops_started_at": now - timedelta(days=100),
            "switchover_at": now - timedelta(days=95),
            "switchover_duration_mins": 18,
            "it_contact_name": "Ingrid Nilsen",
            "it_contact_email": "ingrid.nilsen@seagull.no",
        }),
        "Balena Shipping": ("DevOps Configuring", True, False, {
            "email_sent_at": now - timedelta(days=11),
            "guest_invite_sent": True,
            "reply_received_at": now - timedelta(days=9),
            "field_domain": "balena-dmcc.onmicrosoft.com",
            "field_client_id": "c3d4e5f6-a7b8-9012-cdef-123456789012",
            "field_secret": "••••••••••••••••",
            "field_reply_url": "https://sedna.balena.ae/callback",
            "devops_started_at": now - timedelta(days=1),
            "it_contact_name": "Ahmed Al-Rashid",
            "it_contact_email": "it.admin@balena.ae",
            "follow_up_date": (now + timedelta(days=2)).date(),
        }),
        "BBC Chartering": ("Awaiting Reply", True, True, {
            "email_sent_at": now - timedelta(days=9),
            "guest_invite_sent": True,
            "it_contact_name": "Klaus Weber",
            "it_contact_email": "it@bbc-chartering.com",
            "follow_up_date": now.date(),
        }),
        "NAT Chartering": ("Email Sent", True, True, {
            "email_sent_at": now - timedelta(days=4),
            "guest_invite_sent": True,
            "it_contact_name": "Ola Svendsen",
            "it_contact_email": "it@nat-chartering.no",
            "follow_up_date": (now + timedelta(days=3)).date(),
        }),
    }

    # All other customers default to Not Started
    created = 0
    for cust in customers:
        match = next((v for k, v in seed_map.items() if k.lower() in cust.name.lower()), None)
        if match:
            stage, has_prod, has_test, extras = match
        else:
            # Only seed Not Started for customers that have SSO column != None in customer table
            stage, has_prod, has_test, extras = "Not Started", True, False, {}

        # Avoid duplicates — only seed a subset to keep the table manageable
        if stage == "Not Started" and created >= 9:
            continue

        record = SSOOnboarding(
            customer_id=cust.id,
            stage=stage,
            has_prod=has_prod,
            has_test=has_test,
            **extras,
        )
        db.add(record)
        created += 1

    await db.commit()
    return {"seeded": created}
