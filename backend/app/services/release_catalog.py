"""The list of VMS releases actually published on releasenotes.dataloy.com —
the source of truth for "is this a real version we can upgrade to".

Read from the site's own machine-readable index (llms.txt), which lists
every release page as "[Release X.Y.Z](...)" — confirmed live: 466
versions, including 8.31.5/8.31.6 that the Jira-synced Releases table
doesn't have. Cached in-process for an hour; if the site is unreachable the
caller falls back to the local Releases table and says so.
"""
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

_INDEX_URL = "https://releasenotes.dataloy.com/llms.txt"
_RELEASE_LINK = re.compile(r"\[Release (\d+\.\d+\.\d+)\]")
_TTL_SECONDS = 3600
_cache: dict = {"versions": None, "fetched_at": 0.0}


def version_key(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v))


def release_url(v: str) -> str:
    return f"https://releasenotes.dataloy.com/release-{v}"


async def published_versions() -> tuple[list[str] | None, float]:
    """(versions newest-first, fetched_at) or (None, 0) if unreachable and
    nothing cached yet."""
    if _cache["versions"] is not None and time.time() - _cache["fetched_at"] < _TTL_SECONDS:
        return _cache["versions"], _cache["fetched_at"]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(_INDEX_URL)
            resp.raise_for_status()
        versions = sorted(set(_RELEASE_LINK.findall(resp.text)), key=version_key, reverse=True)
        if versions:
            _cache.update(versions=versions, fetched_at=time.time())
    except Exception as exc:
        logger.warning("releasenotes.dataloy.com index fetch failed: %s", exc)
    return _cache["versions"], _cache["fetched_at"]
