"""
Slack outbound webhook (C6).

Set SLACK_WEBHOOK_URL in .env to enable.
Falls back to logging the message locally when disabled — nothing breaks.
"""
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def post(text: str) -> bool:
    """Post plain text to the team Slack channel. Returns True on success."""
    if not settings.slack_enabled:
        logger.info("[Slack disabled] %s", text[:200])
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                settings.slack_webhook_url,
                json={"text": text},
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        logger.debug("Slack post OK (%d chars)", len(text))
        return True
    except Exception as exc:
        logger.error("Slack post failed: %s", exc)
        return False
