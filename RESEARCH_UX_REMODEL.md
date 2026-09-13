# Sedna Ops UX Remodel — Research Report

**Date:** 2026-08-21  
**Scope:** Navigation/IA remodel, Jira data interpretation, CSM workflow alignment  
**Context:** 8 CSMs, 533 accounts, two products (Dataloy VMS + Sedna Email), Jira integration (DSD project)

---

## 1. Generic CSM Tool Patterns — What the Best Tools Do

The leading CSM platforms — Gainsight, Vitally, ChurnZero, Planhat — have independently converged on roughly the same information architecture because it maps to how CSMs actually work. The structure is three-layer: a **command center** (what do I do today?), a **portfolio view** (how are all my accounts doing?), and an **account 360** (everything about this one customer). Every good tool nails all three and makes it fast to move between them.

**The command center** is the CSM's morning starting point. Gainsight calls it "Cockpit" — it lists all open CTAs (calls to action), tasks, and urgent flags sorted by due date and priority. Vitally's equivalent is a "Today" feed showing scheduled calls, overdue actions, and health alerts that fired overnight. ChurnZero adds real-time alerts triggered by behavioral thresholds. The mental model is: open the app, see exactly what needs attention today, work it down. The worst tools (and many internal ops dashboards) skip this entirely and dump the user into a raw account list, forcing them to reconstruct their own priority queue every morning.

