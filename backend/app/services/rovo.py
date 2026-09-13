"""Rovo MCP Server client — consumes Atlassian's Teamwork Graph to enrich AI
summaries with linked PRs, Confluence pages, and deployments a Jira issue
connects to, beyond what our own Jira polling captures.

Deliberately the *consuming* half only — this does not build a Teamwork
Graph connector (contributing Sedna Ops' own data outward), which is a
separate, bigger piece of work. Auth is API-token (Basic email:api_token),
which Atlassian's own docs call out as the intended path for backend
services/bots — no interactive OAuth consent flow needed for this.

Endpoint is the current post-30-Jun-2026 one (the old /v1/sse path is no
longer supported). Pinned to mcp==1.10.1 in requirements.txt specifically
because newer mcp releases (1.15.0+) require pydantic>=2.11.0, which
conflicts with this app's pinned pydantic==2.9.2 — 1.10.1 is the newest
release still compatible (Requires-Dist: pydantic<3.0.0,>=2.7.2, confirmed
by inspecting the wheel's own METADATA, not assumed). Its client API
differs in real ways from the latest release (function is
`streamablehttp_client` with no underscore before "http", takes `headers=`
directly rather than a pre-built httpx.AsyncClient, yields a 3-tuple
including a session-id callback, and `CallToolResult.structuredContent` is
camelCase) — verified against this exact pinned version's real source, not
the latest docs.

Degrades gracefully like every other optional integration in this app
(ai_enabled, calendar_enabled, dataloy_vms_enabled): missing credentials or
any call failure returns None, never raises past this module — a Rovo
hiccup must never break a summary that would otherwise work.
"""
import base64
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class RovoNotConfiguredError(Exception):
    pass


async def _call_tool(name: str, arguments: dict) -> dict | list | str | None:
    """Open a fresh MCP session, call one tool, close. Reconnecting per-call
    (rather than holding a long-lived session across requests) matches how
    this is actually used — an occasional, on-demand enrichment lookup, not
    a hot path — and avoids managing session lifetime across FastAPI request
    boundaries. Static API-token credentials need no refresh/caching layer,
    unlike the OAuth dance in services/dataloy_vms.py."""
    if not settings.rovo_enabled:
        raise RovoNotConfiguredError("rovo_api_email/rovo_api_token not configured")

    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = {"Authorization": _basic_auth_value()}
    async with streamablehttp_client(settings.rovo_mcp_url, headers=headers) as (read_stream, write_stream, _get_session_id):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            if result.structuredContent is not None:
                return result.structuredContent
            texts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
            return "\n".join(texts) if texts else None


def _basic_auth_value() -> str:
    raw = f"{settings.rovo_api_email}:{settings.rovo_api_token}".encode()
    return "Basic " + base64.b64encode(raw).decode()


async def get_teamwork_context(jira_ref: str) -> str | None:
    """Real, linked context for one Jira issue — PRs, Confluence pages,
    deployments, related work items the graph knows about that our own Jira
    polling doesn't capture. Returns None on any failure (not configured,
    timeout, auth error, or an identifier-format mismatch this integration
    hasn't been live-verified against yet) — enrichment only, never a hard
    dependency for the caller.

    NOTE: the exact identifier format getTeamworkGraphContext expects for a
    Jira issue (bare key like "DSD-12345", a full ARI, or a URL) is not
    confirmed from docs alone — this is verified against the real API the
    first time a real rovo_api_token exists, not assumed here.
    """
    try:
        context = await _call_tool("getTeamworkGraphContext", {"object": jira_ref})
        if not context:
            return None
        # Follow the two-tool pairing the Rovo docs describe: context maps
        # connections, getTeamworkGraphObject reads the actual content of
        # what's connected — only chase what the context call surfaced.
        connections = context.get("connections", []) if isinstance(context, dict) else []
        if not connections:
            return None
        details = []
        for conn in connections[:5]:
            obj_id = conn.get("id") if isinstance(conn, dict) else None
            if not obj_id:
                continue
            obj = await _call_tool("getTeamworkGraphObject", {"id": obj_id})
            if obj:
                details.append(str(obj))
        return "\n".join(details) if details else None
    except RovoNotConfiguredError:
        return None
    except Exception as exc:
        logger.warning("Rovo Teamwork Graph lookup failed for %s: %s", jira_ref, exc)
        return None
