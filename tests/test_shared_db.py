"""Unit tests for SQLAlchemyJobRepository and database models.

Tests repository operations, MQTT broadcasting, and integration workflows.
"""

import json
import time
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cl_ml_tools.common.schema_job_record import JobRecord, JobRecordUpdate, JobStatus

from cl_server_shared import SQLAlchemyJobRepository
from cl_server_shared.models import Base
from cl_server_shared.models import Job as DatabaseJob


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_engine():
    """Create in-memory SQLite database for testing."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def session_factory(test_engine):
    """Create session factory for testing."""
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture
def repository(session_factory):
    """Create SQLAlchemyJobRepository instance for testing."""
    return SQLAlchemyJobRepository(session_factory)


@pytest.fixture
def sample_job_record():
    """Create sample JobRecord for testing."""
    return JobRecord(
        job_id=str(uuid4()),
        task_type="image_resize",
        params={
            "input_path": "/tmp/input.jpg",
            "output_path": "/tmp/output.jpg",
            "width": 800,
            "height": 600,
        },
        status=JobStatus.queued,
        progress=0,
    )


# ============================================================================
# SQLAlchemyJobRepository Tests
# ============================================================================


class TestSQLAlchemyJobRepository:
    """Test suite for SQLAlchemyJobRepository."""

    def test_add_job(self, repository, sample_job_record):
        """Test adding a job to the database."""
        success = repository.add_job(
            sample_job_record, created_by="test_user", priority=5
        )

        assert success is True

        # Verify job was saved
        retrieved_job = repository.get_job(sample_job_record.job_id)
        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_job_record.job_id
        assert retrieved_job.task_type == sample_job_record.task_type
        assert retrieved_job.status == JobStatus.queued

    def test_add_job_with_database_fields(
        self, repository, session_factory, sample_job_record
    ):
        """Test that add_job adds database-specific fields correctly."""
        repository.add_job(sample_job_record, created_by="user123")

        # Check database directly
        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_job_record.job_id)
                .first()
            )

            assert db_job is not None
            assert db_job.created_at is not None
            assert db_job.created_at > 0
            assert db_job.created_by == "user123"
            assert db_job.retry_count == 0
            assert db_job.max_retries == 3

    def test_add_job_stores_params_as_dict(
        self, repository, session_factory, sample_job_record
    ):
        """Test that params dict is stored as JSON/dict (not string)."""
        repository.add_job(sample_job_record)

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_job_record.job_id)
                .first()
            )

            # params should be dict in database (JSON column type)
            assert isinstance(db_job.params, dict)
            assert db_job.params == sample_job_record.params

    def test_get_job(self, repository, sample_job_record):
        """Test retrieving a job by ID."""
        repository.add_job(sample_job_record)
        retrieved_job = repository.get_job(sample_job_record.job_id)

        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_job_record.job_id
        assert isinstance(retrieved_job.params, dict)
        assert isinstance(retrieved_job, JobRecord)

    def test_get_job_nonexistent(self, repository):
        """Test getting a job that doesn't exist returns None."""
        result = repository.get_job("nonexistent-job-id")
        assert result is None

    def test_update_job_status(self, repository, sample_job_record):
        """Test updating job status."""
        repository.add_job(sample_job_record)

        update = JobRecordUpdate(status=JobStatus.processing)
        success = repository.update_job(sample_job_record.job_id, update)

        assert success is True
        updated_job = repository.get_job(sample_job_record.job_id)
        assert updated_job.status == JobStatus.processing

    def test_update_job_progress(self, repository, sample_job_record):
        """Test updating job progress."""
        repository.add_job(sample_job_record)

        update = JobRecordUpdate(progress=50)
        repository.update_job(sample_job_record.job_id, update)

        updated_job = repository.get_job(sample_job_record.job_id)
        assert updated_job.progress == 50

    def test_update_job_sets_timestamps(
        self, repository, session_factory, sample_job_record
    ):
        """Test that status changes set appropriate timestamps."""
        repository.add_job(sample_job_record)

        # Update to processing should set started_at
        update = JobRecordUpdate(status=JobStatus.processing)
        repository.update_job(sample_job_record.job_id, update)

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_job_record.job_id)
                .first()
            )
            assert db_job.started_at is not None
            assert db_job.completed_at is None

        # Update to completed should set completed_at
        update = JobRecordUpdate(status=JobStatus.completed)
        repository.update_job(sample_job_record.job_id, update)

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_job_record.job_id)
                .first()
            )
            assert db_job.completed_at is not None

    def test_fetch_next_job(self, repository):
        """Test fetching next queued job."""
        # Add multiple jobs
        job1 = JobRecord(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={"input_path": "test.jpg", "output_path": "out.jpg"},
            status=JobStatus.queued,
            progress=0,
        )
        job2 = JobRecord(
            job_id=str(uuid4()),
            task_type="image_conversion",
            params={"input_path": "test.jpg", "output_path": "out.png"},
            status=JobStatus.queued,
            progress=0,
        )

        repository.add_job(job1)
        time.sleep(0.01)  # Ensure different created_at timestamps
        repository.add_job(job2)

        # Fetch next job for image_resize
        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job is not None
        assert fetched_job.job_id == job1.job_id
        assert fetched_job.status == JobStatus.processing

    def test_fetch_next_job_atomic(self, repository):
        """Test that fetch_next_job is atomic (only one worker gets the job)."""
        job = JobRecord(
            job_id=str(uuid4()),
            task_type="test",
            params={"input_path": "test.jpg", "output_path": "out.jpg"},
            status=JobStatus.queued,
            progress=0,
        )
        repository.add_job(job)

        # First fetch should succeed
        fetched1 = repository.fetch_next_job(["test"])
        assert fetched1 is not None

        # Second fetch should return None (job already claimed)
        fetched2 = repository.fetch_next_job(["test"])
        assert fetched2 is None

    def test_delete_job(self, repository, sample_job_record):
        """Test deleting a job."""
        repository.add_job(sample_job_record)
        result = repository.delete_job(sample_job_record.job_id)

        assert result is True
        assert repository.get_job(sample_job_record.job_id) is None

    def test_delete_job_nonexistent(self, repository):
        """Test deleting a nonexistent job returns False."""
        result = repository.delete_job("nonexistent-job-id")
        assert result is False

    def test_repository_implements_protocol(self, repository):
        """Test that SQLAlchemyJobRepository implements cl_ml_tools.JobRepository protocol."""
        from cl_ml_tools import JobRepository

        assert isinstance(repository, JobRepository)


