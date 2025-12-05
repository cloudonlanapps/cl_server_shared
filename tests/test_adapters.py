"""Unit tests for adapter implementations.

Tests SQLAlchemyJobRepository and FileStorageAdapter classes that bridge
cl_media_tools library protocols with application implementations.
"""

import json
import tempfile
import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Library schemas
from cl_media_tools.common.schemas import Job as LibraryJob

# Application models and adapters
from cl_server_shared.models.job import Job as DatabaseJob
from cl_server_shared.database import Base
from cl_server_shared.adapters import SQLAlchemyJobRepository, FileStorageAdapter
from cl_server_shared.file_storage import FileStorageService


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

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Cleanup
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
def temp_storage_dir():
    """Create temporary directory for file storage testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def file_storage_service(temp_storage_dir):
    """Create FileStorageService instance for testing."""
    return FileStorageService(base_dir=str(temp_storage_dir))


@pytest.fixture
def file_storage_adapter(file_storage_service):
    """Create FileStorageAdapter instance for testing."""
    return FileStorageAdapter(file_storage_service)


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
            "height": 600
        },
        status="queued",
        progress=0
    )


# ============================================================================
# SQLAlchemyJobRepository Tests
# ============================================================================

class TestSQLAlchemyJobRepository:
    """Test suite for SQLAlchemyJobRepository adapter."""

    def test_add_job(self, repository, sample_library_job):
        """Test adding a job to the database."""
        job_id = repository.add_job(
            sample_library_job,
            created_by="test_user",
            priority=5
        )

        assert job_id == sample_library_job.job_id

        # Verify job was saved to database
        retrieved_job = repository.get_job(job_id)
        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_library_job.job_id
        assert retrieved_job.task_type == sample_library_job.task_type
        assert retrieved_job.params == sample_library_job.params
        assert retrieved_job.status == "queued"
        assert retrieved_job.progress == 0

    def test_add_job_with_database_fields(self, repository, session_factory, sample_library_job):
        """Test that add_job adds database-specific fields correctly."""
        repository.add_job(sample_library_job, created_by="user123")

        # Check database directly
        with session_factory() as session:
            db_job = session.query(DatabaseJob).filter_by(
                job_id=sample_library_job.job_id
            ).first()

            assert db_job is not None
            assert db_job.created_at is not None
            assert db_job.created_at > 0
            assert db_job.created_by == "user123"
            assert db_job.retry_count == 0
            assert db_job.max_retries == 3
            assert db_job.started_at is None
            assert db_job.completed_at is None

    def test_add_job_serializes_params(self, repository, session_factory, sample_library_job):
        """Test that params dict is serialized to JSON string."""
        repository.add_job(sample_library_job)

        # Check database directly
        with session_factory() as session:
            db_job = session.query(DatabaseJob).filter_by(
                job_id=sample_library_job.job_id
            ).first()

            # params should be JSON string in database
            assert isinstance(db_job.params, str)
            # Should be parseable as JSON
            params = json.loads(db_job.params)
            assert params == sample_library_job.params

    def test_get_job(self, repository, sample_library_job):
        """Test retrieving a job by ID."""
        repository.add_job(sample_library_job)

        retrieved_job = repository.get_job(sample_library_job.job_id)

        assert retrieved_job is not None
        assert retrieved_job.job_id == sample_library_job.job_id
        assert retrieved_job.task_type == sample_library_job.task_type
        assert retrieved_job.params == sample_library_job.params

    def test_get_job_nonexistent(self, repository):
        """Test getting a job that doesn't exist returns None."""
        result = repository.get_job("nonexistent-job-id")
        assert result is None

    def test_get_job_deserializes_params(self, repository, sample_library_job):
        """Test that params JSON string is deserialized to dict."""
        repository.add_job(sample_library_job)

        retrieved_job = repository.get_job(sample_library_job.job_id)

        # params should be dict in library Job
        assert isinstance(retrieved_job.params, dict)
        assert retrieved_job.params["width"] == 800
        assert retrieved_job.params["height"] == 600

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

    def test_update_job_task_output(self, repository, sample_library_job):
        """Test updating job task_output."""
        repository.add_job(sample_library_job)

        task_output = {
            "processed_files": ["/tmp/output.jpg"],
            "dimensions": {"width": 800, "height": 600}
        }
        repository.update_job(sample_library_job.job_id, task_output=task_output)

        updated_job = repository.get_job(sample_library_job.job_id)
        assert updated_job.task_output == task_output
        assert updated_job.task_output["processed_files"] == ["/tmp/output.jpg"]

    def test_update_job_error_message(self, repository, sample_library_job):
        """Test updating job error message."""
        repository.add_job(sample_library_job)

        error_msg = "Failed to process image: File not found"
        repository.update_job(sample_library_job.job_id, error_message=error_msg)

        updated_job = repository.get_job(sample_library_job.job_id)
        assert updated_job.error_message == error_msg

    def test_update_job_sets_started_at(self, repository, session_factory, sample_library_job):
        """Test that updating status to 'processing' sets started_at timestamp."""
        repository.add_job(sample_library_job)

        repository.update_job(sample_library_job.job_id, status="processing")

        # Check database directly
        with session_factory() as session:
            db_job = session.query(DatabaseJob).filter_by(
                job_id=sample_library_job.job_id
            ).first()

            assert db_job.started_at is not None
            assert db_job.started_at > 0

    def test_update_job_sets_completed_at(self, repository, session_factory, sample_library_job):
        """Test that updating status to 'completed' sets completed_at timestamp."""
        repository.add_job(sample_library_job)

        repository.update_job(sample_library_job.job_id, status="completed")

        # Check database directly
        with session_factory() as session:
            db_job = session.query(DatabaseJob).filter_by(
                job_id=sample_library_job.job_id
            ).first()

            assert db_job.completed_at is not None
            assert db_job.completed_at > 0

    def test_update_job_sets_completed_at_on_error(self, repository, session_factory, sample_library_job):
        """Test that updating status to 'error' sets completed_at timestamp."""
        repository.add_job(sample_library_job)

        repository.update_job(sample_library_job.job_id, status="error")

        # Check database directly
        with session_factory() as session:
            db_job = session.query(DatabaseJob).filter_by(
                job_id=sample_library_job.job_id
            ).first()

            assert db_job.completed_at is not None
            assert db_job.completed_at > 0

    def test_update_job_nonexistent(self, repository):
        """Test updating a nonexistent job returns False."""
        result = repository.update_job("nonexistent-job-id", status="processing")
        assert result is False

    def test_fetch_next_job(self, repository, sample_library_job):
        """Test fetching the next queued job."""
        repository.add_job(sample_library_job)

        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job is not None
        assert fetched_job.job_id == sample_library_job.job_id
        assert fetched_job.status == "processing"  # Status should be updated

    def test_fetch_next_job_filters_by_task_type(self, repository):
        """Test that fetch_next_job only returns jobs matching task types."""
        # Add job with different task type
        job1 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_conversion",
            params={},
            status="queued"
        )
        repository.add_job(job1)

        # Try to fetch with different task type
        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job is None

    def test_fetch_next_job_multiple_task_types(self, repository):
        """Test fetching job when multiple task types are specified."""
        job1 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_conversion",
            params={},
            status="queued"
        )
        repository.add_job(job1)

        # Fetch with multiple task types
        fetched_job = repository.fetch_next_job(["image_resize", "image_conversion"])

        assert fetched_job is not None
        assert fetched_job.task_type == "image_conversion"

    def test_fetch_next_job_ignores_processing(self, repository):
        """Test that fetch_next_job ignores jobs already processing."""
        job1 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={},
            status="processing"
        )
        repository.add_job(job1)
        # Manually set status to processing
        repository.update_job(job1.job_id, status="processing")

        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job is None

    def test_fetch_next_job_oldest_first(self, repository):
        """Test that fetch_next_job returns oldest job first."""
        # Add multiple jobs with different timestamps
        job1 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={},
            status="queued"
        )
        repository.add_job(job1)

        # Wait a bit to ensure different timestamp
        time.sleep(0.01)

        job2 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={},
            status="queued"
        )
        repository.add_job(job2)

        # Fetch should return job1 (oldest)
        fetched_job = repository.fetch_next_job(["image_resize"])

        assert fetched_job.job_id == job1.job_id

    def test_fetch_next_job_empty_task_types(self, repository, sample_library_job):
        """Test that fetch_next_job with empty task types returns None."""
        repository.add_job(sample_library_job)

        fetched_job = repository.fetch_next_job([])

        assert fetched_job is None

    def test_fetch_next_job_atomicity(self, repository):
        """Test that fetch_next_job is atomic (optimistic locking works)."""
        job1 = LibraryJob(
            job_id=str(uuid4()),
            task_type="image_resize",
            params={},
            status="queued"
        )
        repository.add_job(job1)

        # Fetch job twice - second fetch should return None
        first_fetch = repository.fetch_next_job(["image_resize"])
        second_fetch = repository.fetch_next_job(["image_resize"])

        assert first_fetch is not None
        assert first_fetch.job_id == job1.job_id
        assert second_fetch is None  # Already claimed

    def test_delete_job(self, repository, sample_library_job):
        """Test deleting a job."""
        repository.add_job(sample_library_job)

        success = repository.delete_job(sample_library_job.job_id)
        assert success is True

        # Verify job was deleted
        retrieved_job = repository.get_job(sample_library_job.job_id)
        assert retrieved_job is None

    def test_delete_job_nonexistent(self, repository):
        """Test deleting a nonexistent job returns False."""
        result = repository.delete_job("nonexistent-job-id")
        assert result is False


