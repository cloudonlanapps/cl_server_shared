"""Shared test fixtures for cl_server_shared tests."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
from cl_ml_tools import JobRecord, JobStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from cl_server_shared import JobRepositoryService, JobStorageService
from cl_server_shared.models import Base

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Engine


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command line options and ini values."""
    parser.addini(
        "test_storage_base_dir",
        help="Base directory for test storage",
        default="/tmp/cl_server_test",
    )


@pytest.fixture
def in_memory_engine() -> Generator[Engine, None, None]:
    """Create SQLite in-memory engine with all tables created.

    Yields:
        Engine: SQLAlchemy engine with in-memory SQLite database
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(in_memory_engine: Engine) -> sessionmaker[Session]:
    """Create session factory bound to in-memory engine.

    Args:
        in_memory_engine: SQLAlchemy engine fixture

    Returns:
        sessionmaker: Factory for creating database sessions
    """
    return sessionmaker(bind=in_memory_engine)


@pytest.fixture
def job_repository(session_factory: sessionmaker[Session]) -> JobRepositoryService:
    """Create JobRepositoryService with real MQTT broadcaster.

    Note: Tests will fail if MQTT broker is not running.

    Args:
        session_factory: Session factory fixture

    Returns:
        JobRepositoryService: Repository instance
    """
    return JobRepositoryService(session_factory)


@pytest.fixture
def job_storage(request: pytest.FixtureRequest) -> Generator[JobStorageService, None, None]:
    """Create JobStorageService with test storage directory.

    Priority:
    1. TEST_STORAGE_BASE_DIR environment variable
    2. test_storage_base_dir from pytest config
    3. Default from pytest_addoption

    Yields:
        JobStorageService: Storage service instance

    Note:
        Cleans up test artifacts after test completion.
    """
    # Try environment variable first
    base_dir: str | None = os.getenv("TEST_STORAGE_BASE_DIR")
    if not base_dir:
        # Get from pytest config
        base_dir = cast(str, request.config.getini("test_storage_base_dir"))

    storage = JobStorageService(base_dir=base_dir)

    yield storage

    # Cleanup test artifacts
    storage_path = Path(base_dir)
    if storage_path.exists():
        shutil.rmtree(storage_path)


@pytest.fixture
def sample_job_record() -> JobRecord:
    """Create sample JobRecord for testing.

    Returns:
        JobRecord: Sample job with test data
    """
    return JobRecord(
        job_id=str(uuid4()),
        task_type="test_task",
        params={"key": "value"},
        status=JobStatus.queued,
        progress=0,
    )
