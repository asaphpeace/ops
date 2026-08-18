from datetime import date
from sqlalchemy import Integer, String, Boolean, Date, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(20), nullable=False)  # Premier / Strategic / Scale
    csm: Mapped[str] = mapped_column(String(100), nullable=False)
    arr_gbp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Commercial
    product: Mapped[str | None] = mapped_column(String(100))
    plan: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str | None] = mapped_column(String(50))
    contacts: Mapped[str | None] = mapped_column(Text)
    renewal_date: Mapped[date | None] = mapped_column(Date)
    seats: Mapped[int] = mapped_column(Integer, default=0)
    sla_tier: Mapped[str] = mapped_column(String(50), default="Standard")

    # Health & sentiment
    health_score: Mapped[int] = mapped_column(Integer, default=50)
    sentiment: Mapped[str] = mapped_column(String(30), default="Neutral")
    churn_risk: Mapped[str] = mapped_column(String(20), default="Medium")

    # Upgrade tracking
    upgrades_used: Mapped[int] = mapped_column(Integer, default=0)
    upgrades_limit: Mapped[int] = mapped_column(Integer, default=10)
    prod_version: Mapped[str | None] = mapped_column(String(30))
    test_version: Mapped[str | None] = mapped_column(String(30))

    # Infrastructure
    infra: Mapped[str] = mapped_column(String(20), default="Old")  # Old / New / Mixed
    ip_fw: Mapped[bool] = mapped_column(Boolean, default=False)
    wildfly8: Mapped[bool] = mapped_column(Boolean, default=False)
    sso: Mapped[str] = mapped_column(String(50), default="None")
    integrations: Mapped[str] = mapped_column(String(200), default="None")
    api_customer: Mapped[bool] = mapped_column(Boolean, default=False)

    # Scheduling preferences
    pref_days: Mapped[str | None] = mapped_column(String(100))
    notice_required: Mapped[str | None] = mapped_column(String(50))
    blackout_periods: Mapped[str | None] = mapped_column(String(200))

    # Relationships
    cases: Mapped[list["Case"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    upgrades: Mapped[list["Upgrade"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    migration: Mapped["MigrationProject | None"] = relationship(back_populates="customer", uselist=False, cascade="all, delete-orphan")
    training_gaps: Mapped[list["TrainingGap"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    training_sessions: Mapped[list["TrainingSession"]] = relationship(back_populates="customer", cascade="all, delete-orphan")
    notes: Mapped[list["CustomerNote"]] = relationship(back_populates="customer", cascade="all, delete-orphan")


from app.models.case import Case  # noqa: E402
from app.models.upgrade import Upgrade  # noqa: E402
from app.models.migration_project import MigrationProject  # noqa: E402
from app.models.training import TrainingGap, TrainingSession  # noqa: E402
from app.models.note import CustomerNote  # noqa: E402
