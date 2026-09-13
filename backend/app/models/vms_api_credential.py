from datetime import datetime
from sqlalchemy import Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class VmsApiCredential(Base):
    """Machine-to-machine credential for querying a customer's live Dataloy
    VMS (api.dataloy.com — OAuth2 client-credentials flow, confirmed live:
    client_id/client_secret -> a 24h JWT access_token). One row per customer
    tenant (credentials are provisioned per-tenant by Dataloy); customer_id
    NULL is the shared demo/generic credential usable for non-customer-
    specific simulation, per the user's own description.

    client_secret is a real secret — every read-side schema for this model
    must omit it entirely (not mask it, just never include the field), same
    principle as this app already applies to never exposing values it
    shouldn't. Only a dedicated write action ever sets it.
    """
    __tablename__ = "vms_api_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), unique=True
    )
    label: Mapped[str] = mapped_column(String(100))

    client_id: Mapped[str] = mapped_column(String(200))
    client_secret: Mapped[str] = mapped_column(String(500))
    audience: Mapped[str] = mapped_column(String(50), default="https://dataloy")

    cached_token: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    customer: Mapped["Customer"] = relationship()


from app.models.customer import Customer  # noqa: E402
