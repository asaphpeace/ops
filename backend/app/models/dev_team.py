from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class DevTeam(Base):
    """A Dataloy product/dev team (Aliens, Visions, Rockets League) — who
    support routes a ticket to once the affected VMS module is known.
    Seeded from the L2 Support Hub's TEAMS constant, then maintained in the
    Tools → Teams & Routing tab so the roster can't silently go stale the
    way the hub's hardcoded copy did."""
    __tablename__ = "dev_teams"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    emoji: Mapped[str | None] = mapped_column(String(10))
    notes: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    members: Mapped[list["DevTeamMember"]] = relationship(
        back_populates="team", cascade="all, delete-orphan", order_by="DevTeamMember.sort_order",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class DevTeamMember(Base):
    """display_name is what support calls them; jira_name is the exact Jira
    display string (case assignee / comment author) when one is confirmed,
    left null rather than guessed when the first name is ambiguous in Jira
    (e.g. two different "Kjetil"s comment on DSD tickets)."""
    __tablename__ = "dev_team_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, ForeignKey("dev_teams.id", ondelete="CASCADE"))
    display_name: Mapped[str] = mapped_column(String(200))
    jira_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(10))  # PM / EL / null
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    team: Mapped[DevTeam] = relationship(back_populates="members")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)


class VmsModule(Base):
    """A VMS functional module and the dev team that owns it. team_id is
    nullable — a module with no confirmed owner stays unassigned rather
    than being parked on an arbitrary team."""
    __tablename__ = "vms_modules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    group_name: Mapped[str] = mapped_column(String(60))
    team_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("dev_teams.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
