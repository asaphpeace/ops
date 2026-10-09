"""
APScheduler setup.

IMPORTANT: runs in-process with FastAPI — uvicorn MUST use --workers 1.
Adding workers causes every job to fire N times (see docker-compose.yml).

Jobs:
  heartbeat          every 5 min   health check
  jira_poll          every 5 min   sync cases from Jira (needs JIRA_* env vars)
  upgrade_completion_sync
                     every 1 hour  full-history reconciliation of the Upgrade pipeline
                                   against Jira (was on-demand-only via "Sync from Jira" —
                                   nobody has to remember to click it now)
  team_stats_prewarm every 5 min   refresh My Desk's live team-stats cache in the background
  days_open_recalc   00:05 UTC     keep days_open current from created_at
  snapshot_recalc    00:10 UTC     write today's open/created/closed counts (global + per-customer)
  alert_engine       every 15 min  SLA / stale / renewal / blocked → Slack
  morning_brief      08:45 LON     Haiku brief → Slack (needs SLACK_* + ANTHROPIC_*)
  db_backup          02:00 UTC     pg_dump -> gzip -> /backups, 30-day retention
  customer_engagement_refresh
                     Sun 03:30 UTC refresh last_case_activity_at from live Jira
                                   (Quiet/Dormant badges on Customer Intelligence)
  upgrade_request_type_drift_check
                     02:30 UTC     live-recheck active sys-admin-classified Upgrade rows against
                                   Jira's current request_type; detection only, writes AuditLog
  cert_scan          03:00 UTC     TLS handshake against every real CustomerTenantInfo
                                   subdomain, records expiry/issuer per row
  ollama_supervisor  every 2 hours advisory-only local-LLM narration over already-computed
                                   deterministic signals (needs OLLAMA_BASE_URL) — never mutates
                                   Case/Upgrade/Customer/Incident data, only writes AiObservation rows
  ollama_index_refresh
                     every 30 min  rebuild ollama_search_index (chat's full-text-search fallback)
                                   from cases/case_comments/vms_bugs/upgrades/migration_projects/
                                   releases/incidents/incident_remediations/ops_notes/campaigns —
                                   full rebuild every run, gated on OLLAMA_BASE_URL alongside the
                                   supervisor since it exists only to serve chat
  knowledge_extraction
                     every 2 hours mines not-yet-processed OpsNote (pasted Slack context) for
                                   categorized institutional knowledge (Trend/System/Process/
                                   Procedure/Challenge/Relationship) — steady-state cheap (only
                                   new notes each run), gated on OLLAMA_BASE_URL

  db_backup replaces the old docker-entrypoint-initdb.d/backup.sh approach —
  confirmed live that mechanism only ever runs once, at first-ever container
  init on an empty data directory, never again on restarts (Postgres's own
  documented behavior). Empirically confirmed broken: ./backups held exactly
  one file, from the stack's original first startup, nothing since. This job
  runs the same pg_dump/gzip/retention logic for real, in-process, like every
  other scheduled job here.
"""
import asyncio
import gzip
import logging
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.audit_log import AuditLog
from app.models.case import Case
from app.models.case_snapshot import DailyCaseSnapshot

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _heartbeat():
    logger.debug("Scheduler heartbeat")


async def _jira_poll():
    from app.services.jira import poll_and_upsert
    result = await poll_and_upsert()
    if result["updated"] or result["errors"]:
        logger.info("Jira poll: %s", result)


async def _upgrade_completion_sync():
    # sync_completed_upgrades()'s own docstring calls it "on-demand only... a
    # much heavier full-history JQL scan than the regular 5-minute poll" —
    # that's why it was never auto-scheduled before. Hourly is deliberately
    # much less frequent than jira_poll (5 min) so this stays a real, plain
    # scheduled worker (no LLM/agent involved — Jira's own resolutiondate/
    # status fields are all that's needed) rather than something requiring
    # someone to remember to click "Sync from Jira."
    from app.services.jira import sync_completed_upgrades
    result = await sync_completed_upgrades()
    if result["created"] or result["updated"] or result["errors"]:
        logger.info("Upgrade completion sync: %s", result)


