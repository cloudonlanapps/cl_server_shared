"""Unit tests for FileStorageService."""

import tempfile
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import UploadFile

from cl_server_shared import FileStorageService


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for file storage testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def file_storage(temp_storage_dir):
    """Create FileStorageService instance for testing."""
    return FileStorageService(base_dir=str(temp_storage_dir))


# ============================================================================
# FileStorageService Tests
# ============================================================================


class TestFileStorageService:
    """Test suite for FileStorageService."""

    def test_create_job_directory(self, file_storage, temp_storage_dir):
        """Test creating job directory structure."""
        job_id = str(uuid4())

        file_storage.create_job_directory(job_id)

        # Verify directories were created using get_input_path and get_output_path
        input_path = file_storage.get_input_path(job_id)
        output_path = file_storage.get_output_path(job_id)

        assert input_path.exists()
        assert output_path.exists()
        assert input_path.is_dir()
        assert output_path.is_dir()

    def test_get_input_path(self, file_storage):
        """Test getting input directory path."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        input_path = file_storage.get_input_path(job_id)

        assert input_path.exists()
        assert input_path.is_dir()
        assert input_path.name == "input"
        assert input_path.is_absolute()

    def test_get_output_path(self, file_storage):
        """Test getting output directory path."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        output_path = file_storage.get_output_path(job_id)

        assert output_path.exists()
        assert output_path.is_dir()
        assert output_path.name == "output"
        assert output_path.is_absolute()

    @pytest.mark.asyncio
    async def test_save_input_file(self, file_storage):
        """Test saving input file."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        # Create mock UploadFile
        file_content = b"Test file content"
        file = UploadFile(filename="test.txt", file=BytesIO(file_content))

        result = await file_storage.save_input_file(job_id, "test.txt", file)

        # Verify result structure
        assert "filename" in result
        assert result["filename"] == "test.txt"
        assert "path" in result
        assert "size" in result
        assert result["size"] == len(file_content)
        assert "hash" in result

        # Verify path is relative (from input directory)
        assert result["path"] == "test.txt"

        # Construct absolute path using get_input_path and verify file exists
        input_dir = file_storage.get_input_path(job_id)
        absolute_path = input_dir / result["path"]
        assert absolute_path.exists()
        assert absolute_path.read_bytes() == file_content

    @pytest.mark.asyncio
    async def test_save_input_file_creates_hash(self, file_storage):
        """Test that save_input_file creates SHA256 hash."""
        import hashlib

        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        file_content = b"Test content for hashing"
        expected_hash = hashlib.sha256(file_content).hexdigest()

        file = UploadFile(filename="test.txt", file=BytesIO(file_content))
        result = await file_storage.save_input_file(job_id, "test.txt", file)

        assert result["hash"] == expected_hash

    def test_cleanup_job(self, file_storage):
        """Test cleaning up job directory."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        success = file_storage.cleanup_job(job_id)

        assert success is True

        # Verify directory was deleted
        job_dir = file_storage.get_job_path(job_id)
        assert not job_dir.exists()

    def test_cleanup_job_nonexistent(self, file_storage):
        """Test cleaning up nonexistent job returns False."""
        result = file_storage.cleanup_job("nonexistent-job-id")
        assert result is False

    def test_get_job_path(self, file_storage):
        """Test getting job path."""
        job_id = str(uuid4())
        job_path = file_storage.get_job_path(job_id)

        # Should return absolute path
        assert job_path.is_absolute()
        assert job_id in str(job_path)
        assert "jobs" in str(job_path)

    def test_file_storage_implements_protocol(self, file_storage):
        """Test that FileStorageService implements cl_ml_tools.FileStorage protocol."""
        from cl_ml_tools import FileStorage

        # Should be instance of protocol
        assert isinstance(file_storage, FileStorage)

    @pytest.mark.asyncio
    async def test_multiple_files_same_job(self, file_storage):
        """Test saving multiple files to the same job."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        # Save first file
        file1 = UploadFile(filename="file1.txt", file=BytesIO(b"Content 1"))
        result1 = await file_storage.save_input_file(job_id, "file1.txt", file1)

        # Save second file
        file2 = UploadFile(filename="file2.txt", file=BytesIO(b"Content 2"))
        result2 = await file_storage.save_input_file(job_id, "file2.txt", file2)

        # Both paths should be relative
        assert result1["path"] == "file1.txt"
        assert result2["path"] == "file2.txt"

        # Both files should exist when combined with input_path
        input_path = file_storage.get_input_path(job_id)
        assert (input_path / result1["path"]).exists()
        assert (input_path / result2["path"]).exists()

    def test_get_absolute_path(self, file_storage):
        """Test converting relative path to absolute."""
        relative_path = "store/2024/12/11/test.txt"
        absolute_path = file_storage.get_absolute_path(relative_path)

        assert Path(absolute_path).is_absolute()
        assert "test.txt" in str(absolute_path)

    @pytest.mark.asyncio
    async def test_save_input_file_with_subdirectory(self, file_storage):
        """Test saving file with subdirectory in filename."""
        job_id = str(uuid4())
        file_storage.create_job_directory(job_id)

        # Some systems might send filename with path separator
        file_content = b"Test content"
        file = UploadFile(filename="subdir/test.txt", file=BytesIO(file_content))

        result = await file_storage.save_input_file(job_id, "subdir/test.txt", file)

        # Path should be relative with subdirectory
        assert result["path"] == "subdir/test.txt"

        # File should be saved successfully when combined with input_path
        input_path = file_storage.get_input_path(job_id)
        assert (input_path / result["path"]).exists()
        assert (input_path / result["path"]).read_bytes() == file_content
