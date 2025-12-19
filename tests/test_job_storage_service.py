"""Tests for JobStorageService."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest

from cl_server_shared import JobStorageService

if TYPE_CHECKING:
    from cl_ml_tools import SavedJobFile


# ============================================================================
# Directory Operations Tests
# ============================================================================


def test_create_directory(job_storage: JobStorageService) -> None:
    """Test creating job directory structure."""
    job_id = str(uuid4())

    job_storage.create_directory(job_id)

    # Verify directory structure
    job_dir = job_storage.resolve_path(job_id)
    assert job_dir.exists()
    assert job_dir.is_dir()

    input_dir = job_dir / "input"
    assert input_dir.exists()
    assert input_dir.is_dir()

    output_dir = job_dir / "output"
    assert output_dir.exists()
    assert output_dir.is_dir()


def test_create_directory_idempotent(job_storage: JobStorageService) -> None:
    """Test that creating directory multiple times doesn't error."""
    job_id = str(uuid4())

    # Create twice
    job_storage.create_directory(job_id)
    job_storage.create_directory(job_id)

    # Should still exist
    job_dir = job_storage.resolve_path(job_id)
    assert job_dir.exists()


def test_remove_job(job_storage: JobStorageService) -> None:
    """Test removing job directory."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Create a test file in the directory
    job_dir = job_storage.resolve_path(job_id)
    test_file = job_dir / "input" / "test.txt"
    _ = test_file.write_text("test content")

    # Remove job
    result = job_storage.remove(job_id)

    assert result is True
    assert not job_dir.exists()


def test_remove_job_not_exists(job_storage: JobStorageService) -> None:
    """Test removing non-existent job returns False."""
    job_id = str(uuid4())

    result = job_storage.remove(job_id)

    assert result is False


# ============================================================================
# File Saving (async) Tests
# ============================================================================


async def test_save_bytes(job_storage: JobStorageService) -> None:
    """Test saving bytes data."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Hello, World!"
    relative_path = "input/test.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, content)

    assert result.relative_path == relative_path
    assert result.size == len(content)

    # Verify hash
    expected_hash = hashlib.sha256(content).hexdigest()
    assert result.hash == expected_hash

    # Verify file exists and content is correct
    file_path = job_storage.resolve_path(job_id, relative_path)
    assert file_path.exists()
    assert file_path.read_bytes() == content


async def test_save_from_path(job_storage: JobStorageService, tmp_path: Path) -> None:
    """Test saving from existing file path."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Create source file
    source_file = tmp_path / "source.txt"
    content = b"Test file content"
    _ = source_file.write_bytes(content)

    relative_path = "input/copied.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, str(source_file))

    assert result.relative_path == relative_path
    assert result.size == len(content)

    # Verify file was copied
    dest_path = job_storage.resolve_path(job_id, relative_path)
    assert dest_path.exists()
    assert dest_path.read_bytes() == content


async def test_save_from_pathlike(job_storage: JobStorageService, tmp_path: Path) -> None:
    """Test saving from Path object."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Create source file
    source_file = tmp_path / "source.txt"
    content = b"Path object test"
    _ = source_file.write_bytes(content)

    relative_path = "input/from_path.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, source_file)

    assert result.relative_path == relative_path
    assert result.size == len(content)

    # Verify file was copied
    dest_path = job_storage.resolve_path(job_id, relative_path)
    assert dest_path.exists()
    assert dest_path.read_bytes() == content


async def test_save_async_file(job_storage: JobStorageService) -> None:
    """Test saving from async file-like object."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Async file content"

    # Create async file-like object
    class AsyncBytesIO:
        data: bytes
        pos: int

        def __init__(self, data: bytes):
            self.data = data
            self.pos = 0

        async def read(self, size: int = -1) -> bytes:
            if size == -1:
                result = self.data[self.pos :]
                self.pos = len(self.data)
                return result
            result = self.data[self.pos : self.pos + size]
            self.pos += len(result)
            return result

    async_file = AsyncBytesIO(content)
    relative_path = "input/async.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, async_file)

    assert result.relative_path == relative_path
    assert result.size == len(content)

    # Verify file exists and content is correct
    dest_path = job_storage.resolve_path(job_id, relative_path)
    assert dest_path.exists()
    assert dest_path.read_bytes() == content


async def test_save_with_mkdirs(job_storage: JobStorageService) -> None:
    """Test saving with mkdirs=True creates parent directories."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Test content"
    relative_path = "input/subdir/nested/file.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, content, mkdirs=True)

    assert result.relative_path == relative_path

    # Verify parent directories were created
    file_path = job_storage.resolve_path(job_id, relative_path)
    assert file_path.exists()
    assert file_path.parent.exists()


