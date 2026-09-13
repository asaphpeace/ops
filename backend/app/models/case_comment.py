from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class CaseComment(Base):
    """Local cache of real Jira comments — keyed by jira_ref, not case_id.
    Most tickets processed by the bulk aggregate functions in services/jira.py
    (team_open_stats etc.) have no local Case row at all, so case_id is an
    optional back-reference only, set when a real Case happens to exist at
    write time; lookup and dedup are always by jira_ref."""
    __tablename__ = "case_comments"
    __table_args__ = (UniqueConstraint("jira_ref", "jira_comment_id", name="uq_case_comment_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("cases.id", ondelete="CASCADE"), nullable=True, index=True)
    jira_ref: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    jira_comment_id: Mapped[str] = mapped_column(String(30), nullable=False)
    author: Mapped[str] = mapped_column(String(200))
    created: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    text: Mapped[str] = mapped_column(Text)
    public: Mapped[bool | None] = mapped_column(Boolean)
    # Jira's raw author.accountType ("atlassian", "customer", "app", ...) —
    # confirmed live (DSD-31981) that a jsdPublic=True comment is NOT
    # reliably customer-authored: a real team member (accountType=
    # "atlassian") can post a public/customer-visible reply too. NULL for
    # rows cached before this column existed — callers must degrade
    # gracefully rather than assume "atlassian" or "customer" for those.
    author_account_type: Mapped[str | None] = mapped_column(String(20))
