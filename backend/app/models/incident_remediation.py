from datetime import date, datetime
from sqlalchemy import Integer, Boolean, Date, DateTime, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class IncidentRemediation(Base):
    """One row per customer affected by a 'product' Incident. Deliberately
    has no status field of its own — remediation status is always derived
    live from the linked Upgrade's real stage, never duplicated here, to
    avoid the exact class of two-representations-drift bug this session
    spent hours finding and fixing (SMT/SFL/Dava/Navigare/Seapeak/G2 Ocean/
    COE Shipping). NULL upgrade_id means no real upgrade has been linked
    yet; manually_resolved+notes is the escape hatch for the rare
    non-upgrade remediation (a config change, a workaround)."""

    __tablename__ = "incident_remediations"
    __table_args__ = (UniqueConstraint("incident_id", "customer_id", name="uq_incident_customer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    incident_id: Mapped[int] = mapped_column(Integer, ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    upgrade_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("upgrades.id", ondelete="SET NULL"))

    manually_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)

    # Third remediation path — a compensating control / accepted risk, for
    # a customer who won't get a real patch or resolution soon. One of:
    # accepted_risk / workaround_applied. All four mitigation_* fields are
    # required together (enforced in the router) — never set silently, same
    # bar already enforced for manually_resolved+notes.
    mitigation_type: Mapped[str | None] = mapped_column(String(30))
    mitigation_owner: Mapped[str | None] = mapped_column(String(150))
    mitigation_note: Mapped[str | None] = mapped_column(Text)
    review_by_date: Mapped[date | None] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    incident: Mapped["Incident"] = relationship()
    customer: Mapped["Customer"] = relationship()
    upgrade: Mapped["Upgrade | None"] = relationship()


from app.models.incident import Incident  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.upgrade import Upgrade  # noqa: E402