async def _team_stats_prewarm():
    """Refresh My Desk's live team-stats cache in the background so a real
    page load never pays for a cold fetch.

    team_open_stats' full pagination (6 pages for ~566 open tickets, each
    page also pulling comment threads) measured at 4-5s/page — a cold fetch
    can take ~30s, past the frontend's own request timeout. Running this on
    the same 5-min cadence as `_jira_poll` keeps the cache (TTL matches, via
    settings.jira_stats_cache_ttl_seconds) essentially always warm, so the
    only live Jira traffic for these numbers happens here, on a fixed,
    predictable schedule — not once per person per page load.

    Only pre-warms the combos an actual default page load uses (day/week/
    month resolved windows + the one open-stats query); an explicit month
    picker selection still costs one live fetch on demand, same as today.

    Also prewarms daily_ops_stats (Assigned/Resolved/Replies/Comments) for
    the day-counts My Desk's toggle (14/30/90) and Command Center's Week/
    Month/Quarter windows actually use. Added after confirming live that a
    cold month-window daily_ops_stats call (the comment-truncation fix
    makes team_daily_replies_comments do a real per-ticket fetch for every
    truncated ticket touched in the window) can exceed the frontend's 30s
    request timeout — the same class of problem team_open_stats already
    solved for above, same fix. "Year" (365d) is deliberately NOT prewarmed
    here — it's a rare selection and would make every prewarm cycle
    materially slower; it still works, just costs one real cold fetch the
    first time someone picks it.
    """
    from app.services.daily_ops import daily_ops_stats
    from app.services.jira import team_open_stats, team_resolved_stats
    from app.services.lanes import SUPPORT_TEAM as _TEAM
    from app.services.time_windows import window_start

    if not settings.jira_enabled:
        return
    try:
        async with AsyncSessionLocal() as db:
            await team_open_stats(db, list(_TEAM))
            for days in (1, 7, 30):
                await team_resolved_stats(db, list(_TEAM), days=days)
    except Exception as exc:
        logger.error("Team-stats prewarm failed (My Desk falls back to a live fetch or local data): %s", exc)

    today = datetime.utcnow().date()
    window_days = {14, 30, 90}  # My Desk's own toggle
    for window in ("week", "month", "quarter"):  # Command Center's page-level windows (year excluded, see above)
        window_days.add(max(1, (today - window_start(window).date()).days))
    try:
        async with AsyncSessionLocal() as db:
            for days in sorted(window_days):
                await daily_ops_stats(db, list(_TEAM), days)
    except Exception as exc:
        logger.error("Daily-ops prewarm failed (falls back to a live, possibly slow, fetch): %s", exc)


async def _recalculate_days_open():
    """Recompute days_open from created_at for all open cases."""
    today = date.today()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Case).where(Case.status != "Closed"))
        cases = result.scalars().all()
        changed = 0
        for case in cases:
            correct = max(0, (today - case.created_at.date()).days)
            if case.days_open != correct:
                case.days_open = correct
                changed += 1
        await db.commit()
    logger.info("days_open recalc: %d/%d cases updated", changed, len(cases))


async def _engineering_snapshot_recalc():
    """Write today's Engineering Overview KPI snapshot (Estate / On Current
    Release / Customer Exposure / Legacy Footprint) — one row per day, so
    the Overview's delta arrows ('+4 vs 30 days ago') have real history to
    diff against instead of always reading '—'. Reuses the exact same
    compute_estate_kpis() the live /engineering/overview endpoint calls,
    so the two can never silently disagree."""
    from app.models.engineering_snapshot import EngineeringDailySnapshot
    from app.routers.engineering import compute_estate_kpis

    today = date.today()
    async with AsyncSessionLocal() as db:
        kpis = await compute_estate_kpis(db)
        existing = (
            await db.execute(select(EngineeringDailySnapshot).where(EngineeringDailySnapshot.snapshot_date == today))
        ).scalar_one_or_none()
        if existing:
            existing.estate_count = kpis["estate_count"]
            existing.on_current_release_count = kpis["on_current_release_count"]
            existing.customer_exposure_count = kpis["customer_exposure_count"]
            existing.legacy_footprint_count = kpis["legacy_footprint_count"]
        else:
            db.add(EngineeringDailySnapshot(
                snapshot_date=today,
                estate_count=kpis["estate_count"],
                on_current_release_count=kpis["on_current_release_count"],
                customer_exposure_count=kpis["customer_exposure_count"],
                legacy_footprint_count=kpis["legacy_footprint_count"],
            ))
        await db.commit()
    logger.info("engineering snapshot recalc: %s", kpis)


