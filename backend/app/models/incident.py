from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Incident(Base):
    """A real incident affecting the Sedna Ops app/platform itself — not a
    customer support case. Manually logged, no active detection — a journal,
    not a monitoring system."""

    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))

    # Plain string vocabulary, same convention as Case.case_type/Upgrade.stage
    # — no DB enum/CHECK constraint. One of: code / infra / ai-tooling / product
    source: Mapped[str] = mapped_column(String(20))

    # Set when source="product" and the root cause is a known real VMS bug —
    # points at VmsBug.jira_ref. Drives the per-customer remediation gate
    # (see IncidentRemediation) — never set for platform-only incidents.
    linked_vms_ref: Mapped[str | None] = mapped_column(String(30))

    # A directly-known fix threshold ("any customer below this version is
    # affected"), independent of linked_vms_ref/VmsBug.fix_version — set
    # this when a human already knows the real cutoff (confirmed live: not
    # every real fix maps cleanly to one tracked VmsBug's fix_version).
    # Drives both the manual "suggest customers" flow and the automatic
    # match-on-sync below.
    affected_below_version: Mapped[str | None] = mapped_column(String(30))

    detail: Mapped[str] = mapped_column(Text)  # what happened
    impact: Mapped[str | None] = mapped_column(Text)  # real user/data impact — may be unknown at log time
    root_cause: Mapped[str | None] = mapped_column(Text)  # filled in on resolution
    resolution: Mapped[str | None] = mapped_column(Text)  # e.g. "fixed in commit X" / "rolled back migration Y"

    # Business/customer impact, informational only — no automatic gating
    # tied to this (confirmed directly with the user). One of: Critical /
    # High / Medium / Low.
    severity: Mapped[str] = mapped_column(String(20), default="Medium")

    # Richer sub-state layered on top of `status` (Open/Resolved), which
    # stays the coarse gate the resolve logic keys off. One of: Detected /
    # Fix Identified / Fix Released / Remediating Customers / Closed.
    phase: Mapped[str] = mapped_column(String(30), default="Detected")

    # Captured at resolution time, alongside root_cause/resolution — both
    # optional, unlike those two, since not every incident has a distinct
    # process lesson beyond its technical cause.
    lessons_learned: Mapped[str | None] = mapped_column(Text)
    detection_gap: Mapped[str | None] = mapped_column(Text)

    status: Mapped[str] = mapped_column(String(20), default="Open")  # Open | Resolved

    # May differ from created_at when logged retroactively.
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
