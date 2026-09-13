"""Daily Ops — the single shared source of truth for "how much did each
engineer actually do, per day": Assigned, Resolved, Opened, Replies sent,
Comments made. Both My Desk's daily panel and Command Center's window
aggregate read from this one function rather than each computing their own
version of "resolved count" — see the plan discussion this was built from
for why that mattered (three slightly-different resolved computations
existed before).

Each dimension deliberately uses whichever Jira mechanism is actually
correct for it, not a single "best-effort" approach applied everywhere:
Assigned, Resolved, and Opened come from real Jira history (changelog /
resolution date / creation date) covering every ticket regardless of local
mapping; Replies/Comments need a candidate-set-plus-fetch approach since
Jira has no history operator for comments. See jira.py's
team_daily_assigned/team_daily_resolved/team_daily_created/
team_daily_replies_comments docstrings for the specifics of each.
"""
import asyncio
from datetime import date, timedelta

from app.services.jira import (
    stats_fetched_at,
    team_daily_assigned,
    team_daily_created,
    team_daily_replies_comments,
    team_daily_resolved,
)

# Mirrors the exact cache_key tuples each function below builds internally
# (see their own `cache_key = (...)` lines in jira.py) — used only to look
# up stats_fetched_at() after the real fetch, never passed to the functions
# themselves.
def _cache_keys(team: list[str], days: int) -> list[tuple]:
    t = tuple(sorted(team))
    return [
        ("daily_resolved", t, days),
        ("daily_created", t, days),
        ("daily_assigned", t, days),
        ("daily_replies_comments", t, days),
    ]


async def daily_ops_stats(db, team: list[str], days: int = 30) -> dict:
    """Returns {"days": [{"date": "YYYY-MM-DD", "engineers": {name: {assigned,
    resolved, fresh_resolved, opened, replies, comments}}, "resolved_tickets":
    [...], "opened_tickets": [...]}]} for the last `days` calendar days
    (oldest first), plus a "totals" block summing the whole window per
    engineer — the same shape My Desk's trend sparklines and Command
    Center's window aggregate both consume, just sliced differently (today
    = last day's entry; aggregate = totals block).

    resolved_tickets/opened_tickets carry the real per-ticket detail (ref,
    title, assignee, customer) behind that day's count — added so Command
    Center's Closed/Opened Tickets panels can be drillable.

    fresh_resolved is the subset of `resolved` whose last real activity
    (comment/status-change/creation) actually fell inside this window —
    "resolved minus fresh_resolved" is backlog clearance: closed now, but
    not actually worked on now. fresh_assigned is the analogous subset of
    `assigned`: a reassignment whose ticket was itself created inside this
    window (genuinely new work) vs. an older ticket just changing hands
    (rebalancing). See team_daily_resolved()/team_daily_assigned()'s
    docstrings for why each is anchored to real Jira timestamps rather than
    a second number the reader has to interpret alongside the raw count.
    """
    # Concurrent, not sequential — these are independent live-Jira fetches
    # with no data dependency between them. Running them one after another
    # was already borderline before the fresh/backlog comment-fetch made
    # team_daily_resolved alone cost ~11s at 30 days; confirmed live this
    # dropped the whole call from 43.1s (sequential) to roughly the single
    # slowest fetch instead of their sum.
    #
    # team_daily_resolved and team_daily_replies_comments both now touch the
    # DB-backed comment cache with this same `db` session (see
    # _cached_comments_batch()) — a single AsyncSession can't be used
    # concurrently (confirmed live elsewhere this session:
    # InvalidRequestError), so those two are awaited sequentially inside
    # one task, still running concurrently as a unit alongside the two
    # non-DB fetches.
    async def _db_touching():
        resolved = await team_daily_resolved(db, team, days)
        replies_comments = await team_daily_replies_comments(db, team, days)
        return resolved, replies_comments

    (resolved_result, replies_comments_by_day), opened_result, assigned_result = await asyncio.gather(
        _db_touching(),
        team_daily_created(team, days),
        team_daily_assigned(team, days),
    )
    resolved_by_day = resolved_result["by_day"]
    fresh_resolved_by_day = resolved_result["fresh_by_day"]
    resolved_tickets_by_day = resolved_result["tickets_by_day"]
    opened_by_day = opened_result["by_day"]
    opened_tickets_by_day = opened_result["tickets_by_day"]
    assigned_by_day = assigned_result["by_day"]
    fresh_assigned_by_day = assigned_result["fresh_by_day"]

    today = date.today()
    start = today - timedelta(days=days - 1)

    days_list = []
    totals = {n: {"assigned": 0, "fresh_assigned": 0, "resolved": 0, "fresh_resolved": 0, "opened": 0, "replies": 0, "comments": 0} for n in team}

    for i in range(days):
        d = start + timedelta(days=i)
        key = d.isoformat()
        assigned_row = assigned_by_day.get(key, {n: 0 for n in team})
        fresh_assigned_row = fresh_assigned_by_day.get(key, {n: 0 for n in team})
        resolved_row = resolved_by_day.get(key, {n: 0 for n in team})
        fresh_resolved_row = fresh_resolved_by_day.get(key, {n: 0 for n in team})
        opened_row = opened_by_day.get(key, {n: 0 for n in team})
        rc_row = replies_comments_by_day.get(key, {n: {"replies": 0, "comments": 0} for n in team})

        engineers = {}
        for n in team:
            row = {
                "assigned": assigned_row.get(n, 0),
                "fresh_assigned": fresh_assigned_row.get(n, 0),
                "resolved": resolved_row.get(n, 0),
                "fresh_resolved": fresh_resolved_row.get(n, 0),
                "opened": opened_row.get(n, 0),
                "replies": rc_row.get(n, {}).get("replies", 0),
                "comments": rc_row.get(n, {}).get("comments", 0),
            }
            engineers[n] = row
            for k, v in row.items():
                totals[n][k] += v

        days_list.append({
            "date": key,
            "engineers": engineers,
            "resolved_tickets": resolved_tickets_by_day.get(key, []),
            "opened_tickets": opened_tickets_by_day.get(key, []),
        })

    # The oldest of the four underlying fetches — an honest "as of" bound
    # for the whole panel: if any one dimension is serving a cached (up to
    # jira_stats_cache_ttl_seconds-old) snapshot, the panel as a whole is
    # only as fresh as that one. None only if a key was somehow never
    # fetched (shouldn't happen here — all four were just awaited above).
    fetched_ats = [stats_fetched_at(k) for k in _cache_keys(team, days)]
    fetched_at = min((f for f in fetched_ats if f is not None), default=None)

    return {"days": days, "series": days_list, "totals": totals, "fetched_at": fetched_at}