async def _recalculate_snapshot():
    """Write today's open/created/closed counts — one global row, one per customer.

    The global row's `open_count` comes from live Jira (real total open DSD
    tickets), not the local `cases` table: that table only covers tickets a
    human has manually mapped to a customer, which undercounts real open
    workload by ~10x (confirmed live: 566 real open tickets vs 59 local —
    see team_open_stats' docstring).

    Per-customer OPEN counts are now also real (real_open_counts_by_customer,
    added alongside the Volume by Account / Customer Cases-tab fixes) —
    confirmed live a real customer showed 13 open locally vs. 95 real.
    created_count/closed_count stay local-table-derived for now (a
    real per-customer daily attribution for those would need the same
    per-day live-Jira approach team_daily_created/team_daily_resolved use,
    scoped to ALL customers rather than just SUPPORT_TEAM — a bigger,
    separate lift not covered by this pass).
    """
    from app.config import settings
    from app.services.jira import real_open_counts_by_customer, team_open_stats
    from app.services.lanes import SUPPORT_TEAM as _TEAM

    today = date.today()
    day_start = datetime(today.year, today.month, today.day)
    day_end = day_start + timedelta(days=1)

    async with AsyncSessionLocal() as db:
        all_open_result = await db.execute(select(Case).where(Case.status != "Closed"))
        all_open = all_open_result.scalars().all()

        global_open_count = len(all_open)
        real_open_by_customer: dict[int, int] = {}
        try:
            if not settings.jira_enabled:
                raise RuntimeError("Jira disabled")
            global_open_count = (await team_open_stats(db, list(_TEAM)))["total_open"]
            real_open_by_customer = {
                cid: v["open_count"] for cid, v in (await real_open_counts_by_customer(db)).items()
            }
        except Exception as exc:
            logger.error("Live Jira open-stats fetch failed for snapshot, using local (undercounted) counts: %s", exc)

        created_result = await db.execute(
            select(Case).where(Case.created_at >= day_start, Case.created_at < day_end)
        )
        created_today = created_result.scalars().all()

        closed_result = await db.execute(
            select(Case).where(
                Case.status == "Closed", Case.updated_at >= day_start, Case.updated_at < day_end
            )
        )
        closed_today = closed_result.scalars().all()

        async def _upsert(customer_id: int | None, open_count: int, created_count: int, closed_count: int):
            existing = await db.execute(
                select(DailyCaseSnapshot).where(
                    DailyCaseSnapshot.snapshot_date == today,
                    DailyCaseSnapshot.customer_id == customer_id,
                )
            )
            row = existing.scalar_one_or_none()
            if row is None:
                row = DailyCaseSnapshot(snapshot_date=today, customer_id=customer_id)
                db.add(row)
            row.open_count = open_count
            row.created_count = created_count
            row.closed_count = closed_count

        await _upsert(None, global_open_count, len(created_today), len(closed_today))

        by_customer: dict[int, dict] = {}
        # Real open counts (falls back to the local, undercounted grouping
        # only if the live fetch above failed entirely — real_open_by_customer
        # would be empty in that case).
        if real_open_by_customer:
            for cid, n in real_open_by_customer.items():
                by_customer.setdefault(cid, {"open": 0, "created": 0, "closed": 0})["open"] = n
        else:
            for c in all_open:
                by_customer.setdefault(c.customer_id, {"open": 0, "created": 0, "closed": 0})["open"] += 1
        for c in created_today:
            by_customer.setdefault(c.customer_id, {"open": 0, "created": 0, "closed": 0})["created"] += 1
        for c in closed_today:
            by_customer.setdefault(c.customer_id, {"open": 0, "created": 0, "closed": 0})["closed"] += 1

        for customer_id, counts in by_customer.items():
            await _upsert(customer_id, counts["open"], counts["created"], counts["closed"])

        await db.commit()
    logger.info("Snapshot recalc: %d customer rows + 1 global row", len(by_customer))


async def _alert_engine():
    from app.services.alerts import run as run_alerts
    await run_alerts()


async def _morning_brief():
    from app.services.digest import morning_brief
    await morning_brief()


