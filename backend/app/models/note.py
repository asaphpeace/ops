from datetime import datetime
from sqlalchemy import Boolean, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CustomerNote(Base):
    __tablename__ = "customer_notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(50), default="Asaph")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    # Same note, same list — just also rendered in the Customer Drill
    # Panel's always-visible header (DrillPanel.vue's #header slot, real
    # and independent of which tab is active) so an important note (an
    # upgrade hint, a sensitive request) doesn't require opening Notes to
    # see. Multiple notes can be sticky at once; un-pinning just flips
    # this back, the note itself is never deleted.
    is_sticky: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    customer: Mapped["Customer"] = relationship(back_populates="notes")


from app.models.customer import Customer  # noqa: E402