async def test_save_without_mkdirs(job_storage: JobStorageService) -> None:
    """Test saving with mkdirs=False."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Test content"
    relative_path = "input/file.txt"

    # Should work for existing directory
    result: SavedJobFile = await job_storage.save(job_id, relative_path, content, mkdirs=False)

    assert result.relative_path == relative_path
    file_path = job_storage.resolve_path(job_id, relative_path)
    assert file_path.exists()


async def test_save_nested_path(job_storage: JobStorageService) -> None:
    """Test saving to nested relative paths."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Nested file"
    relative_path = "input/subdir/deep/file.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, content)

    assert result.relative_path == relative_path

    # Verify file exists in nested location
    file_path = job_storage.resolve_path(job_id, relative_path)
    assert file_path.exists()
    assert file_path.read_bytes() == content


async def test_save_large_file(job_storage: JobStorageService) -> None:
    """Test chunked reading for large files."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Create large content (2MB)
    large_content = b"x" * (2 * 1024 * 1024)

    relative_path = "input/large.bin"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, large_content)

    assert result.relative_path == relative_path
    assert result.size == len(large_content)

    # Verify hash
    expected_hash = hashlib.sha256(large_content).hexdigest()
    assert result.hash == expected_hash


# ============================================================================
# Path Operations Tests
# ============================================================================


def test_allocate_path(job_storage: JobStorageService) -> None:
    """Test allocating a path for writing."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    relative_path = "output/result.txt"

    allocated_path = job_storage.allocate_path(job_id, relative_path)

    # Verify absolute Path returned
    assert isinstance(allocated_path, Path)
    assert allocated_path.is_absolute()

    # Verify correct structure
    assert str(allocated_path).endswith(f"jobs/{job_id}/{relative_path}")


def test_allocate_path_with_mkdirs(job_storage: JobStorageService) -> None:
    """Test allocate_path with mkdirs=True creates parent directories."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    relative_path = "output/subdir/result.txt"

    allocated_path = job_storage.allocate_path(job_id, relative_path, mkdirs=True)

    # Verify parent directories exist
    assert allocated_path.parent.exists()
    assert allocated_path.parent.is_dir()


def test_allocate_path_without_mkdirs(job_storage: JobStorageService) -> None:
    """Test allocate_path with mkdirs=False."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    relative_path = "output/result.txt"

    allocated_path = job_storage.allocate_path(job_id, relative_path, mkdirs=False)

    # Path should be returned
    assert isinstance(allocated_path, Path)


def test_resolve_path_job_only(job_storage: JobStorageService) -> None:
    """Test resolving job directory path."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    resolved = job_storage.resolve_path(job_id)

    assert isinstance(resolved, Path)
    assert resolved.is_absolute()
    assert resolved.exists()
    assert str(resolved).endswith(f"jobs/{job_id}")


def test_resolve_path_with_relative(job_storage: JobStorageService) -> None:
    """Test resolving full file path."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    relative_path = "input/test.txt"

    resolved = job_storage.resolve_path(job_id, relative_path)

    assert isinstance(resolved, Path)
    assert resolved.is_absolute()
    assert str(resolved).endswith(f"jobs/{job_id}/{relative_path}")


