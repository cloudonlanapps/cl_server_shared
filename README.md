# cl-server-shared

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Shared utilities for CL Server services - database models, file storage, configuration, and job repository.

## Features

- **Models** - Shared Job and QueueEntry models for distributed job processing
- **Job Repository** - `JobRepositoryService` implementing `cl_ml_tools.JobRepository` protocol
- **File Storage** - `JobStorageService` implementing `cl_ml_tools.JobStorage` protocol
- **Configuration** - Unified `Config` class with environment variable support
- **MQTT Integration** - Built-in broadcaster for job lifecycle events
- **Comprehensive Tests** - 56 tests with 95% code coverage

## Installation

Using `uv` (recommended):
```bash
uv add cl-server-shared

# With development dependencies
uv add --dev cl-server-shared
```

Using `pip`:
```bash
pip install cl-server-shared

# All extras
pip install cl-server-shared[all]
```

## Quick Start

### Configuration

```python
from cl_server_shared import Config

# Access configuration as class variables
print(Config.CL_SERVER_DIR)
print(Config.STORE_DATABASE_URL)
print(Config.MQTT_PORT)
```

### Database and Job Repository

```python
from cl_server_shared import JobRepositoryService, Config
from cl_server_shared.models import Base
from cl_ml_tools import JobRecord, JobStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from uuid import uuid4

# Create engine
engine = create_engine("sqlite:///:memory:")
Base.metadata.create_all(engine)

# Create session factory
session_factory = sessionmaker(bind=engine)

# Create repository
repository = JobRepositoryService(session_factory)

# Add a job
job = JobRecord(
    job_id=str(uuid4()),
    task_type="image_resize",
    params={"width": 800, "height": 600},
    status=JobStatus.queued,
    progress=0
)
repository.add_job(job, created_by="user123", priority=5)

# Worker: Fetch next job (atomically claims job)
next_job = repository.fetch_next_job(["image_resize"])
if next_job:
    # Update progress
    from cl_ml_tools import JobRecordUpdate
    repository.update_job(
        next_job.job_id,
        JobRecordUpdate(status=JobStatus.processing, progress=50)
    )

    # Mark completed
    repository.update_job(
        next_job.job_id,
        JobRecordUpdate(
            status=JobStatus.completed,
            progress=100,
            output={"result": "success"}
        )
    )
```

### File Storage

```python
from cl_server_shared import JobStorageService
from uuid import uuid4

# Create file storage (implements cl_ml_tools.JobStorage protocol)
storage = JobStorageService("/path/to/storage")

# Create job directory
job_id = str(uuid4())
storage.create_directory(job_id)

# Save file (async)
content = b"Hello, World!"
result = await storage.save(job_id, "input/test.txt", content)
# Returns SavedJobFile with: relative_path, size, hash

# Allocate path for writing
output_path = storage.allocate_path(job_id, "output/result.txt", mkdirs=True)
output_path.write_text("Processing complete")

# Resolve paths
input_dir = storage.resolve_path(job_id, "input")  # Absolute path
job_dir = storage.resolve_path(job_id)  # Job root directory

# Open file for reading (async)
async with await storage.open(job_id, "input/test.txt") as f:
    content = await f.read()

# Cleanup
storage.remove(job_id)
```

## API Reference

### JobRepositoryService

Implements `cl_ml_tools.JobRepository` protocol with SQLAlchemy backend.

**Constructor:**
```python
JobRepositoryService(session_factory: sessionmaker[Session])
```

**Key Methods:**
- `add_job(job: JobRecord, created_by: str | None = None, priority: int | None = None) -> bool`
- `get_job(job_id: str) -> JobRecord | None`
- `update_job(job_id: str, updates: JobRecordUpdate) -> bool`
- `fetch_next_job(task_types: Sequence[str]) -> JobRecord | None`
- `delete_job(job_id: str) -> bool`

**Features:**
- Converts between Pydantic `JobRecord` and SQLAlchemy `Job` model
- JSON serialization for params and output
- Automatic timestamp management (created_at, started_at, completed_at)
- Retry logic fields (retry_count, max_retries)
- Optimistic locking for atomic job claiming
- Real-time MQTT broadcasting of job events

