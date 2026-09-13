from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class OllamaConversation(Base):
    """A persisted chat with the local Ollama model. No user_id/owner column
    — this app has no User table and no per-request identity storage beyond
    a JWT's email claim (confirmed via routers/auth.py), so this is a single
    shared conversation list, same as AiObservation/OpsNote have no owner
    today. Real multi-user separation would need a users table first."""

    __tablename__ = "ollama_conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Auto-derived from the first ~60 chars of the first user message —
    # never user-editable, no rename action exists.
    title: Mapped[str] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )

    messages: Mapped[list["OllamaMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="OllamaMessage.created_at"
    )


class OllamaMessage(Base):
    __tablename__ = "ollama_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ollama_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)

    # Which model actually produced this reply — settings.ollama_model for
    # the normal path, "claude-haiku-4-5" for an escalated reply (see
    # routers/ollama_chat.py::escalate_conversation). NULL for user messages
    # and for rows written before this field existed.
    model_used: Mapped[str | None] = mapped_column(String(50))

    # The assembled context bundle actually sent to the model with this
    # message (see services/ollama_context.py) — stored for debuggability
    # (tracing a bad answer to bad retrieval vs. a bad model response),
    # never shown in the UI by default.
    context_used: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    conversation: Mapped["OllamaConversation"] = relationship(back_populates="messages")