# ============================================================================
# FileStorageAdapter Tests
# ============================================================================

class TestFileStorageAdapter:
    """Test suite for FileStorageAdapter."""

    def test_create_job_directory(self, file_storage_adapter, temp_storage_dir):
        """Test creating job directory structure."""
        job_id = str(uuid4())

        job_dir = file_storage_adapter.create_job_directory(job_id)

        assert job_dir.exists()
        assert job_dir.is_dir()
        assert (job_dir / "input").exists()
        assert (job_dir / "output").exists()

    def test_get_input_path(self, file_storage_adapter):
        """Test getting input directory path."""
        job_id = str(uuid4())
        file_storage_adapter.create_job_directory(job_id)

        input_path = file_storage_adapter.get_input_path(job_id)

        assert input_path.exists()
        assert input_path.is_dir()
        assert input_path.name == "input"

    def test_get_output_path(self, file_storage_adapter):
        """Test getting output directory path."""
        job_id = str(uuid4())
        file_storage_adapter.create_job_directory(job_id)

        output_path = file_storage_adapter.get_output_path(job_id)

        assert output_path.exists()
        assert output_path.is_dir()
        assert output_path.name == "output"

    @pytest.mark.asyncio
    async def test_save_input_file(self, file_storage_adapter):
        """Test saving input file."""
        from io import BytesIO
        from fastapi import UploadFile

        job_id = str(uuid4())
        file_storage_adapter.create_job_directory(job_id)

        # Create mock UploadFile
        file_content = b"Test file content"
        file = UploadFile(
            filename="test.txt",
            file=BytesIO(file_content)
        )

        result = await file_storage_adapter.save_input_file(job_id, "test.txt", file)

        assert "filename" in result
        assert result["filename"] == "test.txt"
        assert "path" in result
        assert "size" in result
        assert result["size"] == len(file_content)
        assert "hash" in result

        # Verify path is absolute
        path = Path(result["path"])
        assert path.is_absolute()

        # Verify file exists
        assert path.exists()
        assert path.read_bytes() == file_content

    def test_cleanup_job(self, file_storage_adapter):
        """Test cleaning up job directory."""
        job_id = str(uuid4())
        file_storage_adapter.create_job_directory(job_id)

        success = file_storage_adapter.cleanup_job(job_id)

        assert success is True

        # Verify directory was deleted
        job_dir = file_storage_adapter.service.get_job_path(job_id)
        assert not job_dir.exists()

    def test_cleanup_job_nonexistent(self, file_storage_adapter):
        """Test cleaning up nonexistent job returns False."""
        result = file_storage_adapter.cleanup_job("nonexistent-job-id")
        assert result is False


