"""One-off: designate exactly one primary/technical contact per customer
with more than 1 stored CustomerContact row.

Real signal first: discover the customer's Jira Customer-field option value
(same mechanism customer_case_stats() already uses), fetch their recent
tickets' reporter field, and rank by frequency (ticket count) then recency
(most recent ticket date) among reporters whose email matches a stored
contact. Falls back to a personal-vs-role-inbox heuristic (prefer a named
person over a generic shared inbox like info@/sales@/accounts@) when no
real ticket-reporter match exists — flagged plainly via
primary_contact_reason, not disguised as a measured pick.

Run once via `docker compose exec api python3 scripts/designate_primary_contacts.py`.
"""
import asyncio
import re
from collections import defaultdict
from datetime import datetime, timezone

import httpx
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.config import settings
from app.models.customer import Customer
from app.models.customer_contact import CustomerContact
from app.services.jira import _auth, _HEADERS, _normalize_company_name, _extract_customer_name

ROLE_INBOX_PATTERN = re.compile(
    r"^(info|sales|support|accounts?|accounting|admin|contact|contactteam|office|finance|"
    r"operations?|chartering|dry|crewcv|marketing|press|career|parcel|hr|noreply|no-reply)[@.]",
    re.IGNORECASE,
)


async def discover_option_value(client: httpx.AsyncClient, customer_name: str) -> str | None:
    target_norm = _normalize_company_name(customer_name)
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    page_token: str | None = None
    for _ in range(20):
        params = {
            "jql": 'project = "DSD" AND customfield_10047 is not EMPTY ORDER BY updated DESC',
            "maxResults": 100, "fields": "customfield_10047",
        }
        if page_token:
            params["nextPageToken"] = page_token
        resp = await client.get(url, headers=_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        for issue in data.get("issues", []):
            name = _extract_customer_name(issue["fields"].get("customfield_10047"))
            if name and _normalize_company_name(name) == target_norm:
                return issue["fields"]["customfield_10047"]["value"]
        if data.get("isLast", True):
            break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return None


async def fetch_reporters(client: httpx.AsyncClient, option_value: str) -> dict[str, dict]:
    """email(lower) -> {"count": int, "last_created": datetime}, real
    portal-customer reporters only (accountType == "customer" — the only
    type that ever exposes a real email, confirmed live earlier today)."""
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    jql = f'project = "DSD" AND cf[10047] = "{option_value}" ORDER BY created DESC'
    out: dict[str, dict] = defaultdict(lambda: {"count": 0, "last_created": None})
    page_token: str | None = None
    fetched = 0
    # Recency-weighted sample — most recent 300 tickets is plenty to find a
    # real, currently-active point of contact without an expensive full scan.
    while fetched < 300:
        params = {"jql": jql, "maxResults": 100, "fields": "reporter,created"}
        if page_token:
            params["nextPageToken"] = page_token
        resp = await client.get(url, headers=_HEADERS, params=params)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        fetched += len(issues)
        for issue in issues:
            f = issue["fields"]
            reporter = f.get("reporter") or {}
            if reporter.get("accountType") != "customer":
                continue
            reporter_email = reporter.get("emailAddress")
            if not reporter_email:
                continue
            created = issue["fields"].get("created")
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00")) if created else None
            key = reporter_email.lower()
            out[key]["count"] += 1
            if created_dt and (out[key]["last_created"] is None or created_dt > out[key]["last_created"]):
                out[key]["last_created"] = created_dt
        if data.get("isLast", True):
            break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return out


def pick_heuristic(emails: list[str]) -> tuple[str, str]:
    personal = [e for e in emails if not ROLE_INBOX_PATTERN.match(e)]
    if personal:
        return sorted(personal)[0], "heuristic: personal-looking address, no ticket-reporter activity found"
    return sorted(emails)[0], "heuristic: only generic role inboxes on file, no ticket-reporter activity found"


async def main() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Customer.id, Customer.name).join(CustomerContact, CustomerContact.customer_id == Customer.id)
            .group_by(Customer.id, Customer.name)
            .having(func.count(CustomerContact.id) > 1)
        )
        customers = result.all()
        print(f"{len(customers)} customers with >1 stored contact")

        async with httpx.AsyncClient(auth=_auth(), timeout=20, follow_redirects=True) as client:
            for cid, cname in customers:
                contacts_result = await db.execute(
                    select(CustomerContact).where(CustomerContact.customer_id == cid)
                )
                contacts = contacts_result.scalars().all()
                emails = [c.email for c in contacts]

                chosen_email: str | None = None
                reason: str | None = None
                try:
                    option_value = await discover_option_value(client, cname)
                    if option_value:
                        reporter_stats = await fetch_reporters(client, option_value)
                        # Match real reporter activity against stored contacts
                        matches = [
                            (e, reporter_stats[e.lower()]["count"], reporter_stats[e.lower()]["last_created"])
                            for e in emails if e.lower() in reporter_stats
                        ]
                        if matches:
                            matches.sort(key=lambda m: (-m[1], -(m[2].timestamp() if m[2] else 0)))
                            chosen_email, count, last = matches[0]
                            reason = f"real activity: {count} ticket(s) reported, most recent {last.date() if last else 'unknown'}"
                except Exception as exc:  # noqa: BLE001 — best-effort per customer, never abort the batch
                    print(f"  [warn] {cname}: Jira lookup failed ({exc}), falling back to heuristic")

                if not chosen_email:
                    chosen_email, reason = pick_heuristic(emails)

                for c in contacts:
                    c.is_primary = (c.email == chosen_email)
                    c.primary_contact_reason = reason if c.email == chosen_email else None
                print(f"{cname:45s} -> {chosen_email:40s} ({reason})")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
