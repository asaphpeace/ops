from datetime import datetime
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class AwsResource(Base):
    """
    One row per real AWS resource (EC2 or RDS instance), ingested from a
    periodic manual export — never a live boto3 poller (no live AWS
    credential is granted to this app). See services/aws_import.py for the
    parsing/matching logic and scripts/aws-export.sh for what the user
    actually runs to produce the export.

    `aws_environment` is the Old-AWS vs New-AWS split already tracked on
    Customer.infra — set explicitly by the human at upload time (a
    dropdown), never inferred from the export itself, which carries no
    such label. Old and New are literally separate AWS accounts, so a bare
    resource_id collision across them is possible — the unique constraint
    below includes aws_environment for exactly that reason, mirroring
    CustomerTenantInfo's own (customer_id, environment) uniqueness.
    """

    __tablename__ = "aws_resources"
    __table_args__ = (UniqueConstraint("resource_type", "resource_id", "aws_environment", name="uq_aws_resource"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "EC2" / "RDS"
    resource_id: Mapped[str] = mapped_column(String(60), nullable=False)  # i-0123... / DBInstanceIdentifier
    name: Mapped[str | None] = mapped_column(String(200))  # Name tag (EC2) / identifier (RDS)
    region: Mapped[str | None] = mapped_column(String(20))
    aws_environment: Mapped[str] = mapped_column(String(10), nullable=False)  # "Old" / "New"

    instance_type: Mapped[str | None] = mapped_column(String(30))  # EC2 type OR RDS DBInstanceClass
    engine: Mapped[str | None] = mapped_column(String(50))  # RDS only
    engine_version: Mapped[str | None] = mapped_column(String(30))  # RDS only
    state: Mapped[str | None] = mapped_column(String(30))  # running/stopped/available/...
    endpoint_or_ip: Mapped[str | None] = mapped_column(String(200))
    launched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Whatever the export contains beyond the modeled fields above is never
    # lost — same JSON-column precedent as WeeklyReport.snapshot.
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Matching — never silently auto-assigned, same principle as
    # tenant_discovery.py's probe-then-human-Accept flow. suggested_customer_id
    # is set by the name-heuristic on import; customer_id/customer_environment
    # are only ever set by a real human confirmation action.
    customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="SET NULL"))
    customer_environment: Mapped[str | None] = mapped_column(String(10))  # PROD/TEST/DEV, set only on confirm
    suggested_customer_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("customers.id", ondelete="SET NULL"))
    match_status: Mapped[str] = mapped_column(String(20), default="unmatched")  # unmatched / confirmed / internal
    match_method: Mapped[str | None] = mapped_column(String(20))  # "name_heuristic" / "manual"

    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer | None"] = relationship(foreign_keys=[customer_id])
    metric_snapshots: Mapped[list["AwsResourceMetricSnapshot"]] = relationship(
        back_populates="resource", cascade="all, delete-orphan"
    )


class AwsResourceMetricSnapshot(Base):
    """
    One row per import per resource — append-only, not upsert-in-place.
    The real ask was a "latest known snapshot" from each export, not a
    live time-series; every read path only ever selects the most recent
    row per resource, but appending costs nothing and avoids throwing
    away every prior export's numbers before a real time-series view is
    ever justified.
    """

    __tablename__ = "aws_resource_metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aws_resource_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("aws_resources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # the real CloudWatch datapoint time
    cpu_utilization_pct: Mapped[float | None] = mapped_column(Float)  # present on both EC2 + RDS
    raw_json: Mapped[dict] = mapped_column(JSON, nullable=False)  # everything else the export carried

    resource: Mapped["AwsResource"] = relationship(back_populates="metric_snapshots")


from app.models.customer import Customer  # noqa: E402
