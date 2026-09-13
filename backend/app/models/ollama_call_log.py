from datetime import datetime
from sqlalchemy import Integer, String, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class OllamaCallLog(Base):
    """One row per real call to the local Ollama server — both the
    supervisor's background narration (services/ollama_supervisor.py) and
    interactive chat (routers/ollama_chat.py) write here, distinguished by
    `purpose`, so the metrics view (duration/requests/success rate) covers
    the whole feature from one table. duration_ms/prompt_eval_count/
    eval_count are real fields Ollama itself returns on its final response
    chunk — never fabricated."""

    __tablename__ = "ollama_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # "chat" | "supervisor_fixed_but_open" | "supervisor_cross_signal"
    purpose: Mapped[str] = mapped_column(String(40))

    model_used: Mapped[str] = mapped_column(String(50))
    success: Mapped[bool] = mapped_column(Boolean)
    error_message: Mapped[str | None] = mapped_column(Text)

    duration_ms: Mapped[int | None] = mapped_column(Integer)
    prompt_eval_count: Mapped[int | None] = mapped_column(Integer)
    eval_count: Mapped[int | None] = mapped_column(Integer)

    conversation_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ollama_conversations.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
