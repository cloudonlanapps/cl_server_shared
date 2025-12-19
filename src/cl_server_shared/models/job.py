"""Job model shared between store service and compute worker."""

from typing import TYPE_CHECKING, TypeAlias, override

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base

if TYPE_CHECKING:
    from cl_ml_tools.common.schema_job_record import JobRecord

# TODO: Move this to cl_ml_tools.common.schema_job_record
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | list["JSONValue"] | dict[str, "JSONValue"]


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

    # JSON fields for params and task_output (dict, not string)
    params: Mapped[JSONValue] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[JSONValue] = mapped_column(JSON, nullable=True)

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

    # -------------------------------------------------------------------------
    # Pydantic Conversion Helpers
    # -------------------------------------------------------------------------

    def to_job_record(self) -> "JobRecord":
        """Convert SQLAlchemy Job to Pydantic JobRecord.

        Returns:
            Pydantic JobRecord with core job fields
        """
        from cl_ml_tools.common.schema_job_record import JobRecord, JobStatus

        return JobRecord(
            job_id=self.job_id,
            task_type=self.task_type,
            params=self.params,  # pyright: ignore[reportArgumentType] TODO: Remove this ignore once JobRecord is udated with JSONValue
            output=self.output,  # pyright: ignore[reportArgumentType] TODO: Remove this ignore once JobRecord is udated with JSONValue
            status=JobStatus(self.status),
            progress=self.progress,
            error_message=self.error_message,
        )

    @classmethod
    def from_pydantic(
        cls,
        job_record: "JobRecord",
        *,
        created_by: str | None = None,
        priority: int | None = None,
    ) -> "Job":
        """Create SQLAlchemy Job from Pydantic JobRecord.

        Args:
            job_record: Pydantic JobRecord
            created_by: Optional user identifier
            priority: Optional priority level

        Returns:
            SQLAlchemy Job instance (not persisted)
        """
        import time

        return cls(
            job_id=job_record.job_id,
            task_type=job_record.task_type,
            params=job_record.params,
            status=job_record.status.value,
            progress=job_record.progress,
            task_output=job_record.output,
            error_message=job_record.error_message,
            created_at=int(time.time() * 1000),
            priority=priority or 0,
            retry_count=0,
            max_retries=3,
            created_by=created_by,
        )
