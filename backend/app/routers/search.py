"""Global search — the "type part of anything about a customer and get them"
search bar (top bar on every page + the Customers page).

Matches, within the VMS customer scope only:
  customer name, name aliases, instance subdomains (PROD/TEST/DEV),
  contact emails, and Jira cases (ref or title).
Ranked in Python — the whole searchable set is a few hundred rows (67 VMS
customers, ~112 instances, ~540 contacts) plus a SQL-filtered slice of
cases, so no search index is needed. Each hit says *what* matched so the UI
can show and highlight it ("instance: sfl-test", "contact: ops@…").
"""
import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.database import get_db
from app.models.case import Case
from app.models.customer import Customer
from app.models.customer_contact import CustomerContact
from app.models.customer_name_alias import CustomerNameAlias

router = APIRouter(prefix="/search", tags=["search"])

_JIRA_REF = re.compile(r"^[A-Za-z]+-\d+$")


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _score(text: str | None, q: str) -> int:
    """0 = no match. Exact > prefix > word-start > anywhere; a squashed
    comparison catches punctuation/spacing differences ("safeen" ↔
    "Safe-en", "ac orssleff" ↔ "A.C. Ørssleff" partially)."""
    if not text:
        return 0
    t, ql = text.lower(), q.lower()
    if t == ql:
        return 100
    if t.startswith(ql):
        return 80
    if re.search(r"(^|[\s\-_.@/(])" + re.escape(ql), t):
        return 65
    if ql in t:
        return 45
    sq, sql = _squash(text), _squash(q)
    if sql and len(sql) >= 3 and sql in sq:
        return 35
    return 0


# How much each kind of match is worth relative to a name match.
_WEIGHT = {"name": 1.0, "alias": 0.9, "instance": 0.9, "contact": 0.7, "case": 0.6}


@router.get("")
async def search(q: str = Query("", max_length=100), limit: int = 12, db: AsyncSession = Depends(get_db)):
    q = q.strip()
    if len(q) < 2:
        return {"query": q, "customers": [], "cases": []}

    customers = (await db.execute(
        select(Customer).options(selectinload(Customer.tenant_info))
        .where(Customer.product.ilike("%vms%"))
    )).scalars().all()
    by_id = {c.id: c for c in customers}
    best: dict[int, dict] = {}

    def hit(cid: int, field: str, text: str, raw: int) -> None:
        if not raw or cid not in by_id:
            return
        score = raw * _WEIGHT[field]
        if cid not in best or score > best[cid]["score"]:
            best[cid] = {"score": score, "field": field, "text": text}

    for c in customers:
        hit(c.id, "name", c.name, _score(c.name, q))
        for t in c.tenant_info:
            host = t.subdomain if "." in t.subdomain else f"{t.subdomain}.dataloy.com"
            hit(c.id, "instance", f"{t.environment} · {host}", _score(t.subdomain, q))

    for a in (await db.execute(select(CustomerNameAlias))).scalars():
        hit(a.customer_id, "alias", a.alias_name, _score(a.alias_name, q))

    like = f"%{q}%"
    for ct in (await db.execute(select(CustomerContact).where(CustomerContact.email.ilike(like)))).scalars():
        hit(ct.customer_id, "contact", ct.email, _score(ct.email, q))

    # Cases: an exact Jira ref is the strongest possible signal; otherwise
    # match on title. Shown as their own group and also credit the customer.
    case_q = select(Case).options(joinedload(Case.customer)).where(Case.customer_id.in_(list(by_id)))
    if _JIRA_REF.match(q):
        case_q = case_q.where(Case.jira_ref.ilike(q))
    else:
        case_q = case_q.where(or_(Case.jira_ref.ilike(like), Case.title.ilike(like))).order_by(Case.created_at.desc()).limit(40)
    case_hits = []
    for cs in (await db.execute(case_q)).scalars():
        raw = 100 if cs.jira_ref.lower() == q.lower() else max(_score(cs.jira_ref, q), _score(cs.title, q))
        case_hits.append({"score": raw, "jira_ref": cs.jira_ref, "title": cs.title, "status": cs.status,
                          "customer_id": cs.customer_id, "customer_name": cs.customer.name if cs.customer else None})
        hit(cs.customer_id, "case", f"{cs.jira_ref} — {cs.title}", raw)

    ranked = sorted(best.items(), key=lambda kv: (-kv[1]["score"], by_id[kv[0]].name))[:limit]
    out = []
    for cid, m in ranked:
        c = by_id[cid]
        envs = sorted({t.environment for t in c.tenant_info}, key=lambda e: {"PROD": 0, "TEST": 1}.get(e, 2))
        out.append({
            "customer_id": cid, "name": c.name, "tier": c.tier, "csm": c.csm, "prod_version": c.prod_version,
            "environments": envs, "match_field": m["field"], "match_text": m["text"], "score": round(m["score"]),
        })
    cases = sorted(case_hits, key=lambda h: -h["score"])[:6]
    return {"query": q, "customers": out, "cases": cases}
