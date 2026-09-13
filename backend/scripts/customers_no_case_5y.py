"""One-off: list customers with no real support case raised in the last 5
years, using live Jira data (not the local `cases` table, which this
session already confirmed undercounts real ticket volume by ~7-10x).

Fetches every real DSD ticket created in the last 5 years with a non-empty
Customer field (paginated, ~13.4k tickets, field-limited to keep it light),
builds the set of customers who raised at least one, then diffs against the
full local Customer list (including CustomerNameAlias, so a trading-as name
recorded after the fact still resolves).
"""
import asyncio
from datetime import date, timedelta

import httpx
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.config import settings
from app.models.customer import Customer
from app.models.customer_name_alias import CustomerNameAlias
from app.services.jira import _auth, _HEADERS, _normalize_company_name, _extract_customer_name


async def fetch_active_customer_names(cutoff: str) -> set[str]:
    url = f"{settings.jira_base_url.rstrip('/')}/rest/api/3/search/jql"
    jql = f'project = "DSD" AND customfield_10047 is not EMPTY AND created >= "{cutoff}"'
    active: set[str] = set()
    page_token: str | None = None
    pages = 0
    async with httpx.AsyncClient(auth=_auth(), timeout=30, follow_redirects=True) as client:
        while True:
            params = {"jql": jql, "maxResults": 100, "fields": "customfield_10047"}
            if page_token:
                params["nextPageToken"] = page_token
            resp = await client.get(url, headers=_HEADERS, params=params)
            resp.raise_for_status()
            data = resp.json()
            for issue in data.get("issues", []):
                name = _extract_customer_name(issue["fields"].get("customfield_10047"))
                if name:
                    active.add(_normalize_company_name(name))
            pages += 1
            if pages % 20 == 0:
                print(f"  ...scanned {pages} pages, {len(active)} distinct active customers so far")
            if data.get("isLast", True):
                break
            page_token = data.get("nextPageToken")
            if not page_token:
                break
    print(f"Scanned {pages} pages total, {len(active)} distinct customers raised a case since {cutoff}")
    return active


async def main() -> None:
    cutoff = (date.today() - timedelta(days=5 * 365)).isoformat()
    print(f"Cutoff date: {cutoff}")
    active_normalized = await fetch_active_customer_names(cutoff)

    async with AsyncSessionLocal() as db:
        customers = (await db.execute(
            select(Customer.id, Customer.name, Customer.tier, Customer.csm, Customer.product)
            .where(Customer.status != "Cancelled")
        )).all()
        aliases = (await db.execute(select(CustomerNameAlias))).scalars().all()
        alias_by_customer: dict[int, list[str]] = {}
        for a in aliases:
            alias_by_customer.setdefault(a.customer_id, []).append(_normalize_company_name(a.alias_name))

        no_case_5y = []
        for cid, name, tier, csm, product in customers:
            candidates = {_normalize_company_name(name)} | set(alias_by_customer.get(cid, []))
            if not (candidates & active_normalized):
                no_case_5y.append((cid, name, tier, csm, product))

    print()
    print(f"{len(no_case_5y)} of {len(customers)} active customers raised NO real case in the last 5 years:")
    for cid, name, tier, csm, product in sorted(no_case_5y, key=lambda r: r[1]):
        print(f"  {cid:4d} | {name:45s} | {tier or '-':10s} | {csm or 'Unassigned':15s} | {product or '-'}")


if __name__ == "__main__":
    asyncio.run(main())
