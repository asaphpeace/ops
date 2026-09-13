"""
Google Calendar — one-way push for booked upgrade slots (Command Centre).

Design, not yet live-tested: no service account credentials exist in this
environment. Internal-only attendees (confirmed) — the customer is told the
slot via Jira directly, not invited to the calendar event. One-way push only
(create/update/cancel) — no free/busy conflict-checking.

Uses a service account with the team's Upgrades calendar shared to its email
(ordinary calendar-sharing action) rather than per-user OAuth, since the app
has no persisted-user infrastructure today (identity is a stateless JWT).

Set GOOGLE_CALENDAR_SERVICE_ACCOUNT_JSON (the service account key, as a raw
JSON string) and GOOGLE_CALENDAR_ID (the shared calendar's id) to enable.
Without them, calls here log the event that *would* have been created and
return None — nothing breaks, matching the app's existing pattern for every
other optional integration (Jira/Slack/AI).
"""
import json
import logging
from datetime import datetime, timedelta

from app.config import settings
from app.models.upgrade import Upgrade

logger = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


def _build_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    info = json.loads(settings.google_calendar_service_account_json)
    creds = service_account.Credentials.from_service_account_info(info, scopes=_SCOPES)
    return build("calendar", "v3", credentials=creds)


def _event_body(upgrade: Upgrade, customer_name: str) -> dict:
    start = upgrade.scheduled_at
    end = start + timedelta(minutes=upgrade.duration_minutes)
    return {
        "summary": f"Upgrade: {customer_name} — {upgrade.from_version or '?'} → {upgrade.to_version}",
        "description": (
            f"Environment: {upgrade.environment}\n"
            f"Jira: {upgrade.jira_ref or '—'}\n"
            f"Type: {upgrade.upgrade_type}\n"
            f"Customer will be notified of this slot via Jira directly."
        ),
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
        # Internal-only — confirmed. No external/customer attendees.
        "attendees": [],
    }


async def upsert_upgrade_event(upgrade: Upgrade, customer_name: str) -> str | None:
    """Create or update the calendar event for a scheduled upgrade slot."""
    if not upgrade.scheduled_at:
        return None

    if not settings.calendar_enabled:
        logger.info(
            "Calendar disabled — would %s event for %s (%s -> %s) at %s",
            "update" if upgrade.google_event_id else "create",
            customer_name, upgrade.from_version, upgrade.to_version, upgrade.scheduled_at,
        )
        return None

    try:
        service = _build_service()
        body = _event_body(upgrade, customer_name)
        if upgrade.google_event_id:
            event = service.events().update(
                calendarId=settings.google_calendar_id, eventId=upgrade.google_event_id, body=body
            ).execute()
        else:
            event = service.events().insert(calendarId=settings.google_calendar_id, body=body).execute()
        return event["id"]
    except Exception as exc:
        logger.error("Calendar upsert failed for upgrade %s: %s", upgrade.id, exc)
        return None


async def cancel_upgrade_event(upgrade: Upgrade) -> None:
    """Remove the calendar event for a cancelled/cleared upgrade slot."""
    if not upgrade.google_event_id:
        return

    if not settings.calendar_enabled:
        logger.info("Calendar disabled — would cancel event %s", upgrade.google_event_id)
        return

    try:
        service = _build_service()
        service.events().delete(calendarId=settings.google_calendar_id, eventId=upgrade.google_event_id).execute()
    except Exception as exc:
        logger.error("Calendar cancel failed for upgrade %s: %s", upgrade.id, exc)