# ============================================================================
# Integration Tests
# ============================================================================

class TestAdapterIntegration:
    """Integration tests for adapters working together."""

    @pytest.mark.asyncio
    async def test_full_job_workflow(self, repository, file_storage_adapter):
        """Test complete job workflow using both adapters."""
        from io import BytesIO
        from fastapi import UploadFile

        # 1. Create job directory
        job_id = str(uuid4())
        file_storage_adapter.create_job_directory(job_id)

        # 2. Save input file
        file_content = b"Test image content"
        file = UploadFile(filename="input.jpg", file=BytesIO(file_content))
        file_info = await file_storage_adapter.save_input_file(job_id, "input.jpg", file)

        input_path = file_info["path"]
        output_path = str(file_storage_adapter.get_output_path(job_id) / "output.jpg")

        # 3. Create job
        library_job = LibraryJob(
            job_id=job_id,
            task_type="image_resize",
            params={
                "input_paths": [input_path],
                "output_paths": [output_path],
                "width": 100,
                "height": 100
            },
            status="queued"
        )
        repository.add_job(library_job, created_by="test_user")

        # 4. Fetch job (simulating worker)
        fetched_job = repository.fetch_next_job(["image_resize"])
        assert fetched_job is not None
        assert fetched_job.status == "processing"

        # 5. Update progress
        repository.update_job(job_id, progress=50)

        # 6. Mark complete with output
        task_output = {"processed_files": [output_path]}
        repository.update_job(
            job_id,
            status="completed",
            progress=100,
            task_output=task_output
        )

        # 7. Verify final state
        final_job = repository.get_job(job_id)
        assert final_job.status == "completed"
        assert final_job.progress == 100
        assert final_job.task_output["processed_files"] == [output_path]

        # 8. Cleanup
        file_storage_adapter.cleanup_job(job_id)