async def _backup_database():
    """Real pg_dump -> gzip -> /backups, with 30-day retention. Runs from
    the api container (not db), so connects over the network rather than a
    local unix socket — parses host/port/user/password/dbname straight out
    of settings.database_url, no new settings needed."""
    parsed = urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    backup_dir = "/backups"
    os.makedirs(backup_dir, exist_ok=True)
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    dump_path = f"{backup_dir}/sedna_ops_{date_str}.sql"
    gz_path = f"{dump_path}.gz"

    env = os.environ.copy()
    env["PGPASSWORD"] = parsed.password or ""
    proc = await asyncio.create_subprocess_exec(
        "pg_dump", "-h", parsed.hostname, "-p", str(parsed.port or 5432),
        "-U", parsed.username, parsed.path.lstrip("/"), "-f", dump_path,
        env=env, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error("Database backup failed (pg_dump exit %d): %s", proc.returncode, stderr.decode(errors="replace"))
        return

    with open(dump_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(dump_path)
    logger.info("Database backup written: %s", gz_path)

    cutoff = datetime.utcnow().timestamp() - 30 * 86400
    for fname in os.listdir(backup_dir):
        fpath = os.path.join(backup_dir, fname)
        if fname.startswith("sedna_ops_") and fname.endswith(".sql.gz") and os.path.getmtime(fpath) < cutoff:
            os.remove(fpath)


async def _customer_engagement_refresh():
    """Weekly: refresh Customer.last_case_activity_at from live Jira, backing
    the Quiet (6mo) / Dormant (12mo) engagement badges on Customer
    Intelligence. Only ever moves the stored date forward — a customer with
    no real activity in the scan window simply keeps its existing (possibly
    still-NULL) value, which correctly continues aging rather than being
    reset."""
    from app.models.customer import Customer
    from app.services.jira import customer_last_case_dates

    since = date.today() - timedelta(days=395)
    async with AsyncSessionLocal() as db:
        dates = await customer_last_case_dates(db, since)
        updated = 0
        for customer_id, last_date in dates.items():
            customer = await db.get(Customer, customer_id)
            if customer and (customer.last_case_activity_at is None or last_date > customer.last_case_activity_at):
                customer.last_case_activity_at = last_date
                updated += 1
        await db.commit()
    logger.info("Customer engagement refresh: %d customer(s) updated", updated)


async def _generate_weekly_report():
    """Auto-generate the coming week's Draft weekly ops report early Monday
    morning, so it's ready before the real DevOps priority meeting without
    requiring a manual click. Idempotent (build_weekly_report()'s caller
    already checks for an existing row for the week) — safe if this job
    ever double-fires or someone already generated it manually."""
    from app.models.weekly_report import WeeklyReport
    from app.services.weekly_report import build_weekly_report, current_iso_week, iso_week_bounds
    from sqlalchemy import select

    week = current_iso_week()
    async with AsyncSessionLocal() as db:
        existing = (await db.execute(select(WeeklyReport).where(WeeklyReport.week == week))).scalar_one_or_none()
        if existing:
            logger.info("Weekly report %s already exists — skipping auto-generate", week)
            return
        period_start, period_end = iso_week_bounds(week)
        snapshot = await build_weekly_report(db, week)
        db.add(WeeklyReport(week=week, period_start=period_start, period_end=period_end, status="Draft", snapshot=snapshot))
        await db.commit()
    logger.info("Weekly report %s auto-generated", week)


async def _cert_scan():
    """Daily TLS-certificate sweep over every real CustomerTenantInfo
    subdomain — see services/cert_scan.py for the full reasoning (a bare
    handshake on :443, not a full app request, so unlike tenant_info.py's
    on-demand-only /info probe this one runs on a schedule). Ungated (no
    settings.X_enabled check) — this isn't an optional third-party
    integration, it scans hosts already on file. Per-host failures are
    already swallowed inside scan_all_certificates() itself; this try/except
    only guards against a DB-level fault, matching this file's own
    one-job-failure-never-crashes-the-scheduler convention."""
    from app.services.cert_scan import scan_all_certificates

    try:
        async with AsyncSessionLocal() as db:
            result = await scan_all_certificates(db)
        logger.info("Cert scan: %s", result)
    except Exception:
        logger.exception("Cert scan failed")


async def _release_version_sync():
    """Daily — the Releases section's Jira version sync, which used to run
    only when someone clicked it (confirmed 2026-10-08: it had stopped at
    8.31.4 while Jira already had 8.31.5–8.31.8 released). Read-only against
    Jira; upserts local Release rows. Gated on Jira like every other
    optional integration."""
    from app.services.jira import sync_release_versions_from_jira

    if not settings.jira_enabled:
        return
    try:
        logger.info("Release version sync: %s", await sync_release_versions_from_jira())
    except Exception:
        logger.exception("Release version sync failed")


async def _upgrade_request_type_drift_check():
    """Daily — real live re-check of every active, sys-admin-classified
    Upgrade row against its linked ticket's current Jira request_type (see
    services/jira.py::check_upgrade_request_type_drift() for the real
    incidents this exists for, e.g. DSD-30760). Detection only, never
    mutates the Upgrade row itself — writes one AuditLog row per newly
    (or still-)drifted ref, deduped against the last ~20h so an unresolved
    drift doesn't spam a fresh log entry every single day. This is the
    persisted trail routers/upgrades.py::request_type_drift_recent() and
    desk_briefing()'s flag both read — cheap, DB-only, no live Jira call —
    so the Operations > Upgrades panel and My Desk can show yesterday's
    finding without re-hitting Jira on every page load; the panel's own
    "Check for drift" button still does a fresh, on-demand live check."""
    from app.services.jira import check_upgrade_request_type_drift

    drifted = await check_upgrade_request_type_drift()
    if not drifted:
        logger.info("Upgrade request_type drift check: 0 row(s) drifted")
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=20)
    logged = 0
    async with AsyncSessionLocal() as db:
        for d in drifted:
            existing = await db.execute(
                select(AuditLog).where(
                    AuditLog.action == "upgrade.request_type_drift_detected",
                    AuditLog.target_id == d["jira_ref"],
                    AuditLog.created_at >= cutoff,
                )
            )
            if existing.scalar_one_or_none():
                continue  # already flagged within the last ~day, don't spam
            db.add(AuditLog(
                actor="system", action="upgrade.request_type_drift_detected", target_type="upgrade",
                target_id=d["jira_ref"],
                # Pipe-delimited, deliberately parseable — recent_request_type_drift()
                # (upgrade_supervision.py) parses this back into the same
                # {title, stored_request_type, live_request_type} shape
                # check_upgrade_request_type_drift() returns live, so the
                # frontend renders both identically.
                detail=f"title={d['title']} | stored={d['stored_request_type']} | live={d['live_request_type']}",
            ))
            logged += 1
        await db.commit()
    logger.info("Upgrade request_type drift check: %d row(s) drifted, %d newly logged", len(drifted), logged)


async def _ollama_supervisor():
    """Advisory-only — computes deterministic candidate signals, hands
    them to the local Ollama model for narration, stores the result as
    AiObservation rows. Never touches Case/Upgrade/Customer/Incident data."""
    from app.services.ollama_supervisor import run_supervisor_pass
    async with AsyncSessionLocal() as db:
        created = await run_supervisor_pass(db)
    logger.info("Ollama supervisor pass: %d new observation(s)", created)


async def _knowledge_extraction():
    """Mines any not-yet-processed OpsNote (pasted Slack context) for
    categorized institutional knowledge — services/knowledge_extraction.py.
    Steady-state cheap (only new notes each run, tracked via
    OpsNote.knowledge_extracted_at); the first pass over existing notes is
    a real, one-time slow cost, since each note is chunked and each chunk
    is its own sequential Ollama call."""
    from app.services.knowledge_extraction import run_knowledge_extraction
    async with AsyncSessionLocal() as db:
        created = await run_knowledge_extraction(db)
    logger.info("Knowledge extraction pass: %d new extract(s)", created)


async def _ollama_index_refresh():
    """Rebuilds ollama_search_index — the full-text-search fallback for
    chat retrieval (services/ollama_context.py) when a message names no
    real entity ref/customer. Feeds live chat, so refreshed more often than
    the 2h supervisor pass; comment-history search doesn't need jira_poll's
    5min freshness either, so 30 minutes."""
    from app.services.ollama_index import rebuild_search_index
    async with AsyncSessionLocal() as db:
        total = await rebuild_search_index(db)
    logger.info("Ollama search index rebuilt: %d row(s)", total)


def init_scheduler():
    scheduler.add_job(
        _heartbeat,
        trigger=IntervalTrigger(minutes=5),
        id="heartbeat",
        replace_existing=True,
    )

    scheduler.add_job(
        _jira_poll,
        trigger=IntervalTrigger(minutes=5),
        id="jira_poll",
        replace_existing=True,
    )

    scheduler.add_job(
        _upgrade_completion_sync,
        trigger=IntervalTrigger(hours=1),
        id="upgrade_completion_sync",
        replace_existing=True,
    )

    scheduler.add_job(
        _team_stats_prewarm,
        trigger=IntervalTrigger(minutes=5),
        id="team_stats_prewarm",
        replace_existing=True,
    )

    scheduler.add_job(
        _recalculate_days_open,
        trigger=CronTrigger(hour=0, minute=5),
        id="days_open_recalc",
        replace_existing=True,
    )

    scheduler.add_job(
        _recalculate_snapshot,
        trigger=CronTrigger(hour=0, minute=10),
        id="snapshot_recalc",
        replace_existing=True,
    )

    scheduler.add_job(
        _engineering_snapshot_recalc,
        trigger=CronTrigger(hour=0, minute=15),
        id="engineering_snapshot_recalc",
        replace_existing=True,
    )

    scheduler.add_job(
        _backup_database,
        trigger=CronTrigger(hour=2, minute=0),
        id="db_backup",
        replace_existing=True,
    )

    scheduler.add_job(
        _alert_engine,
        trigger=IntervalTrigger(minutes=15),
        id="alert_engine",
        replace_existing=True,
    )

    scheduler.add_job(
        _customer_engagement_refresh,
        trigger=CronTrigger(day_of_week="sun", hour=3, minute=30),
        id="customer_engagement_refresh",
        replace_existing=True,
    )

    scheduler.add_job(
        _upgrade_request_type_drift_check,
        trigger=CronTrigger(hour=2, minute=30),
        id="upgrade_request_type_drift_check",
        replace_existing=True,
    )

    scheduler.add_job(
        _release_version_sync,
        trigger=CronTrigger(hour=2, minute=45),
        id="release_version_sync",
        replace_existing=True,
    )

    scheduler.add_job(
        _cert_scan,
        trigger=CronTrigger(hour=3, minute=0),
        id="cert_scan",
        replace_existing=True,
    )

    scheduler.add_job(
        _generate_weekly_report,
        trigger=CronTrigger(day_of_week="mon", hour=6, minute=0),
        id="generate_weekly_report",
        replace_existing=True,
    )

    if settings.slack_enabled:
        scheduler.add_job(
            _morning_brief,
            trigger=CronTrigger(hour=8, minute=45, timezone="Europe/London"),
            id="morning_brief",
            replace_existing=True,
        )
        logger.info("Morning brief scheduled — 08:45 Europe/London → #support-vms")
    else:
        logger.info("SLACK_WEBHOOK_URL not set — morning brief disabled")

    if settings.ollama_enabled:
        scheduler.add_job(
            _ollama_supervisor,
            trigger=IntervalTrigger(hours=2),
            id="ollama_supervisor",
            replace_existing=True,
        )
        logger.info("Ollama supervisor scheduled — every 2h against %s", settings.ollama_base_url)

        scheduler.add_job(
            _ollama_index_refresh,
            trigger=IntervalTrigger(minutes=30),
            id="ollama_index_refresh",
            replace_existing=True,
        )
        logger.info("Ollama search index refresh scheduled — every 30min")

        scheduler.add_job(
            _knowledge_extraction,
            trigger=IntervalTrigger(hours=2),
            id="knowledge_extraction",
            replace_existing=True,
        )
        logger.info("Knowledge extraction scheduled — every 2h")
    else:
        logger.info("OLLAMA_BASE_URL not set — Ollama supervisor, chat, and knowledge extraction disabled")

    scheduler.start()
    logger.info(
        "APScheduler started (%d jobs) — Jira=%s Slack=%s AI=%s Ollama=%s",
        len(scheduler.get_jobs()),
        settings.jira_enabled,
        settings.slack_enabled,
        settings.ai_enabled,
        settings.ollama_enabled,
    )
