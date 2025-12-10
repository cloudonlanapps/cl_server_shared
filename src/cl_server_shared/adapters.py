"""Adapter implementations for cl_ml_tools protocols.

This module provides adapter classes that bridge the cl_ml_tools library
protocols (JobRepository and FileStorage) with the application's actual
implementations (SQLAlchemy database and FileStorageService).

The adapters handle:
- Mapping between library Job schema (minimal) and database Job model (full fields)
- JSON serialization/deserialization for params and task_output
- Adding database-specific fields (timestamps, retry logic, user tracking)
- Atomic job claiming with optimistic locking
- MQTT broadcasting of job progress updates
"""

import json
import time
from pathlib import Path
from typing import Optional, List, Dict, Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

# Library protocols and schemas
from cl_ml_tools.common.job_repository import JobRepository
from cl_ml_tools.common.file_storage import FileStorage
from cl_ml_tools.common.schemas import Job as LibraryJob

# Application models and services
from .models.job import Job as DatabaseJob
from .file_storage import FileStorageService

# MQTT broadcasting
from .config import (
    BROADCAST_TYPE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
)
from .mqtt import get_broadcaster


class SQLAlchemyJobRepository:
    """SQLAlchemy implementation of JobRepository protocol.

    This adapter bridges the cl_ml_tools JobRepository protocol with
    SQLAlchemy database operations. It handles:

    - Mapping library Job (7 fields) ↔ database Job (14 fields)
    - JSON serialization for params and task_output
    - Timestamp management (created_at, started_at, completed_at)
    - Retry logic fields (retry_count, max_retries)
    - User tracking (created_by)
    - Atomic job claiming using optimistic locking

    Example:
        session_factory = create_session_factory(engine)
        repository = SQLAlchemyJobRepository(session_factory)

        # Add job
        library_job = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={"width": 100, "height": 100}
        )
        repository.add_job(library_job, created_by="user123", priority=5)

        # Fetch next job
        job = repository.fetch_next_job(["image_resize"])
    """

    def __init__(self, session_factory):
        """Initialize repository with session factory and MQTT broadcaster.

        Args:
            session_factory: SQLAlchemy session factory (sessionmaker)
        """
        self.session_factory = session_factory

        # Setup broadcaster for job progress updates
        self.broadcaster = get_broadcaster(
            broadcast_type=BROADCAST_TYPE,
            broker=MQTT_BROKER,
            port=MQTT_PORT,
            topic=MQTT_TOPIC,
        )

    def _db_to_library_job(self, db_job: DatabaseJob) -> LibraryJob:
        """Convert database Job to library Job schema.

        Strips database-specific fields and parses JSON strings.

        Args:
            db_job: SQLAlchemy Job model instance

        Returns:
            Library Job with minimal fields
        """
        # Parse params from JSON string to dict
        params = json.loads(db_job.params) if db_job.params else {}

        # Parse task_output from JSON string to dict
        task_output = None
        if db_job.task_output:
            try:
                task_output = json.loads(db_job.task_output)
            except json.JSONDecodeError:
                task_output = None

        return LibraryJob(
            job_id=db_job.job_id,
            task_type=db_job.task_type,
            params=params,
            status=db_job.status,
            progress=db_job.progress,
            task_output=task_output,
            error_message=db_job.error_message,
        )

    def add_job(
        self,
        job: LibraryJob,
        created_by: Optional[str] = None,
        priority: Optional[int] = None,
    ) -> str:
        """Save job to database.

        Converts library Job to database Job, adding:
        - created_at timestamp
        - retry_count = 0
        - max_retries = 3
        - created_by from parameter

        Args:
            job: Library Job object to save
            created_by: Optional user identifier
            priority: Optional priority (currently not stored, for future use)

        Returns:
            The job_id of the saved job
        """
        with self.session_factory() as session:
            # Convert library Job to database Job
            db_job = DatabaseJob(
                job_id=job.job_id,
                task_type=job.task_type,
                params=json.dumps(job.params),
                status=job.status,
                progress=job.progress,
                created_at=int(time.time() * 1000),  # Current timestamp in milliseconds
                task_output=json.dumps(job.task_output) if job.task_output else None,
                error_message=job.error_message,
                retry_count=0,
                max_retries=3,
                created_by=created_by,
            )

            session.add(db_job)
            session.commit()

            return db_job.job_id

    def get_job(self, job_id: str) -> Optional[LibraryJob]:
        """Get job by ID.

        Args:
            job_id: Unique job identifier

        Returns:
            Library Job object if found, None otherwise
        """
        with self.session_factory() as session:
            stmt = select(DatabaseJob).where(DatabaseJob.job_id == job_id)
            db_job = session.execute(stmt).scalar_one_or_none()

            if db_job:
                return self._db_to_library_job(db_job)
            return None

    def update_job(self, job_id: str, **kwargs) -> bool:
        """Update job fields and broadcast progress to MQTT.

        Handles both library fields and database-specific fields:
        - Library fields: status, progress, task_output, error_message
        - Database fields: started_at, completed_at, retry_count

        Special handling:
        - task_output dict is serialized to JSON string
        - When status changes to "processing", sets started_at if not set
        - When status changes to "completed" or "error", sets completed_at
        - Broadcasts progress updates via MQTT when progress changes

        Args:
            job_id: Unique job identifier
            **kwargs: Fields to update

        Returns:
            True if job was updated, False if job not found
        """
        with self.session_factory() as session:
            # Build update values
            update_values = {}

            # Track status and progress for broadcasting
            status = kwargs.get("status")
            progress = kwargs.get("progress")

            # Handle library fields
            if "status" in kwargs:
                update_values["status"] = kwargs["status"]

                # Auto-set timestamps based on status
                if kwargs["status"] == "processing":
                    # Check if started_at is not already set
                    stmt = select(DatabaseJob.started_at).where(
                        DatabaseJob.job_id == job_id
                    )
                    started_at = session.execute(stmt).scalar_one_or_none()
                    if started_at is None:
                        update_values["started_at"] = int(time.time() * 1000)

                elif kwargs["status"] in ("completed", "error"):
                    update_values["completed_at"] = int(time.time() * 1000)

            if "progress" in kwargs:
                update_values["progress"] = kwargs["progress"]

            if "task_output" in kwargs:
                # Serialize dict to JSON string
                task_output = kwargs["task_output"]
                update_values["task_output"] = (
                    json.dumps(task_output) if task_output else None
                )

            if "error_message" in kwargs:
                update_values["error_message"] = kwargs["error_message"]

            # Handle database-specific fields (passed through directly)
            if "retry_count" in kwargs:
                update_values["retry_count"] = kwargs["retry_count"]

            if "started_at" in kwargs:
                update_values["started_at"] = kwargs["started_at"]

            if "completed_at" in kwargs:
                update_values["completed_at"] = kwargs["completed_at"]

            if not update_values:
                return False

            # Execute update
            stmt = (
                update(DatabaseJob)
                .where(DatabaseJob.job_id == job_id)
                .values(**update_values)
            )
            result = session.execute(stmt)
            session.commit()

            # Broadcast progress update via MQTT if progress was updated
            if result.rowcount > 0 and progress is not None:
                self._broadcast_progress(job_id, status or "processing", progress)

            return result.rowcount > 0

    def _broadcast_progress(self, job_id: str, status: str, progress: float):
        """Broadcast job progress update via MQTT.

        Args:
            job_id: Unique job identifier
            status: Current job status
            progress: Progress percentage (0-100)
        """
        if not self.broadcaster.connected:
            return

        self.broadcaster.publish_event(status, job_id, {"progress": progress})

    def fetch_next_job(self, task_types: List[str]) -> Optional[LibraryJob]:
        """Atomically find and claim the next queued job.

        Uses optimistic locking to prevent race conditions:
        1. Find job with status="queued" AND task_type in task_types
        2. Atomically update status to "processing" and set started_at
        3. Return the claimed job as library Job

        The UPDATE ... WHERE query ensures atomicity - only one worker
        will successfully claim a specific job even if multiple workers
        query simultaneously.

        Args:
            task_types: List of task types to process

        Returns:
            Library Job object with status="processing" if found, None otherwise
        """
        if not task_types:
            return None

        with self.session_factory() as session:
            # Find next queued job with matching task type
            # Order by created_at to process oldest first
            stmt = (
                select(DatabaseJob)
                .where(
                    DatabaseJob.status == "queued",
                    DatabaseJob.task_type.in_(task_types),
                )
                .order_by(DatabaseJob.created_at)
                .limit(1)
            )

            db_job = session.execute(stmt).scalar_one_or_none()

            if not db_job:
                return None

            # Atomically claim the job using optimistic locking
            # This UPDATE will only succeed if status is still "queued"
            current_time = int(time.time() * 1000)
            stmt = (
                update(DatabaseJob)
                .where(
                    DatabaseJob.job_id == db_job.job_id,
                    DatabaseJob.status == "queued",  # Optimistic lock
                )
                .values(status="processing", started_at=current_time)
            )

            result = session.execute(stmt)
            session.commit()

            # Check if we successfully claimed the job
            if result.rowcount == 0:
                # Another worker claimed it first
                return None

            # Refresh the job object to get updated values
            session.refresh(db_job)

            return self._db_to_library_job(db_job)

    def delete_job(self, job_id: str) -> bool:
        """Delete job from database.

        Args:
            job_id: Unique job identifier

        Returns:
            True if job was deleted, False if job not found
        """
        with self.session_factory() as session:
            stmt = select(DatabaseJob).where(DatabaseJob.job_id == job_id)
            db_job = session.execute(stmt).scalar_one_or_none()

            if db_job:
                session.delete(db_job)
                session.commit()
                return True

            return False


