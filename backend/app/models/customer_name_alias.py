from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class CustomerNameAlias(Base):
    """A raw Jira 'Customer' field string that refers to an existing local
    Customer under a different name/spelling — set when a human resolves an
    UnmatchedUpgradeCustomer by linking it to an existing customer, rather
    than renaming the customer's real established name to match one Jira
    ticket's string. Checked as a matching fallback in the upgrade sync."""

    __tablename__ = "customer_name_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    alias_name: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    customer: Mapped["Customer"] = relationship()


from app.models.customer import Customer  # noqa: E402