**Example:**
```python
from cl_server_shared import JobRepositoryService
from cl_ml_tools import JobRecord, JobRecordUpdate, JobStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Setup
engine = create_engine("sqlite:///jobs.db")
session_factory = sessionmaker(bind=engine)
repository = JobRepositoryService(session_factory)

# Add job
job = JobRecord(
    job_id="job-123",
    task_type="image_resize",
    params={"width": 100, "height": 100},
    status=JobStatus.queued,
    progress=0
)
repository.add_job(job, created_by="user123", priority=5)

# Fetch and process (worker)
next_job = repository.fetch_next_job(["image_resize"])
if next_job:
    # Job is now in "processing" state
    update = JobRecordUpdate(progress=50)
    repository.update_job(next_job.job_id, update)

    # Complete
    update = JobRecordUpdate(
        status=JobStatus.completed,
        progress=100,
        output={"files": ["output.jpg"]}
    )
    repository.update_job(next_job.job_id, update)
```

### JobStorageService

Implements `cl_ml_tools.JobStorage` protocol for job file management.

**Constructor:**
```python
JobStorageService(base_dir: str | None = None)
# If base_dir is None, uses Config.MEDIA_STORAGE_DIR
```

**Key Methods:**
- `create_directory(job_id: str) -> None` - Create job workspace
- `remove(job_id: str) -> bool` - Remove job directory
- `save(job_id: str, relative_path: str, file: FileLike, *, mkdirs: bool = True) -> SavedJobFile` (async)
- `allocate_path(job_id: str, relative_path: str, *, mkdirs: bool = True) -> Path`
- `open(job_id: str, relative_path: str) -> AsyncFileLike` (async)
- `resolve_path(job_id: str, relative_path: str | None = None) -> Path`

**Features:**
- Creates organized job workspaces: `jobs/{job_id}/input/` and `jobs/{job_id}/output/`
- SHA256 hash calculation for all saved files
- Supports bytes, file paths, Path objects, and async file streams
- Chunked reading for large files (1MB chunks)
- **Path Guarantee**: All returned paths have their parent directories created

**Example:**
```python
from cl_server_shared import JobStorageService

storage = JobStorageService("/path/to/storage")

# Create workspace
job_id = "job-123"
storage.create_directory(job_id)

# Save different file types
# 1. Bytes
result = await storage.save(job_id, "input/data.bin", b"binary data")

# 2. From file path
result = await storage.save(job_id, "input/image.jpg", "/tmp/source.jpg")

# 3. From async stream
async with aiofiles.open("large_file.dat", "rb") as f:
    result = await storage.save(job_id, "input/large.dat", f)

# Allocate path for libraries that need filenames
output_path = storage.allocate_path(job_id, "output/result.png", mkdirs=True)
# Now use output_path with PIL, OpenCV, etc.

# Read files
async with await storage.open(job_id, "input/data.bin") as f:
    content = await f.read()

# Get absolute paths
input_dir = storage.resolve_path(job_id, "input")
job_dir = storage.resolve_path(job_id)

# Cleanup
storage.remove(job_id)
```

### Configuration

**Config Class** - Centralized configuration accessed as class variables:

| Config Variable | Description | Default |
|----------------|-------------|---------|
| `CL_SERVER_DIR` | Base directory (required env var) | - |
| `STORE_DATABASE_URL` | Store/Worker database | `sqlite:///{CL_SERVER_DIR}/media_store.db` |
| `AUTH_DATABASE_URL` | Auth service database | `sqlite:///{CL_SERVER_DIR}/user_auth.db` |
| `MEDIA_STORAGE_DIR` | Media file storage | `{CL_SERVER_DIR}/media` |
| `COMPUTE_STORAGE_DIR` | Compute workspace | `{CL_SERVER_DIR}/compute` |
| `MQTT_BROKER` | MQTT broker hostname | `localhost` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_TOPIC` | Event topic | `inference/events` |
| `BROADCAST_TYPE` | Broadcaster type | `mqtt` |
| `LOG_LEVEL` | Logging level | `INFO` |

**Example:**
```python
from cl_server_shared import Config

