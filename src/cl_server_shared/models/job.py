"""Job model shared between store service and compute worker."""
from typing import Optional
from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

class Job(Base):
    """Job model storing compute job metadata, status, and results.

    This model is shared between:
    - store_service: Creates and manages jobs
    - compute_worker: Claims and processes jobs

    Both services access the same database table.
    """
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)

    params: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    started_at: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    task_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_by: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    def __repr__(self):
        return f"<Job(job_id={self.job_id}, task_type={self.task_type}, status={self.status})>"
