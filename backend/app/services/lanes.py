"""
Single source of truth for "who's currently blocking this ticket."

Jira's real status vocabulary (Waiting for support / Waiting for customer /
Resolved / Pending Upgrade / Defect-Enhancement-submitted) has no concept of
Dev vs DevOps vs escalated — that distinction only exists in the team's heads
and in internal Jira comments, never in a field. So the lane is derived from,
in priority order:

  1. escalated_at (manual toggle, or auto-set when a human — not the SLA bot —
     @mentions Gisele in an internal comment)
  2. needs_csm_briefing (manual toggle — Jira has no signal for "customer
     needs a plain-English update", that's a judgment call)
  3. lane_override (manual correction when the mention-derived guess is wrong)
  4. last_mention_name, mapped through the real team roster below
  5. status: "Awaiting Customer" -> customer
  6. unassigned support tickets -> a distinct "unassigned" bucket (nobody's
     claimed it yet — the highest-priority thing to notice, not "mine")
  7. default -> me

Every view/endpoint that needs "how much is on my desk" calls waiting_on()
or compute_lanes() — never re-derives its own bucketing.
"""
from typing import Literal

from app.models.case import Case

Lane = Literal["me", "defect", "devops", "dev", "customer", "csm", "escalated", "unassigned"]

LANE_ORDER: list[Lane] = ["me", "defect", "devops", "dev", "customer", "csm", "escalated", "unassigned"]

LANE_LABELS: dict[Lane, str] = {
    "me": "Ball in my court",
    "defect": "Open Defects",
    "devops": "Waiting on DevOps",
    "dev": "Waiting on Dev",
    "customer": "Waiting on Customer",
    "csm": "Needs CSM briefing",
    "escalated": "Escalated to Gisele",
    "unassigned": "Unassigned — needs triage",
}

# Real Jira display names, confirmed against live DSD data.
DEVOPS_ROSTER = {"Martin Fure", "Elias Hjellestad"}
TEAM_LEAD = "Gisele Wolff"
SUPPORT_TEAM = {"Asaph Mulaisi", "Gisele Wolff", "Yaseen Dolan"}

# The SLA-breach automation posts internal comments and @mentions Gisele on
# every ticket approaching its SLA — that's noise, not a human handoff signal.
# Its mentions are filtered out before last_mention_name is ever set (see
# services/jira.py::_extract_last_mention), but this constant is the single
# place that identifies it if that logic needs to check it again.
BOT_ACCOUNT_NAME = "Bernhard Hafting"


def _mention_lane(name: str) -> Lane | None:
    if name in DEVOPS_ROSTER:
        return "devops"
    if name == TEAM_LEAD:
        return "escalated"
    if name in SUPPORT_TEAM:
        # Self-mentions or mentioning a teammate who isn't DevOps/Gisele
        # aren't a useful signal — fall through to the status-based default.
        return None
    # Anyone else named (a real Dev engineer) — per team convention, treat
    # any non-DevOps named individual as Dev.
    return "dev"


def waiting_on(case: Case) -> Lane:
    if case.escalated_at is not None:
        return "escalated"
    if case.needs_csm_briefing:
        return "csm"
    if case.lane_override:
        return case.lane_override  # type: ignore[return-value]

    if case.last_mention_name:
        guess = _mention_lane(case.last_mention_name)
        if guess:
            return guess

    if case.status == "Awaiting Customer":
        return "customer"
    if not case.assigned_to:
        return "unassigned"
    # A logged defect isn't really "in my court" the way a support ticket
    # is — it's waiting on a fix, not on me to work it day-to-day — but it
    # only gets its own bucket once none of the more specific signals above
    # (escalation, CSM flag, a real mention, awaiting-customer, unassigned)
    # already placed it somewhere more precise.
    if case.case_type == "Defect":
        return "defect"
    return "me"


def compute_lanes(cases: list[Case]) -> dict:
    """Group open cases into lanes with count / oldest age / share for each.

    Returns the real case objects per lane (not just ids) — a live-Jira
    ticket with no local Case row yet (see desk.py::_live_open_cases) has
    id=None, and multiple such tickets would collide if this only kept ids
    for the caller to look back up afterward."""
    buckets: dict[Lane, list[Case]] = {lane: [] for lane in LANE_ORDER}
    for case in cases:
        buckets[waiting_on(case)].append(case)

    total = len(cases) or 1
    lanes = []
    for lane in LANE_ORDER:
        rows = buckets[lane]
        oldest = max((c.days_open for c in rows), default=0)
        lanes.append({
            "lane": lane,
            "label": LANE_LABELS[lane],
            "count": len(rows),
            "oldest_days": oldest,
            "share_pct": round(len(rows) / total * 100),
            "cases": rows,
        })

    return {"total_open": len(cases), "lanes": lanes}