# ============================================================================
# MQTT Broadcasting Tests
# ============================================================================


class TestSQLAlchemyJobRepositoryBroadcasting:
    """Tests for MQTT broadcasting in SQLAlchemyJobRepository."""

    def _create_mock_session_factory(self, rowcount=1):
        """Helper method to create properly mocked session factory."""
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.rowcount = rowcount
        mock_session.execute.return_value = mock_result

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__enter__ = Mock(return_value=mock_session)
        mock_session_factory.return_value.__exit__ = Mock(return_value=False)

        return mock_session_factory

    @patch("cl_server_shared.shared_db.get_broadcaster")
    def test_broadcaster_initialized(self, mock_get_broadcaster):
        """Test that broadcaster is initialized in __init__."""
        mock_broadcaster = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster
        mock_session_factory = Mock()

        repository = SQLAlchemyJobRepository(mock_session_factory)

        assert hasattr(repository, "broadcaster")
        assert repository.broadcaster is not None

    @patch("cl_server_shared.shared_db.get_broadcaster")
    def test_update_job_broadcasts_progress(self, mock_get_broadcaster):
        """Test that update_job broadcasts progress when progress is updated."""
        mock_broadcaster = Mock()
        mock_broadcaster.connected = True
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory()
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update job progress using JobRecordUpdate
        update = JobRecordUpdate(progress=50)
        repository.update_job("test-job-id", update)

        # Verify broadcast was called
        mock_broadcaster.publish_event.assert_called_once()
        call_args = mock_broadcaster.publish_event.call_args

        # Check that topic and payload were passed
        assert "topic" in call_args.kwargs
        assert "payload" in call_args.kwargs

        # Parse payload
        payload = json.loads(call_args.kwargs["payload"])
        assert payload["job_id"] == "test-job-id"
        assert payload["event_type"] == "processing"
        assert payload["progress"] == 50

    @patch("cl_server_shared.shared_db.get_broadcaster")
    def test_update_job_different_status(self, mock_get_broadcaster):
        """Test broadcasting with different job statuses."""
        mock_broadcaster = Mock()
        mock_broadcaster.publish_event = Mock()
        mock_get_broadcaster.return_value = mock_broadcaster

        mock_session_factory = self._create_mock_session_factory()
        repository = SQLAlchemyJobRepository(mock_session_factory)

        # Update to completed using JobRecordUpdate
        update = JobRecordUpdate(status=JobStatus.completed, progress=100)
        repository.update_job("test-job-id", update)

        # Verify broadcast
        assert mock_broadcaster.publish_event.called
        call_args = mock_broadcaster.publish_event.call_args
        payload = json.loads(call_args.kwargs["payload"])

        assert payload["event_type"] == "completed"
        assert payload["progress"] == 100


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Integration tests for repository and storage working together."""

    @pytest.mark.asyncio
    async def test_full_job_workflow(self, repository):
        """Test complete job workflow."""
        # Create job
        job = JobRecord(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={
                "input_path": "/tmp/input.jpg",
                "output_path": "/tmp/output.jpg",
                "width": 100,
                "height": 100,
            },
            status=JobStatus.queued,
            progress=0,
        )
        repository.add_job(job, created_by="test_user")

        # Fetch job (simulating worker)
        fetched_job = repository.fetch_next_job(["image_resize"])
        assert fetched_job is not None
        assert fetched_job.status == JobStatus.processing

        # Update progress
        update = JobRecordUpdate(progress=50)
        repository.update_job(job.job_id, update)

        # Mark complete with output
        task_output = {"processed_files": ["/path/to/output.jpg"]}
        update = JobRecordUpdate(
            status=JobStatus.completed, progress=100, output=task_output
        )
        repository.update_job(job.job_id, update)

        # Verify final state
        final_job = repository.get_job(job.job_id)
        assert final_job.status == JobStatus.completed
        assert final_job.progress == 100
        assert final_job.output["processed_files"] == ["/path/to/output.jpg"]
