"""One-off cleanup: consolidate duplicate active Upgrade rows.

Confirmed live (2026-08-27): 11 customers each had 2-10 active Upgrade rows
all targeting the same environment+to_version, none ever advanced past
Requested/DevOps Approval — root cause was _ensure_upgrade_from_ticket()
only deduping by jira_ref, not by customer+environment (fixed separately in
services/jira.py). This script consolidates the existing duplicates it
already created: keeps the one furthest along PIPELINE_STAGES (tie-broken
by most recent created_at) per group, cancels the rest.

Run once via: docker compose exec api python3 scripts/consolidate_duplicate_upgrades.py
"""
import asyncio
import sys
from collections import defaultdict

sys.path.insert(0, ".")

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.upgrade import Upgrade

PIPELINE_STAGES = [
    "Requested",
    "DevOps Approval",
    "Cust. Confirmed",
    "Scheduled",
    "In Progress",
    "Verified Done",
]


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Upgrade).where(Upgrade.stage.notin_(("Verified Done", "Cancelled")))
        )
        upgrades = result.scalars().all()

        groups: dict[tuple, list[Upgrade]] = defaultdict(list)
        for u in upgrades:
            groups[(u.customer_id, u.environment, u.to_version)].append(u)

        dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
        print(f"Found {len(dup_groups)} duplicate groups covering {sum(len(v) for v in dup_groups.values())} rows.\n")

        total_cancelled = 0
        for (customer_id, environment, to_version), rows in dup_groups.items():
            rows.sort(key=lambda u: (PIPELINE_STAGES.index(u.stage), u.created_at), reverse=True)
            survivor = rows[0]
            duplicates = rows[1:]
            print(f"Customer {customer_id} · {environment} · {to_version}: keeping {survivor.jira_ref} ({survivor.stage}), cancelling {len(duplicates)} — {[d.jira_ref for d in duplicates]}")
            for d in duplicates:
                d.stage = "Cancelled"
                db.add(AuditLog(
                    actor="system", action="upgrade.duplicate_cancelled",
                    target_type="upgrade", target_id=d.jira_ref,
                    detail=f"Consolidated into {survivor.jira_ref} (same customer/environment/version)",
                ))
                total_cancelled += 1

        await db.commit()
        print(f"\nDone. {total_cancelled} duplicate rows moved to Cancelled across {len(dup_groups)} customers.")


asyncio.run(main())
