# Sedna Ops — Remodel Design Brief

## What this is

Sedna Ops is an internal web app used by a single L2 support engineer at Sedna, a maritime SaaS company, to run day-to-day support operations for the Dataloy VMS (voyage management system) and Sedna Email products. It currently exists (Vue 3 + FastAPI, dark theme) but was built around the wrong mental model — a customer-health/CSM-portfolio frame borrowed from tools like Gainsight. It needs a remodel around the actual job: L2 support coordination.

## The user

One person. L2 support engineer. Not a CSM, not a manager — the technical coordination hub sitting between four other parties:

- **DevOps** — environment/infra issues, deploy windows, upgrade blockers (e.g. WF8→WF33)
- **Dev** — actual defects: root cause, reproduction, fix ETA
- **CSMs** (8 of them, covering ~533 accounts) — need plain-English translations of ticket status so they can talk to customers without technical involvement
- **Managers** — need SLA breach visibility, escalation trail, and workload/capacity signal

The user's job is to know, for every ticket they own, **who has the ball right now** — and to move it forward or flag when it's stuck too long.

## Core mental model — "ball in whose court," not "account health"

Reject the CSM-tool pattern (portfolio sorted by health score / churn risk / renewal). The organizing unit is the **ticket**, not the account, and tickets are grouped by **who's currently blocking progress**, not by customer.

Primary lanes (this is the home screen — "My Desk"):

1. **Ball in my court** — needs the user's triage, reproduction, or reply. Only section demanding action right now.
2. **Waiting on DevOps** — environment/infra blockers. Should visually escalate the longer they sit, since DevOps queues go quiet easily.
3. **Waiting on Dev** — handed-off defects. Needs root-cause status and rough fix-ETA signal, not the raw Jira ticket.
4. **Waiting on Customer** — needs a chase, nothing else.
5. **Needs CSM briefing** — technical work is done/diagnosed; next action is someone telling the customer something non-technical. A handoff queue, not a status.
6. **Escalated / manager-visible** — SLA breaches and anything blocked long enough to be a capacity problem, not a triage problem.

Real proof this model is needed: the live Jira queue currently contains a ticket open **2,310 days**. Under a flat list it has the same visual weight as a 3-day-old ticket. Under this model it would immediately surface as either forgotten or a mislabeled permanent limitation.

## Ticket rows carry context — don't make it a separate view

Each ticket row is self-contained. It shows the ticket (ref, type, priority, days open, status) plus a thin context strip so the user never has to tab away to check account details mid-triage:

- **Tier badge** (Premier / Strategic / Scale) — same bug reads differently on a $767K account vs a $400 account
- **Renewal flag** — only shown if the account renews within ~60 days; irrelevant otherwise
- **Migration flag** — only shown if the account is mid-VMS-migration; explains elevated ticket volume so it isn't misread as a problem
- **CSM name** — required for the "needs CSM briefing" lane; that's who gets handed off to

Explicitly do NOT bring back: account health scores, churn-risk tiers, NPS bands, or a portfolio view sorted by customer health. Those are CSM-owned artifacts. The user needs just enough account signal to prioritize and route correctly, not a duplicate of the CSM's dashboard.

## Screens needed

1. **My Desk (home)** — the six lanes above. Default and most-used view.
2. **Ticket detail** — single ticket, full context: Jira ref/link, environment (PROD/TEST/DEV), root cause, blocked_by, linked/duplicate tickets, resolution notes, the context strip expanded (full account info on demand, not by default).
3. **Operations** — lower-priority, less frequent: Migrations Gantt, Upgrade pipeline, SSO provisioning queue. Not competing with My Desk for primary nav weight.
4. **Support Signals** (secondary/analytical) — portfolio-wide Jira patterns: ticket volume trend, aging distribution (0–14 / 15–30 / 31–90 / 90+ / 365+ "stale"), issue type mix (Bug vs Training-gap vs Upgrade), SLA breach trend. This is where "how's the queue doing overall" lives — separate from "what do I do right now."
5. **Unmatched Jira queue** — a maintenance task, not a daily destination. Small badge/count somewhere, not top-level nav.

## Data already available (real, from the current schema)

Case: `jira_ref`, `title`, `case_type` (Upgrade/Defect/Support/Training Gap), `environment` (PROD/TEST/DEV), `status` (Active/Awaiting Dev/Awaiting Customer/Awaiting DevOps/Requested/Closed), `priority` (High/Medium/Low), `days_open`, `blocked` + `blocked_reason` + `blocked_by`, `linked_case_ref`, `assigned_to`, `resolution_note`, `escalated_at`.

Customer: `name`, `csm`, `tier` (Premier/Strategic/Scale), `arr_gbp`, `product`, `renewal_date`.

Jira live sync: polls `dataloy-cloud.atlassian.net` project DSD every 5 minutes; unmatched issues (no local account match) queue for manual assignment.

## Gaps to design around (schema will need small additions, not a rebuild)

- `status` is currently a loose string — the design should assume a clean `waiting_on` concept (Dev / DevOps / Customer / CSM / Me) exists per ticket, even though today it's inferred from status text.
- No explicit "needs CSM briefing" signal yet — treat it as a real lane the design should support, to be backed by a new flag.
- No shared "environment incident" concept — a DevOps-side outage affects many tickets at once; the design should allow one incident banner/context to cover multiple affected tickets rather than repeating the same blocker per ticket.

## Tone / visual direction

Current app is a dark-theme ops dashboard (near-black background, teal/blue accent, dense data rows) — that instinct is right for this kind of tool and can carry forward. This is a single-operator cockpit, not a marketing dashboard: prioritize scan speed, information density done cleanly, and instantly-readable urgency (color/badge, not prose) over decoration. Avoid anything that reads as a customer-facing SaaS product — this is an internal instrument panel.
