"""
Parses real AWS log exports (CloudWatch Logs events + CloudTrail lookup
events) into LogEntry rows. No live AWS credential is ever used here —
same manual export/paste model as services/aws_import.py.

Application, RDS, and VPC Flow logs are all delivered through CloudWatch
Logs (`aws logs filter-log-events`) — one real event shape regardless of
what's actually writing to that log group. CloudTrail is structurally
different (`aws cloudtrail lookup-events`) and gets its own parser.
"""
import json
import re
from datetime import datetime, timezone

_LEVEL_PATTERN = re.compile(r"\b(ERROR|WARN|WARNING|INFO|DEBUG|FATAL|CRITICAL)\b")

# Standard VPC Flow Log version 2 field order — used only to synthesize a
# more readable `message`; the full original line always stays in raw_json
# regardless of whether this parses cleanly.
_VPC_FLOW_FIELDS = [
    "version", "account_id", "interface_id", "srcaddr", "dstaddr",
    "srcport", "dstport", "protocol", "packets", "bytes",
    "start", "end", "action", "log_status",
]


def _epoch_to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        ms = float(value)
        # CloudWatch Logs timestamps are epoch milliseconds; CloudTrail's
        # EventTime (when present as a number) is epoch seconds — the
        # magnitude tells them apart (ms values are ~13 digits, s ~10).
        if ms > 10_000_000_000:
            ms = ms / 1000
        return datetime.fromtimestamp(ms, tz=timezone.utc)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None


def parse_cloudwatch_log_events(raw: dict | list, log_type: str) -> list[dict]:
    """Handles `aws logs filter-log-events`'s real shape
    ({"events": [{"eventId","timestamp","message","logStreamName"}]}) or
    an already-flattened list. Used for log_type in
    {"application", "rds", "vpc_flow"} — same event shape, different
    semantic label supplied by the caller (the log group's real content
    differs, the CloudWatch envelope doesn't)."""
    if isinstance(raw, dict) and "events" in raw:
        events = raw.get("events", [])
    elif isinstance(raw, list):
        events = raw
    else:
        events = []

    out = []
    for e in events:
        message = e.get("message", "")
        level = None
        if log_type == "application":
            m = _LEVEL_PATTERN.search(message)
            level = m.group(1) if m else None

        if log_type == "vpc_flow":
            parts = message.split()
            if len(parts) == len(_VPC_FLOW_FIELDS):
                fields = dict(zip(_VPC_FLOW_FIELDS, parts))
                message = (
                    f"{fields['action']} {fields['srcaddr']}:{fields['srcport']} "
                    f"-> {fields['dstaddr']}:{fields['dstport']} proto={fields['protocol']}"
                )

        event_id = e.get("eventId") or f"{e.get('logStreamName', '')}:{e.get('timestamp', '')}"
        out.append({
            "event_id": event_id,
            "timestamp": _epoch_to_dt(e.get("timestamp")),
            "message": message,
            "level": level,
            "raw": e,
        })
    return [r for r in out if r["timestamp"] and r["event_id"]]


def parse_cloudtrail_events(raw: dict | list) -> list[dict]:
    """Handles `aws cloudtrail lookup-events`'s real shape
    ({"Events": [{"EventId","EventName","EventTime","Username",
    "CloudTrailEvent": "<json string>"}]}) or an already-flattened list.
    CloudTrail events are structured audit records, not freeform text —
    message is synthesized into one searchable line; the full parsed
    detail always lives in raw_json."""
    if isinstance(raw, dict) and "Events" in raw:
        events = raw.get("Events", [])
    elif isinstance(raw, list):
        events = raw
    else:
        events = []

    out = []
    for e in events:
        detail = e.get("CloudTrailEvent")
        parsed_detail = None
        if isinstance(detail, str):
            try:
                parsed_detail = json.loads(detail)
            except json.JSONDecodeError:
                parsed_detail = None
        elif isinstance(detail, dict):
            parsed_detail = detail

        source_ip = (parsed_detail or {}).get("sourceIPAddress") or "unknown IP"
        event_name = e.get("EventName") or (parsed_detail or {}).get("eventName") or "UnknownEvent"
        username = e.get("Username") or "unknown user"

        out.append({
            "event_id": e.get("EventId"),
            "timestamp": _epoch_to_dt(e.get("EventTime")),
            "message": f"{event_name} by {username} from {source_ip}",
            "level": None,
            "raw": parsed_detail or e,
        })
    return [r for r in out if r["timestamp"] and r["event_id"]]
