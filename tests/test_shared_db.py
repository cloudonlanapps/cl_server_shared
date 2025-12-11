"""Unit tests for SQLAlchemyJobRepository and database models.

Tests repository operations, MQTT broadcasting, and integration workflows.
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from cl_ml_tools import Job as LibraryJob
from cl_server_shared import Job as DatabaseJob, SQLAlchemyJobRepository
from cl_server_shared.models import Base


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
def sample_library_job():
    """Create sample library Job for testing."""
    return LibraryJob(
        job_id=str(uuid4()),
        task_type="image_resize",
        params={
            "input_paths": ["/tmp/input.jpg"],
            "output_paths": ["/tmp/output.jpg"],
            "width": 800,
            "height": 600,
        },
        status="queued",
        progress=0,
    )


# ============================================================================
# SQL AlchemyJobRepository Tests
# ============================================================================


class TestSQLAlchemyJobRepository:
    """Test suite for SQLAlchemyJobRepository."""

    def test_add_job(self, repository, sample_library_job):
        """Test adding a job to the database."""
        job_id = repository.add_job(
            sample_library_job, created_by="test_user", priority=5
        )

        assert job_id == sample_library_job.job_id

        # Verify job was saved
        retrieved_job = repository.get_job(job_id)
        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_library_job.job_id
        assert retrieved_job.task_type == sample_library_job.task_type
        assert retrieved_job.status == "queued"

    def test_add_job_with_database_fields(
        self, repository, session_factory, sample_library_job
    ):
        """Test that add_job adds database-specific fields correctly."""
        repository.add_job(sample_library_job, created_by="user123")

        # Check database directly
        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_library_job.job_id)
                .first()
            )

            assert db_job is not None
            assert db_job.created_at is not None
            assert db_job.created_at > 0
            assert db_job.created_by == "user123"
            assert db_job.retry_count == 0
            assert db_job.max_retries == 3

    def test_add_job_serializes_params(
        self, repository, session_factory, sample_library_job
    ):
        """Test that params dict is serialized to JSON string."""
        repository.add_job(sample_library_job)

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_library_job.job_id)
                .first()
            )

            # params should be JSON string in database
            assert isinstance(db_job.params, str)
            params = json.loads(db_job.params)
            assert params == sample_library_job.params

    def test_get_job(self, repository, sample_library_job):
        """Test retrieving a job by ID."""
        repository.add_job(sample_library_job)
        retrieved_job = repository.get_job(sample_library_job.job_id)

        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_library_job.job_id
        assert isinstance(retrieved_job.params, dict)

    def test_get_job_nonexistent(self, repository):
        """Test getting a job that doesn't exist returns None."""
        result = repository.get_job("nonexistent-job-id")
        assert result is None

    def test_update_job_status(self, repository, sample_library_job):
        """Test updating job status."""
        repository.add_job(sample_library_job)
        success = repository.update_job(sample_library_job.job_id, status="processing")

        assert success is True
        updated_job = repository.get_job(sample_library_job.job_id)
        assert updated_job.status == "processing"

    def test_update_job_progress(self, repository, sample_library_job):
        """Test updating job progress."""
        repository.add_job(sample_library_job)
        repository.update_job(sample_library_job.job_id, progress=50)

        updated_job = repository.get_job(sample_library_job.job_id)
        assert updated_job.progress == 50

    def test_update_job_sets_timestamps(
        self, repository, session_factory, sample_library_job
    ):
        """Test that status changes set appropriate timestamps."""
        repository.add_job(sample_library_job)

        # Update to processing should set started_at
        repository.update_job(sample_library_job.job_id, status="processing")

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_library_job.job_id)
                .first()
            )
            assert db_job.started_at is not None
            assert db_job.completed_at is None

        # Update to completed should set completed_at
        repository.update_job(sample_library_job.job_id, status="completed")

        with session_factory() as session:
            db_job = (
                session.query(DatabaseJob)
                .filter_by(job_id=sample_library_job.job_id)
                .first()
            )
            assert db_job.completed_at is not None

    def test_fetch_next_job(self, repository):
        """Test fetching next queued job."""
        # Add multiple jobs
        job1 = LibraryJob(
            job_id=str(uuid4()), task_type="image_resize", params={}, status="queued"
        )
        job2 = LibraryJob(
            job_id=str(uuid4()), task_type="image_conversion", params={}, status="queued"
        )

        repository.add_job(job1)
        time.sleep(0.01)  # Ensure different created_at timestamps
        repository.add_job(job2)

        # Fetch next job for image_resize
        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job is not None
        assert fetched_job.job_id == job1.job_id
        assert fetched_job.status == "processing"

    def test_fetch_next_job_atomic(self, repository):
        """Test that fetch_next_job is atomic (only one worker gets the job)."""
        job = LibraryJob(
            job_id=str(uuid4()), task_type="test", params={}, status="queued"
        )
        repository.add_job(job)

        # First fetch should succeed
        fetched1 = repository.fetch_next_job(["test"])
        assert fetched1 is not None

        # Second fetch should return None (job already claimed)
        fetched2 = repository.fetch_next_job(["test"])
        assert fetched2 is None

    def test_delete_job(self, repository, sample_library_job):
        """Test deleting a job."""
        repository.add_job(sample_library_job)
        result = repository.delete_job(sample_library_job.job_id)

        assert result is True
        assert repository.get_job(sample_library_job.job_id) is None

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

        # Update job progress
        repository.update_job("test-job-id", progress=50)

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

        # Update to completed
        repository.update_job("test-job-id", status="completed", progress=100)

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
        job = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={"width": 100, "height": 100},
            status="queued",
        )
        repository.add_job(job, created_by="test_user")

        # Fetch job (simulating worker)
        fetched_job = repository.fetch_next_job(["image_resize"])
        assert fetched_job is not None
        assert fetched_job.status == "processing"

        # Update progress
        repository.update_job(job.job_id, progress=50)

        # Mark complete with output
        task_output = {"processed_files": ["/path/to/output.jpg"]}
        repository.update_job(
            job.job_id, status="completed", progress=100, task_output=task_output
        )

        # Verify final state
        final_job = repository.get_job(job.job_id)
        assert final_job.status == "completed"
        assert final_job.progress == 100
        assert final_job.task_output["processed_files"] == ["/path/to/output.jpg"]