class FileStorageAdapter:
    """Adapter wrapping FileStorageService to implement FileStorage protocol.

    This is a thin wrapper that adapts the existing FileStorageService
    to satisfy the cl_ml_tools FileStorage protocol. Most methods
    are simple pass-throughs, but some handle path conversions.

    The FileStorage protocol expects absolute paths, and FileStorageService
    returns relative paths from save_input_file. This adapter handles the
    conversion by using get_absolute_path.

    Example:
        file_storage_service = FileStorageService("/path/to/media")
        adapter = FileStorageAdapter(file_storage_service)

        # Now adapter can be passed to cl_ml_tools functions
        job_dir = adapter.create_job_directory(job_id)
        input_path = adapter.get_input_path(job_id)
    """

    def __init__(self, file_storage_service: FileStorageService):
        """Initialize adapter with FileStorageService.

        Args:
            file_storage_service: Existing FileStorageService instance
        """
        self.service = file_storage_service

    def create_job_directory(self, job_id: str) -> Path:
        """Create job directory structure with input/output subdirectories.

        Args:
            job_id: Unique job identifier

        Returns:
            Absolute path to the job directory
        """
        return self.service.create_job_directory(job_id)

    def get_input_path(self, job_id: str) -> Path:
        """Get absolute path to job's input directory.

        Args:
            job_id: Unique job identifier

        Returns:
            Absolute path to the input directory
        """
        return self.service.get_input_path(job_id)

    def get_output_path(self, job_id: str) -> Path:
        """Get absolute path to job's output directory.

        Args:
            job_id: Unique job identifier

        Returns:
            Absolute path to the output directory
        """
        return self.service.get_output_path(job_id)

    async def save_input_file(self, job_id: str, filename: str, file) -> dict:
        """Save uploaded file to job's input directory.

        Note: FileStorageService returns relative path in "path" field.
        This is converted to absolute path to match protocol expectations.

        Args:
            job_id: Unique job identifier
            filename: Target filename
            file: File object (FastAPI UploadFile)

        Returns:
            Dict with file metadata:
            {
                "filename": str,  # Saved filename
                "path": str,      # Absolute path to saved file (converted from relative)
                "size": int,      # File size in bytes
                "hash": str       # File hash (SHA256)
            }
        """
        result = await self.service.save_input_file(job_id, filename, file)

        # Convert relative path to absolute path
        if "path" in result:
            relative_path = result["path"]
            absolute_path = self.service.get_absolute_path(relative_path)
            result["path"] = str(absolute_path)

        return result

    def cleanup_job(self, job_id: str) -> bool:
        """Delete job directory and all its files.

        Args:
            job_id: Unique job identifier

        Returns:
            True if deleted, False if directory didn't exist
        """
        return self.service.cleanup_job(job_id)
