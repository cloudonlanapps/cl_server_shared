"""Job model shared between store service and compute worker."""

from typing import TypeAlias, override

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base

# for ORM we don't use it from Pytentic, hence define JSONObject here
#
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]

JSONObject: TypeAlias = dict[str, JSONValue]


class Job(Base):
    """Job model storing compute job metadata, status, and results.

    This model is shared between:
    - store_service: Creates and manages jobs
    - compute_worker: Claims and processes jobs

    Both services access the same database table.

    Database-specific fields (not in JobRecord):
    - id: Primary key
    - priority: Job priority level
    - created_at, started_at, completed_at: Timestamps in milliseconds
    - retry_count, max_retries: Retry logic
    - created_by: User attribution
    """

    __tablename__ = "jobs"  # pyright: ignore[reportUnannotatedClassAttribute]

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)

    # JSON fields for params and output (dict, not string)
    params: Mapped[JSONObject] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=False,
        default=dict,
    )

    output: Mapped[JSONObject | None] = mapped_column(
        MutableDict.as_mutable(JSON),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String, nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    started_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    completed_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_by: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    updated_at: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    @override
    def __repr__(self) -> str:
        return f"<Job(job_id={self.job_id}, task_type={self.task_type}, status={self.status})>"
