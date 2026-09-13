# Sedna Ops Runbook

## Scope & Assumptions

Sedna Ops runs as a single-host Docker Compose stack — `sedna-ops-api-1`, `sedna-ops-db-1`, `sedna-ops-web-1`, `sedna-ops-nginx-1` — with no redundancy and no failover. Anyone following this has shell + Docker access to the host. Log the outcome of any real incident handled via this runbook in the app's own Platform Incidents page (`/incidents`).

## 1. Disk Full on the Docker Host

**Symptoms**: containers restarting unexpectedly, Postgres write errors in `docker compose logs db`, `docker compose up` failing to pull/build.

**Diagnose**:
```bash
df -h
docker system df
du -sh ./backups
docker volume inspect sedna-ops_postgres-data
```

**Immediate relief**:
```bash
docker system prune           # reclaim dangling images/build cache
find ./backups -name "sedna_ops_*.sql.gz" -mtime +30 -delete   # backup retention should already do this — see §4 if it hasn't
```

**Root-cause candidates specific to this stack**: `db_backup`'s 30-day retention not actually running (see §4), Postgres WAL growth from a long-running transaction, `--reload`'s dev-mode file watching accumulating temp files.

## 2. A Container Won't Start

- **`api`**: `docker compose logs api` — common causes: an Alembic migration failed on startup, a missing/misconfigured `.env` var, port `8002` already bound on the host.
- **`db`**: check the healthcheck directly — `docker compose exec db pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`. Volume permission issues are the other common cause.
- **`web` / `nginx`**: distinguish a build failure (`docker compose build` errors) from a runtime crash (`docker compose ps` shows it exited after starting) — a build failure needs a Dockerfile/dependency fix, a runtime crash needs the container's own logs.

**Recovery order**: `db` must be healthy before `api` starts (already encoded in `docker-compose.yml`'s `depends_on: condition: service_healthy`) — don't force-start `api` if `db` isn't healthy yet.

## 3. Rolling Back a Bad Alembic Migration

`alembic downgrade -1` runs the target migration's own `downgrade()` function — it only undoes what that specific migration's author wrote, nothing more.

- **Safe** when the migration only added a nullable column or a new table, and no already-committed data depends on it existing.
- **Unsafe** when the migration dropped/renamed a column, or the currently-running app code already relies on the new schema — downgrading schema under code that still expects it will start 500ing immediately.

**Correct sequence**: stop or roll back the `api` deployment *first*, then downgrade the schema — never the reverse. **Always take a fresh backup before downgrading**, regardless of what the scheduled job's last run looked like (see §4) — a downgrade that goes wrong is much easier to recover from with a backup taken minutes ago than one from last night.

Log it as a platform incident (`source=code` if the migration itself was wrong, `source=infra` if it was an environment/ordering issue).

## 4. Backup Verification

A real, working backup now runs via `app/scheduler.py`'s `db_backup` job (`CronTrigger(hour=2, minute=0)` — 02:00 UTC daily), writing `pg_dump` output straight to `./backups` on the host, gzipped, with 30-day retention. This replaced the previous `docker-entrypoint-initdb.d/backup.sh` approach, which was confirmed live to only ever execute once — at the very first container initialization — and never again on subsequent restarts; `./backups` held exactly one stale file from the stack's original startup with nothing since, for the entire life of the database up to this fix.

**Don't just trust that a job is "registered" — verify it's actually producing usable output:**

1. **Confirm real files are accumulating**, not just existing: `ls -la ./backups` should show multiple files with distinct, recent dates — not one old file.
2. **Confirm the job actually ran today**: check `docker compose logs api | grep "Database backup"` for a recent `"Database backup written"` line, or a `"Database backup failed"` line if something's wrong (check the logged `pg_dump` stderr in that case).
3. **Prove restorability, not just existence** — a backup nobody has ever restored is unverified:
   ```bash
   docker run --rm -e POSTGRES_PASSWORD=x -e POSTGRES_DB=restoretest -d --name restore-scratch postgres:16-alpine
   gunzip -c ./backups/sedna_ops_<latest-date>.sql.gz | docker exec -i restore-scratch psql -U postgres -d restoretest
   docker exec restore-scratch psql -U postgres -d restoretest -c "SELECT count(*) FROM customers;"
   docker stop restore-scratch
   ```
   Compare that row count against the real production `customers` table count — they should match (or be very close, if a poll ran between the backup and now).
4. **Re-run this checklist quarterly.** If a gap is found (job silently stopped running, backups accumulating but never restoring cleanly, retention not pruning), log it as a platform incident (`source=infra`) — this exact failure mode already happened once, silently, for the entire life of this app before this runbook existed.
