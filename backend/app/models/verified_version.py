from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class VerifiedVersion(Base):
    """A VMS release the Upgrade Runner has accepted as a real upgrade target.

    source="releasenotes": confirmed on releasenotes.dataloy.com, remembered
    so it stays usable if the site is later unreachable.
    source="manual": confirmed by a person while releasenotes lags behind
    publication (a real, recurring delay) — note says how. Not a blind
    bypass: the real run's own ecr_tag_check still refuses a version whose
    image was never built."""
    __tablename__ = "verified_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[str] = mapped_column(String(40), unique=True)
    source: Mapped[str] = mapped_column(String(20))  # releasenotes / manual
    note: Mapped[str | None] = mapped_column(Text)
    verified_by: Mapped[str] = mapped_column(String(200), default="you")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
