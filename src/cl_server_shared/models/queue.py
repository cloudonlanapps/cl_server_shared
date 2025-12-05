"""Queue entry model for priority-based job management."""
from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

class QueueEntry(Base):
    """Priority queue entry for job scheduling.

    Used by store_service to manage job priority.
    Note: Currently compute_worker ignores priority and processes FIFO.
    """
    __tablename__ = "queue_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    enqueued_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    def __repr__(self):
        return f"<QueueEntry(job_id={self.job_id}, priority={self.priority})>"