# Access configuration
db_url = Config.STORE_DATABASE_URL
storage_dir = Config.MEDIA_STORAGE_DIR
mqtt_port = Config.MQTT_PORT
```

### Models

**Job** (SQLAlchemy model) - Database representation:
- `job_id: str` - Unique identifier (indexed)
- `task_type: str` - Task identifier
- `params: dict` - JSON parameters
- `status: str` - Job state (queued/processing/completed/error)
- `progress: int` - Progress percentage (0-100)
- `output: dict | None` - JSON results
- `error_message: str | None` - Error details
- `created_at: int` - Creation timestamp (milliseconds)
- `started_at: int | None` - Start timestamp
- `completed_at: int | None` - Completion timestamp
- `retry_count: int` - Current retry count
- `max_retries: int` - Maximum retries (default: 3)
- `created_by: str | None` - User attribution
- `priority: int` - Job priority

**JobRecord** (Pydantic model from cl_ml_tools) - Protocol interface:
- `job_id: str`
- `task_type: str`
- `params: dict`
- `status: JobStatus` (enum)
- `progress: int`
- `output: dict | None`
- `error_message: str | None`

## Architecture

### Service Architecture

Multi-service distributed architecture:

1. **Store Service** - Job orchestration
   - Creates jobs in shared database
   - Manages file uploads
   - Publishes MQTT job events

2. **Worker Service** - Distributed processing
   - Shares database with store service
   - Claims jobs atomically via `fetch_next_job()`
   - Processes jobs and updates progress
   - Updates MQTT on status changes

3. **Auth Service** (optional)
   - Separate database for user management
   - JWT-based authentication

### Database Sharing

Store and Worker services share the same database (`media_store.db`):
- **Store**: Creates jobs, reads results
- **Worker**: Claims jobs, updates status/progress
- **Concurrency**: SQLite WAL mode for concurrent access

### Package Structure

```
src/cl_server_shared/
├── __init__.py           # Public API: Config, JobRepositoryService, JobStorageService
├── config.py             # Config class
├── job_storage.py        # JobStorageService (implements JobStorage)
├── shared_db.py          # JobRepositoryService (implements JobRepository)
├── job_translator.py     # JobRecord ↔ Job conversion
└── models/
    ├── __init__.py       # Base, Job, QueueEntry
    ├── base.py           # SQLAlchemy Base
    ├── job.py            # Job model
    └── queue.py          # QueueEntry model
```

### Public API

```python
from cl_server_shared import (
    Config,                # Configuration singleton
    JobRepositoryService,  # Job repository
    JobStorageService,     # File storage
)

from cl_server_shared.models import (
    Base,                  # SQLAlchemy base
    Job,                   # Job model
    QueueEntry,            # Queue model
)
```

## Testing

The library includes comprehensive tests with 95% code coverage.

### Running Tests

Using `uv` (recommended):
```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/cl_server_shared --cov-report=term-missing

# Type checking
uv run basedpyright tests/
```

Using `pip`:
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Coverage
pytest tests/ --cov=src/cl_server_shared --cov-report=term-missing
```

### Test Configuration

Configure test storage directory in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
test_storage_base_dir = "/tmp/cl_server_test"
```

Or via environment variable:
```bash
export TEST_STORAGE_BASE_DIR=/tmp/my_test_dir
```

### Test Coverage

- **JobRepositoryService**: 30 tests covering CRUD, job claiming, MQTT broadcasting, data integrity
- **JobStorageService**: 26 tests covering directory ops, async file I/O, path operations, hash calculation
- **Total**: 56 tests, 95% code coverage

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CL_SERVER_DIR` | **Yes** | Base directory (must exist and be writable) |
| `DATABASE_URL` | No | Override default database URL |
| `MEDIA_STORAGE_DIR` | No | Override media storage location |
| `COMPUTE_STORAGE_DIR` | No | Override compute workspace |
| `MQTT_BROKER` | No | MQTT broker hostname (default: localhost) |
| `MQTT_PORT` | No | MQTT port (default: 1883) |
| `MQTT_TOPIC` | No | Event topic (default: inference/events) |
| `BROADCAST_TYPE` | No | "mqtt" or other (default: mqtt) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `WORKER_ID` | No | Worker identifier |
| `WORKER_SUPPORTED_TASKS` | No | Comma-separated task types |
| `WORKER_POLL_INTERVAL` | No | Poll interval seconds (default: 5) |

Auth-specific:
- `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` - ES256 JWT keys
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` - Admin credentials
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiry (default: 30)

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/cloudonlanapps/cl_ml_tools.git
cd cl-server-shared

# Install with uv
uv sync --all-extras

# Or with pip
pip install -e ".[dev]"
```

### Code Quality

```bash
# Run tests
uv run pytest tests/ -v

# Type checking
uv run basedpyright src/ tests/

# Linting and formatting
uv run ruff check src/
uv run ruff format src/
```

### Requirements

- Python 3.12+
- SQLAlchemy 2.0+
- Pydantic 2.0+
- aiofiles 25.0+
- cl_ml_tools (from GitHub)

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure tests pass: `uv run pytest tests/ -v`
5. Check types: `uv run basedpyright src/ tests/`
6. Format code: `uv run ruff format src/`
7. Submit a pull request

## Links

- **Repository**: https://github.com/cloudonlanapps/cl_ml_tools
- **cl_ml_tools**: https://github.com/cloudonlanapps/cl_ml_tools
- **Issues**: https://github.com/cloudonlanapps/cl_ml_tools/issues
