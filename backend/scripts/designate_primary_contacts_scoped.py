"""Same logic as designate_primary_contacts.py, scoped to specific customer
ids — used for a small follow-up batch (newly-added multi-contact
customers) without re-running the full 60-customer live-Jira sweep again."""
import asyncio
import sys

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.customer import Customer
from app.models.customer_contact import CustomerContact
from app.services.jira import _auth
import httpx
from scripts.designate_primary_contacts import discover_option_value, fetch_reporters, pick_heuristic


async def main(customer_ids: list[int]) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids)))
        customers = result.all()

        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            for cid, cname in customers:
                contacts_result = await db.execute(select(CustomerContact).where(CustomerContact.customer_id == cid))
                contacts = contacts_result.scalars().all()
                emails = [c.email for c in contacts]

                chosen_email: str | None = None
                reason: str | None = None
                try:
                    option_value = await discover_option_value(client, cname)
                    if option_value:
                        reporter_stats = await fetch_reporters(client, option_value)
                        matches = [
                            (e, reporter_stats[e.lower()]["count"], reporter_stats[e.lower()]["last_created"])
                            for e in emails if e.lower() in reporter_stats
                        ]
                        if matches:
                            matches.sort(key=lambda m: (-m[1], -(m[2].timestamp() if m[2] else 0)))
                            chosen_email, count, last = matches[0]
                            reason = f"real activity: {count} ticket(s) reported, most recent {last.date() if last else 'unknown'}"
                except Exception as exc:  # noqa: BLE001
                    print(f"  [warn] {cname}: Jira lookup failed ({exc}), falling back to heuristic")

                if not chosen_email:
                    chosen_email, reason = pick_heuristic(emails)

                for c in contacts:
                    c.is_primary = (c.email == chosen_email)
                    c.primary_contact_reason = reason if c.email == chosen_email else None
                print(f"{cname:35s} -> {chosen_email:40s} ({reason})")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    ids = [int(a) for a in sys.argv[1:]]
    asyncio.run(main(ids))
