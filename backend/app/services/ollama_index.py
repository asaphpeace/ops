"""Background content-index rebuild for chat's full-text-search fallback
(services/ollama_context.py). Full rebuild every run, not an incremental
upsert — confirmed live this is the right call at the real data scale
(~22,400 total indexable rows across all 9 source tables, dominated by
case_comments' 20,871 rows / ~4.9MB), and several source columns
(Upgrade.blocked_reason, Release.notes) have no updated_at to key an
incremental cutoff off anyway. Revisit only if case_comments grows past
roughly 500K rows. Mirrors scheduler.py's own _recalculate_snapshot/
_recalculate_days_open, both already full recomputes."""
from sqlalchemy import delete, text

from app.models.ollama_search_index import OllamaSearchIndex

# One (source_type, INSERT...SELECT) pair per source table. Each SELECT
# only emits rows with real, non-empty content — never an empty string row.
_REBUILD_QUERIES: list[tuple[str, str]] = [
    (
        "case",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'case', jira_ref, customer_id,
               title || COALESCE(' ' || resolution_note, '') || COALESCE(' ' || rovo_context, ''),
               now()
        FROM cases
        """,
    ),
    (
        "case_comment",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'case_comment', cc.jira_ref || '#' || cc.jira_comment_id,
               (SELECT c.customer_id FROM cases c WHERE c.jira_ref = cc.jira_ref LIMIT 1),
               cc.text, now()
        FROM case_comments cc
        WHERE cc.text IS NOT NULL AND cc.text <> ''
        """,
    ),
    (
        "vms_bug",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'vms_bug', jira_ref, NULL,
               COALESCE(ai_summary, '') || COALESCE(' ' || rovo_context, ''), now()
        FROM vms_bugs
        WHERE COALESCE(ai_summary, '') <> '' OR COALESCE(rovo_context, '') <> ''
        """,
    ),
    (
        "upgrade",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'upgrade', id::text, customer_id, blocked_reason, now()
        FROM upgrades
        WHERE blocked_reason IS NOT NULL AND blocked_reason <> ''
        """,
    ),
    (
        "migration_project",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'migration_project', id::text, customer_id,
               COALESCE(integration_notes, '') || COALESCE(' ' || ip_notes, ''), now()
        FROM migration_projects
        WHERE COALESCE(integration_notes, '') <> '' OR COALESCE(ip_notes, '') <> ''
        """,
    ),
    (
        "release",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'release', id::text, NULL, notes, now()
        FROM releases
        WHERE notes IS NOT NULL AND notes <> ''
        """,
    ),
    (
        "incident",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'incident', id::text, NULL,
               detail || COALESCE(' ' || impact, '') || COALESCE(' ' || root_cause, '') || COALESCE(' ' || resolution, ''),
               now()
        FROM incidents
        """,
    ),
    (
        "incident_remediation",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'incident_remediation', id::text, customer_id, notes, now()
        FROM incident_remediations
        WHERE notes IS NOT NULL AND notes <> ''
        """,
    ),
    (
        "ops_note",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'ops_note', id::text, customer_id, text, now()
        FROM ops_notes
        WHERE text IS NOT NULL AND text <> ''
        """,
    ),
    (
        "campaign",
        """
        INSERT INTO ollama_search_index (source_type, source_ref, customer_id, content, updated_at)
        SELECT 'campaign', id::text, NULL, message, now()
        FROM campaigns
        WHERE message IS NOT NULL AND message <> ''
        """,
    ),
]


async def rebuild_search_index(db) -> int:
    """Full delete + reinsert, one transaction. Returns the total row count
    after rebuild."""
    await db.execute(delete(OllamaSearchIndex))
    for _source_type, query in _REBUILD_QUERIES:
        await db.execute(text(query))
    await db.commit()

    result = await db.execute(text("SELECT count(*) FROM ollama_search_index"))
    return result.scalar_one()