def test_resolve_path_returns_absolute(job_storage: JobStorageService) -> None:
    """Test that resolve_path always returns absolute paths."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Test with None
    path1 = job_storage.resolve_path(job_id, None)
    assert path1.is_absolute()

    # Test with relative path
    path2 = job_storage.resolve_path(job_id, "input/file.txt")
    assert path2.is_absolute()


# ============================================================================
# File Reading (async) Tests
# ============================================================================


async def test_open_file(job_storage: JobStorageService) -> None:
    """Test opening a stored file for reading."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Save file first
    content = b"Test content to read"
    relative_path = "input/test.txt"
    _ = await job_storage.save(job_id, relative_path, content)

    # Open and read - job_storage.open returns an aiofiles file object
    import aiofiles

    file_path = job_storage.resolve_path(job_id, relative_path)
    async with aiofiles.open(file_path, "rb") as async_file:
        read_content = await async_file.read()

    assert read_content == content


async def test_open_file_not_exists(job_storage: JobStorageService) -> None:
    """Test opening non-existent file raises error."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    with pytest.raises(FileNotFoundError):
        _ = await job_storage.open(job_id, "input/nonexistent.txt")


# ============================================================================
# Hash Calculation Tests
# ============================================================================


async def test_hash_calculation_bytes(job_storage: JobStorageService) -> None:
    """Test SHA256 hash calculation for bytes."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Hash me!"
    relative_path = "input/hash_test.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, content)

    # Verify hash matches expected
    expected_hash = hashlib.sha256(content).hexdigest()
    assert result.hash == expected_hash


async def test_hash_calculation_file(job_storage: JobStorageService, tmp_path: Path) -> None:
    """Test SHA256 hash calculation for file copy."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    # Create source file
    content = b"File content for hashing"
    source_file = tmp_path / "source.txt"
    _ = source_file.write_bytes(content)

    relative_path = "input/copied_hash.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, str(source_file))

    # Verify hash
    expected_hash = hashlib.sha256(content).hexdigest()
    assert result.hash == expected_hash


async def test_hash_calculation_async(job_storage: JobStorageService) -> None:
    """Test SHA256 hash calculation for async stream."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"Async stream content"

    # Create async file-like object
    class AsyncBytesIO:
        data: bytes
        pos: int

        def __init__(self, data: bytes):
            self.data = data
            self.pos = 0

        async def read(self, size: int = -1) -> bytes:
            if size == -1:
                result = self.data[self.pos :]
                self.pos = len(self.data)
                return result
            result = self.data[self.pos : self.pos + size]
            self.pos += len(result)
            return result

    async_file = AsyncBytesIO(content)
    relative_path = "input/async_hash.txt"

    result: SavedJobFile = await job_storage.save(job_id, relative_path, async_file)

    # Verify hash
    expected_hash = hashlib.sha256(content).hexdigest()
    assert result.hash == expected_hash


# ============================================================================
# Path Guarantee Tests
# ============================================================================


def test_create_directory_guarantees_paths_exist(job_storage: JobStorageService) -> None:
    """Test that create_directory guarantees all paths exist."""
    job_id = str(uuid4())

    job_storage.create_directory(job_id)

    # All paths returned by resolve_path should exist
    job_dir = job_storage.resolve_path(job_id)
    assert job_dir.exists(), "Job directory must exist after create_directory"

    input_dir = job_storage.resolve_path(job_id, "input")
    assert input_dir.exists(), "Input directory must exist after create_directory"

    output_dir = job_storage.resolve_path(job_id, "output")
    assert output_dir.exists(), "Output directory must exist after create_directory"


async def test_save_guarantees_parent_exists(job_storage: JobStorageService) -> None:
    """Test that save with mkdirs=True guarantees parent directories exist."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    content = b"test"
    relative_path = "input/a/b/c/file.txt"

    _ = await job_storage.save(job_id, relative_path, content, mkdirs=True)

    # Parent must exist
    file_path = job_storage.resolve_path(job_id, relative_path)
    assert file_path.parent.exists(), "Parent directory must exist after save with mkdirs=True"


def test_allocate_path_guarantees_parent_exists(job_storage: JobStorageService) -> None:
    """Test that allocate_path with mkdirs=True guarantees parent exists."""
    job_id = str(uuid4())
    job_storage.create_directory(job_id)

    relative_path = "output/nested/deep/file.txt"

    allocated = job_storage.allocate_path(job_id, relative_path, mkdirs=True)

    # Parent must exist
    assert allocated.parent.exists(), "Parent directory must exist after allocate_path with mkdirs=True"
