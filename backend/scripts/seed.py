"""Copy every record from one Sedna Ops database to another.

Run it inside the api container (so DATABASE_URL and asyncpg are available):

  # on the source instance
  docker compose exec api python scripts/seed.py export
  #   -> backend/scripts/seed_data.json.gz   (backend/ is bind-mounted)

  # copy seed_data.json.gz to the same place on the target machine, then:
  docker compose exec api alembic upgrade head          # schema first
  docker compose exec api python scripts/seed.py import

Works on whatever tables exist, so new tables are picked up automatically.
The export is plain JSON produced by Postgres itself (json_agg) and the import
hands it back through json_populate_recordset, so types round-trip without any
per-table code.

Never exported: alembic_version (the target owns its own migration state) and
ollama_search_index (derived content; rebuild it from the Ollama page).
vms_api_credentials holds client secrets and is skipped unless you pass
--include-secrets.

The data file contains customer contacts, notes and tenant login notes. Treat
it as sensitive and do not commit it (it is gitignored).
"""
import argparse
import asyncio
import gzip
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone

import asyncpg

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DEFAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_data.json.gz")
ALWAYS_SKIP = {"alembic_version", "ollama_search_index"}
SECRET_TABLES = {"vms_api_credentials"}
CHUNK_ROWS = 2000


def _dsn(override: str | None) -> str:
    url = override or os.environ.get("DATABASE_URL")
    if not url:
        from app.config import settings
        url = settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _tables(conn) -> list[str]:
    rows = await conn.fetch(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' ORDER BY table_name"
    )
    return [r["table_name"] for r in rows]


async def _insert_order(conn, tables: list[str]) -> list[str]:
    """Parents before children, from the real foreign keys. Self-references
    are ignored; a genuine cycle falls through in name order (the import also
    relaxes FK checks when it is allowed to)."""
    rows = await conn.fetch(
        """
        SELECT c.conrelid::regclass::text AS child, c.confrelid::regclass::text AS parent
        FROM pg_constraint c
        JOIN pg_namespace n ON n.oid = c.connamespace
        WHERE c.contype = 'f' AND n.nspname = 'public'
        """
    )
    wanted = set(tables)
    deps: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        child, parent = r["child"].strip('"'), r["parent"].strip('"')
        if child != parent and child in wanted and parent in wanted:
            deps[child].add(parent)
    ordered: list[str] = []
    remaining = sorted(wanted)
    while remaining:
        ready = [t for t in remaining if not (deps[t] - set(ordered))]
        if not ready:
            ready = remaining[:1]
        ordered.extend(ready)
        remaining = [t for t in remaining if t not in ready]
    return ordered


async def export_data(args) -> None:
    conn = await asyncpg.connect(_dsn(args.dsn))
    try:
        skip = set(ALWAYS_SKIP)
        if not args.include_secrets:
            skip |= SECRET_TABLES
        tables = [t for t in await _tables(conn) if t not in skip]
        version = await conn.fetchval("SELECT version_num FROM alembic_version") if "alembic_version" in await _tables(conn) else None

        data: dict[str, list] = {}
        for t in tables:
            raw = await conn.fetchval(f"SELECT coalesce(json_agg(t), '[]'::json)::text FROM {_q(t)} t")
            data[t] = json.loads(raw)
            print(f"  {t}: {len(data[t])} rows")

        payload = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "alembic_version": version,
            "includes_secrets": bool(args.include_secrets),
            "tables": data,
        }
        with gzip.open(args.file, "wt", encoding="utf-8") as fh:
            json.dump(payload, fh)
        total = sum(len(v) for v in data.values())
        print(f"\nExported {total} rows from {len(data)} tables to {args.file}")
        print(f"Source migration: {version}")
    finally:
        await conn.close()


async def import_data(args) -> None:
    with gzip.open(args.file, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    data: dict[str, list] = payload["tables"]

    conn = await asyncpg.connect(_dsn(args.dsn))
    try:
        target_tables = set(await _tables(conn))
        if "alembic_version" not in target_tables:
            sys.exit("Target has no alembic_version table; run `alembic upgrade head` first.")
        target_version = await conn.fetchval("SELECT version_num FROM alembic_version")
        if payload.get("alembic_version") != target_version and not args.force:
            sys.exit(
                f"Migration mismatch: data is from {payload.get('alembic_version')}, target is at "
                f"{target_version}. Run `alembic upgrade head` (or pull the same code), or pass --force."
            )

        missing = [t for t in data if t not in target_tables]
        if missing:
            print(f"Skipping tables not in target schema: {', '.join(missing)}")
        tables = await _insert_order(conn, [t for t in data if t in target_tables])

        async with conn.transaction():
            try:
                async with conn.transaction():  # savepoint, so a refusal doesn't abort the import
                    await conn.execute("SET LOCAL session_replication_role = replica")
            except asyncpg.InsufficientPrivilegeError:
                print("Note: cannot relax FK checks (not superuser); relying on dependency order.")

            if args.truncate:
                await conn.execute("TRUNCATE " + ", ".join(_q(t) for t in tables) + " RESTART IDENTITY CASCADE")
                print("Truncated target tables.")

            for t in tables:
                rows = data[t]
                if not rows:
                    continue
                cols = [
                    r["column_name"] for r in await conn.fetch(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'public' AND table_name = $1 AND is_generated = 'NEVER' "
                        "ORDER BY ordinal_position", t,
                    )
                ]
                col_sql = ", ".join(_q(c) for c in cols)
                stmt = (
                    f"INSERT INTO {_q(t)} ({col_sql}) OVERRIDING SYSTEM VALUE "
                    f"SELECT {col_sql} FROM json_populate_recordset(NULL::{_q(t)}, $1::json) "
                    "ON CONFLICT DO NOTHING"
                )
                inserted = 0
                for i in range(0, len(rows), CHUNK_ROWS):
                    status = await conn.execute(stmt, json.dumps(rows[i:i + CHUNK_ROWS]))
                    inserted += int(status.split()[-1])
                print(f"  {t}: {inserted}/{len(rows)} rows")

            # Rows arrive with their original ids, so every serial must be moved past them.
            for t in tables:
                seq_cols = await conn.fetch(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND table_name = $1 AND (column_default LIKE 'nextval(%' OR is_identity = 'YES')", t,
                )
                for r in seq_cols:
                    c = r["column_name"]
                    await conn.execute(
                        f"SELECT setval(pg_get_serial_sequence($1, $2), "
                        f"COALESCE((SELECT MAX({_q(c)}) FROM {_q(t)}), 1), "
                        f"(SELECT MAX({_q(c)}) FROM {_q(t)}) IS NOT NULL)",
                        _q(t), c,
                    )
        print("\nImport complete; sequences reset.")
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="dump all tables to a gzipped JSON file")
    e.add_argument("--file", default=DEFAULT_FILE)
    e.add_argument("--dsn", help="override DATABASE_URL")
    e.add_argument("--include-secrets", action="store_true", help="also export vms_api_credentials")
    e.set_defaults(func=export_data)

    i = sub.add_parser("import", help="load a file produced by `export` into this database")
    i.add_argument("--file", default=DEFAULT_FILE)
    i.add_argument("--dsn", help="override DATABASE_URL")
    i.add_argument("--truncate", action="store_true", help="empty the target tables first (CASCADE)")
    i.add_argument("--force", action="store_true", help="import even if migration versions differ")
    i.set_defaults(func=import_data)

    args = p.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
