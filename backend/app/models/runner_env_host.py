from datetime import datetime
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class RunnerEnvHost(Base):
    """The public host of an aws-util environment that isn't linked to a
    customer instance (e.g. demo-test → demo.dataloy.com). aws-util env
    names don't always equal the hostname, and the env repos don't record
    it (checked: demo-test's repo only mentions infra hosts), so the
    Upgrade Runner's /info pre-check and post-check need to be told."""
    __tablename__ = "runner_env_hosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    environment: Mapped[str] = mapped_column(String(100), unique=True)
    host: Mapped[str] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
