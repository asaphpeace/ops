from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ReleaseNoteFeature(Base):
    """One real new-feature entry from a master release's public Synopsis
    page (releasenotes.dataloy.com), cached locally so the Education view
    doesn't hit the external site on every load. Master releases only —
    patch releases (8.30.1, 8.30.2...) carry bug fixes, not new features,
    confirmed live against the real site. Fetched once per version and
    never re-fetched once successful — a published master release's
    content doesn't change after the fact."""

    __tablename__ = "release_note_features"
    __table_args__ = (UniqueConstraint("version", "ticket_id", "title", name="uq_release_note_feature"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # e.g. "8.30"
    ticket_id: Mapped[str | None] = mapped_column(String(30))  # e.g. "VMS-25177"
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str | None] = mapped_column(String(150))  # e.g. "Time Charter Contract Control"
    description: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(String(300), nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