**The portfolio view** answers the question "how is my book of business doing?" at a glance. Every good platform shows accounts sorted by health score or risk flag, with the ability to filter by tier, renewal date, or flag type. The key design insight: this view is not for finding a specific customer (that's search), it's for pattern recognition — spotting the cluster of amber accounts that need proactive outreach before they go red. Vitally handles this well by showing health score, product tier, and the "last CSM touchpoint" date in a single dense row. Planhat is widely praised for its clean data model and exceptional visual design — it makes the portfolio feel manageable rather than overwhelming. The tension between portfolio and account views is resolved by keeping portfolio interactions shallow and fast (hover to see key metrics, click to open the 360), rather than turning the portfolio into a table of endless columns.

**The account 360** is the single-customer deep dive. Gainsight's C360 is the canonical example: a tabbed layout with health trend, timeline, contacts, open tasks, product usage, survey scores, and renewal data. The critical UX lesson from the C360 is that it should feel like a "source of truth" not a "form to fill in." CSMs need to read context fast, log something quickly, then exit. The most common failure mode is tabs that require too many clicks to find the one piece of information the CSM actually needs. Vitally solves this by surfacing the three most important signals (health, last touchpoint, renewal date) as a persistent header that stays visible regardless of which tab is active.

**Signal surfacing vs data burial** is the defining quality gap between good and bad CSM tools. Gainsight and ChurnZero show aggregate indicators at the top level — health score, churn risk tier, NPS band — and only surface raw data (individual support tickets, individual events) when the user drills down. Tools that invert this and show raw data at the top level (long ticket lists, raw Jira issues, uninterpreted event logs) force the CSM to do the cognitive work of pattern recognition themselves. At 533 accounts split across 8 CSMs (about 66 accounts per CSM on average), that cognitive overhead is not sustainable.

---

## 2. Jira Aggregation for CS Teams — Specific Patterns and Metrics

The core problem with surfacing Jira data to CSMs is that **support engineers and CSMs need different things from the same data**. A support engineer needs to see the individual issue, the assignee, the linked PR, the comment thread. A CSM needs to know: is this account's support burden normal, getting worse, or a sign of something structural? These are completely different views of identical underlying data.

**The metrics that matter for CSMs** (not support engineers) fall into four categories:

1. **Volume signal:** total open tickets per account, and whether that number is trending up, flat, or resolving. A customer with 12 open tickets isn't necessarily in trouble if they've had 15 open tickets for the last six months. But a customer who went from 2 to 12 in 30 days is a red flag. Trend direction matters more than absolute count.

2. **Severity concentration:** the ratio of Critical and High priority tickets to total open tickets. An account with 10 open tickets, all Medium, is in a different position than one with 3 open tickets where 2 are Critical. Weight the health contribution of support tickets by severity, not by count. A practical formula: `support_risk = (critical_count × 3 + high_count × 2 + medium_count × 1) / total_open`. Normalize this to a 0–100 scale and apply a weight of ~25% in the overall health score.

3. **Age distribution:** buckets are more useful than averages. The relevant thresholds for DSD issues are: 0–14 days (fresh, normal), 15–30 days (watch), 31–90 days (aging, flag amber), 90+ days (stale, flag red), 365+ days (structural — this is a product gap, not a support issue). The current unmatched queue shows at least one issue at 2310 days open — that's a case study in why a single "days open" number per issue is not enough; you need aging buckets with graduated alert colors.

4. **Issue type mix:** the DSD labels (VMS, upgrade, training-gap) tell a story. An account with mostly `training-gap` issues needs a different intervention (user education, proactive training session) than one with mostly `Bug` issues at Critical priority (that's an escalation). Surfacing the issue type breakdown per account lets the CSM choose the right response without reading individual ticket titles.

**What CSMs should NOT see at the top level:** individual Jira issue titles, assignees, JQL IDs, internal Jira statuses like "Awaiting DevOps." These are operational details for support and engineering. The CSM view of a Jira issue should be a one-line summary: `DSD-4821 | Bug | Critical | 47 days open | Awaiting Dev`. That's it. The link to the actual Jira issue should be there for when they need to reference it, but it should not be the primary interface.

**The unmatched queue problem:** the current implementation has 9 unmatched issues. The right UX for this is not a raw list — it's a triage workflow. Each unmatched issue should show: issue title, issue type, priority, probable account matches (fuzzy-matched by company name fragments in the title or description), and a one-click "assign to account" action. After assignment, the issue should disappear from the unmatched queue and appear in that account's support summary. The volume of unmatched issues should be surfaced as a small notification badge on the Jira nav item for whoever does queue maintenance, not as a primary view.

**SLA breach as a health signal:** the current Triage view already uses SLA breach as a flag. This should be integrated into the Jira aggregation layer — when a DSD issue is in a status that implies Sedna-side delay (Awaiting Dev, Awaiting DevOps, In Progress) and has been open beyond a threshold, it should count as a Sedna-side SLA risk, separate from customer-side delays (Awaiting Customer). This distinction matters: an account with 3 tickets stuck at "Awaiting Dev" for 60 days is a Sedna delivery problem, not a customer behavior problem, and the CSM's response is different (escalation internally, proactive communication externally).

---

## 3. Maritime B2B Context — What's Specific to This Scenario

Dataloy VMS serves shipowners, operators, charterers, and traders — a narrow but operationally critical vertical. Maritime software buyers are characteristically conservative (long procurement cycles, large IT and legal involvement in contracts), operationally dependent (a VMS bug can affect vessel scheduling, voyage P&L calculations, cargo coordination), and geographically distributed (accounts span Northern Europe, Southeast Asia, Middle East, Americas). Dataloy reported 25% revenue growth and 15% new customer growth in 2024, which means Sedna's CS team is simultaneously managing a growing book of new onboarding accounts and an existing base of established customers — two very different support profiles that a generic CSM tool doesn't distinguish.

**The account tier structure ($400 ARR Scale to $767K Premier) has direct implications for workflow:**

- **Scale accounts** are high-volume, low-touch. Many are likely single-vessel or small-fleet operators using Dataloy for basic voyage tracking. Their support profile is predominantly training-gap issues and basic configuration. CSMs covering Scale cannot afford deep individual engagement — they need portfolio-level risk triage to catch the handful of Scale accounts that are genuinely at risk, and to ignore the rest unless triggered. The current "CSM Renewal Risk" view is the right idea for Scale, but needs to be faster to scan.

- **Premier accounts** ($767K ARR or close) are operationally complex. These are large shipping groups with multiple business units, multiple VMS modules in use, complex integrations, procurement teams, and multi-year contracts. Their support issues are rarely training-gap — they're integration bugs, upgrade blockers, data migration problems. A Premier account with a 2-week-old Critical Jira ticket is a fundamentally different situation from a Scale account with the same ticket. The tool should visually communicate this difference — Premier accounts should feel "heavier" in the UI, with more surface area and more visible escalation paths.

- **Migrations and upgrades as lifecycle events:** the Migrations Gantt view already exists, which is appropriate — VMS version migrations are the highest-risk moment in a maritime software account's lifecycle. A customer that is mid-migration has elevated support burden, elevated churn risk if it goes badly, and elevated expansion potential if it goes well. The tool should reflect this by flagging mid-migration accounts distinctly in the portfolio view (not just in the Migrations-specific view), and by correlating migration phase with support ticket volume so CSMs can spot when a migration is generating unexpected issue volume.

- **Renewal cycles in maritime B2B:** the 90-day renewal window is standard B2B SaaS advice, but for maritime enterprise accounts the realistic window is 120–180 days. Contract renewals involve procurement, legal review, sometimes port authority or flag state compliance checks. CSMs managing Premier accounts should be prompted to begin renewal conversations at 120 days, not 90. The current renewal days counter is correct in concept but the threshold colors should be calibrated to this context.

- **Upgrade and SSO as expansion signals:** the existence of Upgrades and SSO tabs in the current account panel is architecturally correct. For maritime SaaS, a customer moving to a higher VMS tier or adopting SSO/SAML is an expansion signal worth tracking against NRR targets. These should be surfaced in the Intelligence view alongside renewal data.

---

## 4. Proposed Navigation / IA Remodel — Concrete Recommendation

The current flat nav (Triage | Customers | Command | Migrations | Trends | CSM Renewal Risk | Jira Mapping) has three structural problems: it conflates triage with risk scoring (two items doing the same job from different angles), it buries calendar-based planning inside an underused "Command" item, and it exposes raw Jira data as a navigation destination rather than a signal layer beneath the existing views.

**Proposed structure — five primary nav items:**

### Today (Home)
Replaces: Triage + Command (partially)

The morning landing page. Answers: "What do I need to do today?" Content:
- My CTAs: accounts flagged HIGH RISK or ACTION REQUIRED, sorted by urgency
- Calendar strip: today's scheduled calls and QBRs (lifted from Command view)
- Jira alerts that fired in the last 24 hours: new Critical tickets assigned to my accounts, tickets that crossed 30-day / 90-day aging thresholds overnight
- Renewal countdown: accounts with renewals in the next 14 days
- Quick stats row: accounts in red health / accounts in amber / open Jira tickets across my portfolio (link to Portfolio)

The Activity tab, Upgrades tab, Migrations tab, and SSO tab that currently live inside Triage become programme dashboards accessible from Operations (see below), not sub-tabs on a triage queue.

### Portfolio (My Accounts)
Replaces: Customers + CSM Renewal Risk

A single unified account list with rich per-row metadata. The portfolio view is not a search tool — it's a risk-sorted, filterable view of the CSM's book of business. Columns: account name, tier badge (Premier/Strategic/Scale), health dot (green/amber/red), health delta (up/down arrow vs last 30 days), open Jira tickets (count, colored by severity concentration), renewal date (with urgency coloring), last touchpoint (days ago), migration status flag (if mid-migration).

Default sort: health score ascending (worst accounts at top). Filter controls: by tier, by health band, by renewal window (30/60/90/120 days), by migration status. CSM filter: each CSM sees their own portfolio by default; managers can switch to "All CSMs" view.

Clicking a row opens the Account 360 panel (side panel, as now, but redesigned — see section 5).

The "CSM Renewal Risk" view is retired as a standalone nav item. Its cards are replaced by the Portfolio rows — same data, better density, sortable.

### Account 360 (side panel — not a nav item)
Replaces: the current Customers side panel

Opens from Portfolio. Persistent header shows: account name, tier, health score (with sparkline trend), renewal date, CSM owner. Below the header, tabs:

- **Overview** — health score breakdown (product usage, support burden, engagement), open Jira summary card (aggregate, not list), last three timeline events, active case count
- **Support** — Jira issue aggregation view (not the raw issue list — see Section 5 for design)
- **Cases** — internal case queue (current tab, keep as-is)
- **Timeline & Notes** — merged (currently separate tabs, functionally identical enough to merge)
- **Operations** — Upgrades, Migrations, SSO in one tab (low-frequency, shouldn't compete with Support and Overview for tab space)

### Operations
Replaces: Migrations tab + Upgrades tab + SSO tab from Triage

A workspace for the team's operational programmes, not account-specific. Three sub-views:
- **Migrations** — existing Gantt board (keep, it works)
- **Upgrades** — pipeline of pending/in-progress VMS tier upgrades
- **SSO** — SSO provisioning queue across all accounts

This view is typically used by a subset of the team (whoever manages migrations) and doesn't need to compete with Portfolio and Today for nav prominence. It should be lower in the nav or grouped with a divider.

### Intelligence
Replaces: Trends + Jira Mapping (partially)

Passive analytical views for understanding portfolio-wide patterns. Three sub-views:
- **Health Trends** — existing charts (health distribution, open cases by CSM, dwell time) — keep
- **Support Signals** — portfolio-wide Jira analysis: ticket volume by account (heat-ranked), aging distribution across all accounts, issue type breakdown (Bug vs Training-gap vs Upgrade), SLA breach trends. This is where the "Jira Mapping" concept graduates to — not raw issue assignment, but interpreted patterns.
- **Jira Queue** — the unmatched issue assignment workflow (admin-level, moved here from a top-level nav item). Small badge showing unmatched count.

---

## 5. Jira Interpretation Layer — Turning DSD Issues into CSM Signals

The Jira Mapping view currently surfaces raw issue data. Here is the specific design for transforming that into CSM-facing signals.

**Per-account Support Summary Card (shown in Account 360 Overview tab and Portfolio rows):**

```
[ SUPPORT ]  7 open   2 Critical  |  Avg age 38d  |  Oldest: 91d
             Bug ██████ 5   Training-gap ██ 2
             ⚠ 2 tickets aging > 30d  |  1 Sedna-side delay
```

This card is generated from the matched DSD issues for that account. The "Sedna-side delay" count is issues in status "In Progress," "Awaiting Dev," or "Awaiting DevOps" that have been open > 14 days — this is what the CSM needs to escalate internally or explain proactively to the customer.

**In the Account 360 Support tab:**

Show issues as a compact list, not a full table. Each row: `[Priority badge] [Type badge] DSD-XXXXX — Title (truncated 60 chars) — N days open — [Status chip]`. Grouped by: Critical first, then High, then Medium. Within each group, sorted by days open descending. A toggle to show closed issues (collapsed by default — resolved issues are noise for a CSM).

Below the list, a small "Support Trend" sparkline: weekly ticket volume for the last 8 weeks. This instantly shows whether an account's support load is growing, stable, or resolving.

**Aging thresholds and colors (consistent across all views):**
- 0–14 days: neutral (no highlight)
- 15–30 days: amber dot
- 31–90 days: amber background
- 90–365 days: red background
- 365+ days: red background + "Stale" badge — these should be flagged for review in a dedicated report, because a ticket open for a year is either a known product limitation (should be documented as such, not tracked as an open ticket) or a forgotten issue

**Health score contribution from support (recommended formula):**

`support_score = 100 - min(100, (critical_open × 20) + (high_open × 8) + (medium_open × 3) + (tickets_over_90d × 15))`

Apply this as a 25% weight in the overall health score. This means a single unresolved Critical ticket drops the support component by 20 points, which is appropriate — a Premier account with a Critical-priority open bug for 6 weeks should not have a green health score regardless of how well everything else is going.

**The unmatched queue workflow:**

When a new DSD issue has no `jira_ref` match, the system should attempt fuzzy matching against account names using the issue title and description. Show the top 2–3 probable matches with a confidence indicator. The assignment UI should be: issue summary at top, probable matches as clickable options below (with account name, tier, current CSM shown), plus a manual search field. One click assigns and removes from queue. This workflow belongs in Intelligence > Jira Queue, not as a top-level nav destination.

---

## 6. Quick Wins — Highest-Impact Immediate Changes

These can be implemented without a full remodel and will meaningfully reduce the "hard to consume" problem today.

**1. Add a Jira summary pill to every account row in the Customers list.** A single pill showing open ticket count, colored by severity concentration (green/amber/red), does more to communicate support burden than any amount of drilling into the Jira Mapping view. Takes 2–3 hours to implement; changes how every CSM reads their portfolio.

**2. Surface the oldest open Jira ticket age on the CSM Renewal Risk cards.** The current cards show health score, security score, renewal days, SLA breaches, and active cases. Adding "Oldest open ticket: N days" (colored red if > 30 days) gives CSMs the one piece of information most likely to change their renewal conversation prep.

**3. Replace the Jira Mapping list with an aging-bucketed view.** Instead of a flat table of issues, show four columns: 0–14 days, 15–30 days, 31–90 days, 90+ days. Each column shows issue count and lists the issues. This single layout change converts the Jira view from a data dump into an actionable queue — the 90+ column is what needs human attention, and it's immediately obvious.

**4. Add health score delta (trend arrow) to all account displays.** A static health score number tells you where an account is. A delta (▲ +8 / ▼ −12 vs last 30 days) tells you which direction it's moving. Accounts trending down are more urgent than accounts that are already low but stable. This is the single most impactful metric improvement in Gainsight and Vitally and it requires only storing last month's score.

**5. Merge CSM Renewal Risk into Portfolio with a filter.** The CSM Renewal Risk view and the Customers view are showing overlapping data from different angles. Removing the duplicate nav item and adding a "Renewal at risk" filter to the Portfolio view eliminates cognitive context-switching and reduces the nav from 7 items to 6 — then ultimately 5 with the full remodel.

**6. Add a "days since last CSM touchpoint" column to the account list.** This is the data point most directly under the CSM's control and most directly correlated with churn risk. Accounts that haven't been contacted in 45+ days should be amber; 90+ days should be red. It requires logging touchpoints (currently done via Notes/Timeline) and surfacing the most recent date.

**7. Make the unmatched Jira queue a badge, not a nav item.** Add a small count badge to whatever nav item houses Jira management (Intelligence in the proposed IA, or a sub-item in the current structure). The unmatched queue should not be a top-level destination — it's a maintenance task, not a daily workflow.

**8. Add issue-type grouping to the account-level Jira view.** Instead of listing all open tickets chronologically, group them: Bugs first (operational risk), then Training-gap (CSM can act on this), then other. This lets the CSM scan in 10 seconds and know whether the account's support load is a product problem or a training problem — two completely different interventions.

**9. Add a mid-migration flag to the Portfolio row.** Accounts that are currently in a migration (tracked in the Migrations Gantt) should show a small migration-phase badge in the Portfolio list. Mid-migration accounts need more frequent touchpoints and their elevated support ticket volume is expected — the CSM needs to know not to interpret that volume as a health signal.

**10. Calibrate renewal urgency colors to 120/60/30 days instead of 90/30/14.** Maritime enterprise procurement is slower than generic SaaS. Using 120 days as the "start the conversation" threshold and surfacing that in amber (not just green) ensures CSMs begin renewal prep in time to navigate the multi-stakeholder maritime procurement process. The 30-day red threshold is too late for any meaningful intervention on a Premier account.

---

*This report synthesizes patterns from Gainsight, Vitally, Planhat, and ChurnZero platform analysis, Jira aggregation best practices, and B2B maritime software context. All recommendations are grounded in the specific Sedna Ops structure: 8 CSMs, 533 accounts, DSD project (Dataloy Service Desk), VMS + Email products, Premier/Strategic/Scale tiers.*
