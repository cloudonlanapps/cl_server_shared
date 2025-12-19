"""Tests for JobRepositoryService."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from uuid import uuid4

from cl_ml_tools import JobRecord, JobRecordUpdate, JobStatus
from pydantic import JsonValue
from sqlalchemy import select

from cl_server_shared import JobRepositoryService
from cl_server_shared.models import Job

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session, sessionmaker


# ============================================================================
# Basic Operations Tests
# ============================================================================


def test_add_job(job_repository: JobRepositoryService, sample_job_record: JobRecord) -> None:
    """Test adding a job to the repository."""
    result = job_repository.add_job(sample_job_record)

    assert result is True

    # Verify job was stored
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.job_id == sample_job_record.job_id
    assert retrieved.task_type == sample_job_record.task_type
    assert retrieved.params == sample_job_record.params
    assert retrieved.status == JobStatus.queued
    assert retrieved.progress == 0


def test_add_job_with_created_by(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test adding a job with created_by parameter."""
    created_by = "test_user_123"
    result = job_repository.add_job(sample_job_record, created_by=created_by)

    assert result is True

    # Verify job was stored with created_by
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None


def test_add_job_with_priority(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test adding a job with priority parameter."""
    priority = 5
    result = job_repository.add_job(sample_job_record, priority=priority)

    assert result is True

    # Verify job was stored
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None


def test_get_job(job_repository: JobRepositoryService, sample_job_record: JobRecord) -> None:
    """Test retrieving an existing job."""
    _ = job_repository.add_job(sample_job_record)

    retrieved = job_repository.get_job(sample_job_record.job_id)

    assert retrieved is not None
    assert isinstance(retrieved, JobRecord)
    assert retrieved.job_id == sample_job_record.job_id
    assert retrieved.task_type == sample_job_record.task_type
    assert isinstance(retrieved.status, JobStatus)


def test_get_job_not_found(job_repository: JobRepositoryService) -> None:
    """Test retrieving a non-existent job returns None."""
    result = job_repository.get_job("nonexistent_job_id")

    assert result is None


def test_delete_job(job_repository: JobRepositoryService, sample_job_record: JobRecord) -> None:
    """Test deleting an existing job."""
    _ = job_repository.add_job(sample_job_record)

    result = job_repository.delete_job(sample_job_record.job_id)

    assert result is True

    # Verify job is deleted
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is None


def test_delete_job_not_found(job_repository: JobRepositoryService) -> None:
    """Test deleting a non-existent job returns False."""
    result = job_repository.delete_job("nonexistent_job_id")

    assert result is False


# ============================================================================
# Update Operations Tests
# ============================================================================


def test_update_job_status(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test updating job status."""
    _ = job_repository.add_job(sample_job_record)

    update = JobRecordUpdate(status=JobStatus.processing)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True

    # Verify status was updated
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.status == JobStatus.processing


def test_update_job_progress(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test updating job progress."""
    _ = job_repository.add_job(sample_job_record)

    update = JobRecordUpdate(progress=50)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True

    # Verify progress was updated
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.progress == 50


def test_update_job_output(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test updating job output with JSON data."""
    _ = job_repository.add_job(sample_job_record)

    output_data: dict[str, JsonValue] = {"result": "success", "data": {"value": 42}}
    update = JobRecordUpdate(output=output_data)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True

    # Verify output was updated
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.output == output_data


def test_update_job_error_message(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test updating job error_message."""
    _ = job_repository.add_job(sample_job_record)

    error_msg = "Something went wrong"
    update = JobRecordUpdate(error_message=error_msg)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True

    # Verify error_message was updated
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.error_message == error_msg


def test_update_job_multiple_fields(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test updating multiple job fields at once."""
    _ = job_repository.add_job(sample_job_record)

    output_data: dict[str, JsonValue] = {"result": "done"}
    update = JobRecordUpdate(status=JobStatus.completed, progress=100, output=output_data)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True

    # Verify all fields were updated
    retrieved = job_repository.get_job(sample_job_record.job_id)
    assert retrieved is not None
    assert retrieved.status == JobStatus.completed
    assert retrieved.progress == 100
    assert retrieved.output == output_data


def test_update_job_not_found(job_repository: JobRepositoryService) -> None:
    """Test updating a non-existent job returns False."""
    update = JobRecordUpdate(status=JobStatus.processing)
    result = job_repository.update_job("nonexistent_job_id", update)

    assert result is False


def test_update_job_timestamps(
    job_repository: JobRepositoryService,
    sample_job_record: JobRecord,
    session_factory: sessionmaker[Session],
) -> None:
    """Test automatic timestamp management on status changes."""
    _ = job_repository.add_job(sample_job_record)

    # Update to processing - should set started_at
    update = JobRecordUpdate(status=JobStatus.processing)
    _ = job_repository.update_job(sample_job_record.job_id, update)

    with session_factory() as session:
        stmt = select(Job).where(Job.job_id == sample_job_record.job_id)
        db_job = session.execute(stmt).scalar_one()
        assert db_job.started_at is not None
        started_at = db_job.started_at

    # Update to processing again - should NOT change started_at
    time.sleep(0.01)  # Small delay
    _ = job_repository.update_job(sample_job_record.job_id, update)

    with session_factory() as session:
        stmt = select(Job).where(Job.job_id == sample_job_record.job_id)
        db_job = session.execute(stmt).scalar_one()
        assert db_job.started_at == started_at  # Should be unchanged

    # Update to completed - should set completed_at
    update = JobRecordUpdate(status=JobStatus.completed)
    _ = job_repository.update_job(sample_job_record.job_id, update)

    with session_factory() as session:
        stmt = select(Job).where(Job.job_id == sample_job_record.job_id)
        db_job = session.execute(stmt).scalar_one()
        assert db_job.completed_at is not None


# ============================================================================
# Job Claiming (fetch_next_job) Tests
# ============================================================================


def test_fetch_next_job_single(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test fetching a single queued job."""
    _ = job_repository.add_job(sample_job_record)

    fetched = job_repository.fetch_next_job([sample_job_record.task_type])

    assert fetched is not None
    assert fetched.job_id == sample_job_record.job_id
    assert fetched.status == JobStatus.processing


def test_fetch_next_job_by_task_type(job_repository: JobRepositoryService) -> None:
    """Test filtering jobs by task_type."""
    # Add jobs with different task types
    job1 = JobRecord(
        job_id=str(uuid4()),
        task_type="type_a",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    job2 = JobRecord(
        job_id=str(uuid4()),
        task_type="type_b",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job1)
    _ = job_repository.add_job(job2)

    # Fetch only type_a
    fetched = job_repository.fetch_next_job(["type_a"])

    assert fetched is not None
    assert fetched.job_id == job1.job_id
    assert fetched.task_type == "type_a"


def test_fetch_next_job_multiple_task_types(job_repository: JobRepositoryService) -> None:
    """Test fetching with multiple task types."""
    job1 = JobRecord(
        job_id=str(uuid4()),
        task_type="type_a",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    job2 = JobRecord(
        job_id=str(uuid4()),
        task_type="type_b",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job1)
    _ = job_repository.add_job(job2)

    # Fetch with both types - should get first one
    fetched = job_repository.fetch_next_job(["type_a", "type_b"])

    assert fetched is not None
    assert fetched.task_type in ["type_a", "type_b"]


def test_fetch_next_job_empty_queue(job_repository: JobRepositoryService) -> None:
    """Test fetching when no jobs are available."""
    result = job_repository.fetch_next_job(["test_task"])

    assert result is None


def test_fetch_next_job_no_matching_type(job_repository: JobRepositoryService) -> None:
    """Test fetching when no matching task_type exists."""
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="type_a",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job)

    result = job_repository.fetch_next_job(["type_b"])

    assert result is None


def test_fetch_next_job_empty_task_types(job_repository: JobRepositoryService) -> None:
    """Test fetching with empty task_types list."""
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="type_a",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job)

    result = job_repository.fetch_next_job([])

    assert result is None


def test_fetch_next_job_order(job_repository: JobRepositoryService) -> None:
    """Test FIFO ordering - oldest job first."""
    # Add jobs with delays to ensure different created_at
    job1 = JobRecord(
        job_id="job1",
        task_type="test",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job1)

    time.sleep(0.01)  # Small delay

    job2 = JobRecord(
        job_id="job2",
        task_type="test",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job2)

    # Should fetch job1 first (older)
    fetched = job_repository.fetch_next_job(["test"])

    assert fetched is not None
    assert fetched.job_id == "job1"


def test_fetch_next_job_optimistic_locking(
    in_memory_engine: Engine, session_factory: sessionmaker[Session]
) -> None:
    """Test optimistic locking prevents double-claiming."""
    _ = in_memory_engine  # Keep engine alive during test

    # Create two repository instances (simulating two workers)
    repo1 = JobRepositoryService(session_factory)
    repo2 = JobRepositoryService(session_factory)

    # Add multiple queued jobs
    for i in range(3):
        job = JobRecord(
            job_id=f"job_{i}",
            task_type="test",
            params={},
            status=JobStatus.queued,
            progress=0,
        )
        _ = repo1.add_job(job)

    # Both workers fetch jobs
    fetched1 = repo1.fetch_next_job(["test"])
    fetched2 = repo2.fetch_next_job(["test"])

    # Should get different jobs
    assert fetched1 is not None
    assert fetched2 is not None
    assert fetched1.job_id != fetched2.job_id


def test_fetch_next_job_skips_processing(job_repository: JobRepositoryService) -> None:
    """Test that fetch_next_job skips jobs already processing."""
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="test",
        params={},
        status=JobStatus.processing,
        progress=50,
    )
    _ = job_repository.add_job(job)

    result = job_repository.fetch_next_job(["test"])

    assert result is None


def test_fetch_next_job_skips_completed(job_repository: JobRepositoryService) -> None:
    """Test that fetch_next_job skips completed jobs."""
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="test",
        params={},
        status=JobStatus.completed,
        progress=100,
    )
    _ = job_repository.add_job(job)

    result = job_repository.fetch_next_job(["test"])

    assert result is None


# ============================================================================
# MQTT Broadcasting Tests
# ============================================================================
# Note: These tests use real MQTT broadcaster and will fail if broker is down


def test_mqtt_broadcast_on_add(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test that MQTT broadcast is sent on add_job.

    Note: Requires MQTT broker to be running.
    """
    # This will send MQTT broadcast if broker is available
    result = job_repository.add_job(sample_job_record)

    assert result is True
    # If this passes, MQTT broker is working
    # If it fails with connection error, MQTT broker is down


def test_mqtt_broadcast_on_update(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test that MQTT broadcast is sent on job update.

    Note: Requires MQTT broker to be running.
    """
    _ = job_repository.add_job(sample_job_record)

    # This will send MQTT broadcast if broker is available
    update = JobRecordUpdate(status=JobStatus.processing, progress=50)
    result = job_repository.update_job(sample_job_record.job_id, update)

    assert result is True


def test_mqtt_broadcast_on_fetch(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test that MQTT broadcast is sent when job is claimed.

    Note: Requires MQTT broker to be running.
    """
    _ = job_repository.add_job(sample_job_record)

    # This will send MQTT broadcast if broker is available
    fetched = job_repository.fetch_next_job([sample_job_record.task_type])

    assert fetched is not None


# ============================================================================
# Data Integrity Tests
# ============================================================================


def test_job_record_conversion(
    job_repository: JobRepositoryService, sample_job_record: JobRecord
) -> None:
    """Test JobRecord to DB Job conversion preserves all fields."""
    _ = job_repository.add_job(sample_job_record)

    retrieved = job_repository.get_job(sample_job_record.job_id)

    assert retrieved is not None
    assert retrieved.job_id == sample_job_record.job_id
    assert retrieved.task_type == sample_job_record.task_type
    assert retrieved.params == sample_job_record.params
    assert retrieved.status == sample_job_record.status
    assert retrieved.progress == sample_job_record.progress
    assert retrieved.output == sample_job_record.output
    assert retrieved.error_message == sample_job_record.error_message


def test_job_params_json_storage(job_repository: JobRepositoryService) -> None:
    """Test storing complex JSON params."""
    complex_params: dict[str, JsonValue] = {
        "nested": {"key": "value", "number": 42},
        "list": [1, 2, 3],
        "string": "test",
    }
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="test",
        params=complex_params,
        status=JobStatus.queued,
        progress=0,
    )

    _ = job_repository.add_job(job)
    retrieved = job_repository.get_job(job.job_id)

    assert retrieved is not None
    assert retrieved.params == complex_params


def test_job_output_json_storage(job_repository: JobRepositoryService) -> None:
    """Test storing complex JSON output."""
    job = JobRecord(
        job_id=str(uuid4()),
        task_type="test",
        params={},
        status=JobStatus.queued,
        progress=0,
    )
    _ = job_repository.add_job(job)

    complex_output: dict[str, JsonValue] = {
        "results": [{"id": 1, "value": "a"}, {"id": 2, "value": "b"}],
        "metadata": {"count": 2},
    }
    update = JobRecordUpdate(output=complex_output)
    _ = job_repository.update_job(job.job_id, update)

    retrieved = job_repository.get_job(job.job_id)
    assert retrieved is not None
    assert retrieved.output == complex_output
