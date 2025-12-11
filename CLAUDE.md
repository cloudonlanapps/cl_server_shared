# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`cl-server-shared` is a Python library providing shared utilities for CL Server services (auth, store, worker). It's designed for distributed compute architectures where multiple services share common database models, file storage, and event broadcasting.

## Development Commands

### Testing
```bash
# Install development dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/cl_server_shared --cov-report=term-missing

# Run single test file
pytest tests/test_shared_db.py -v
pytest tests/test_file_storage.py -v
pytest tests/test_config.py -v
```

### Linting
```bash
# Format and lint with ruff (configured in pyproject.toml)
ruff check src/
ruff format src/
```

### Building
```bash
# Build package
python -m build

# Install locally for testing
pip install -e .

# Install with optional dependencies
pip install -e ".[mqtt]"      # MQTT support
pip install -e ".[fastapi]"   # FastAPI support
pip install -e ".[compute]"   # Compute/image processing
pip install -e ".[all]"       # All extras
```

## Architecture

### Service Architecture

The library is designed for a **multi-service architecture**:

1. **Auth Service** - JWT-based authentication with ES256 keys
   - Uses `Config.AUTH_DATABASE_URL` (separate database: `user_auth.db`)
   - Manages users and access tokens

2. **Store Service** - Media file management and job orchestration
   - Uses `Config.STORE_DATABASE_URL` (`media_store.db`)
   - Creates jobs, manages file storage
   - Publishes MQTT events for job lifecycle

3. **Worker Service** - Distributed compute processing
   - Uses `Config.WORKER_DATABASE_URL` (same as store: `media_store.db`)
   - Claims and processes jobs from shared database

### Database Sharing Model

**Critical**: Store service and worker share the **same database** (`media_store.db`) with different access patterns:
- Store service: Creates jobs, reads results
- Worker: Claims jobs, updates status/progress
- Auth service: Uses separate database for user data

All SQLite databases should use **WAL mode** (Write-Ahead Logging) for concurrent access. Services configure this when creating engines.

### Package Structure

```
src/cl_server_shared/
├── __init__.py                    # Public API: Config, FileStorageService, Job, QueueEntry, SQLAlchemyJobRepository
├── config.py                      # Config class - centralized configuration singleton
├── file_storage.py                # FileStorageService (implements cl_ml_tools.FileStorage)
├── shared_db.py                   # SQLAlchemyJobRepository (implements cl_ml_tools.JobRepository)
└── models/
    ├── __init__.py                # Base, Job, QueueEntry
    ├── job.py                     # Job model
    └── queue.py                   # QueueEntry model
```

### Configuration System

The `Config` class (config.py:16) is a **centralized configuration singleton**:
- All values are class variables accessed directly: `Config.CL_SERVER_DIR`
- Values loaded from environment variables with service-specific defaults
- **No module-level variable exports** - use `Config.VARIABLE_NAME` pattern

**Important**: `CL_SERVER_DIR` environment variable is **required** and must be writable. All file paths default relative to this directory.

### MQTT Event Broadcasting

Built into `SQLAlchemyJobRepository` via `cl_ml_tools.get_broadcaster()`:
- `MQTTBroadcaster` for production (paho-mqtt)
- `NoOpBroadcaster` for testing/dev
- Always call `shutdown_broadcaster()` on cleanup
- Use `clear_retained(topic)` to remove sticky retained messages from broker

Events published: `started`, `progress`, `completed`, `failed` with job_id and metadata.

### Compute Module Pattern

To create a new compute module:

1. Import and subclass `ComputeModule` from `cl_ml_tools`
2. Implement `supported_task_types` property returning list of task type strings
3. Implement async `process()` method with signature:
   ```python
   async def process(
       self, job_id: str, task_type: str,
       params: dict,  # Raw dict from JSON, validated by cl_ml_tools
       progress_callback: Optional[Callable[[int], None]] = None
   ) -> Dict[str, Any]
   ```
4. Return dict with keys: `status` ("ok"/"error"), `task_output`, `error` (optional)
5. Call `run_compute_job(module)` from `cl_server_shared` in `if __name__ == "__main__"`

The `run_compute_job()` function handles all infrastructure:
- CLI argument parsing (--job-id)
- Database connection setup
- Job status updates
- MQTT event publishing
- Progress callbacks
- Error handling and retries

### Parameter Validation

All compute job parameters are defined in `cl_ml_tools` as Pydantic models. The compute module receives parameters as a dict and cl_ml_tools handles validation.

### Database Models

`Job` model (models/job.py:8) is the **central shared entity**:
- `job_id` - Unique identifier (indexed)
- `task_type` - String identifying compute task
- `params` - JSON-encoded parameters
- `status` - Lifecycle state (indexed for worker queries)
- `progress` - 0-100 percentage
- Timestamps: `created_at`, `started_at`, `completed_at`
- `task_output` - JSON results from worker
- `retry_count` / `max_retries` - Automatic retry logic
- `created_by` - User attribution (indexed)

`QueueEntry` model (models/queue.py) - Priority queue for job scheduling.

## Important Patterns

### SQLAlchemy Base Class
All models inherit from `Base` (models/__init__.py:6). When creating new models:
```python
from cl_server_shared.models import Base
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class MyModel(Base):
    __tablename__ = "my_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
```

### Database Access Pattern
Services create their own engines and sessions:
```python
from cl_server_shared import Config, SQLAlchemyJobRepository
from cl_server_shared.models import Base
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Create engine
engine = create_engine(
    Config.STORE_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Enable WAL mode for concurrent access
@event.listens_for(engine, "connect")
def enable_wal_mode(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()

# Create tables
Base.metadata.create_all(bind=engine)

# Create session factory
session_factory = sessionmaker(bind=engine)

# Create repository
repository = SQLAlchemyJobRepository(session_factory)
```

### SQLAlchemyJobRepository

**Location**: `shared_db.py:37`

Implements `cl_ml_tools.JobRepository` protocol with SQLAlchemy backend:
- Maps between library Job (7 fields) and database Job (14 fields)
- Handles JSON serialization, timestamps, retry logic
- `fetch_next_job()` uses optimistic locking for atomic job claiming
- MQTT broadcasting integrated via `Config` values

**Key Methods**:
- `add_job(job, created_by=None, priority=None)` - Add job to database
- `get_job(job_id)` - Retrieve job by ID
- `update_job(job_id, **kwargs)` - Update job fields
- `fetch_next_job(task_types)` - Atomically claim next queued job
- `delete_job(job_id)` - Delete job

### FileStorageService

**Location**: `file_storage.py:16`

Implements `cl_ml_tools.FileStorage` protocol directly (no separate adapter):
- Manages job directories with input/output subdirectories
- Returns absolute paths (protocol requirement)
- SHA256 hash calculation for uploaded files

**Key Methods**:
- `create_job_directory(job_id)` - Create job workspace
- `get_input_path(job_id)` - Absolute path to input directory
- `get_output_path(job_id)` - Absolute path to output directory
- `save_input_file(job_id, filename, file)` - Save uploaded file (async)
- `cleanup_job(job_id)` - Delete job directory

## Environment Variables

Required:
- `CL_SERVER_DIR` - Base directory for all data (must exist and be writable)

Optional (with defaults):
- `DATABASE_URL` - Override default database paths
- `MEDIA_STORAGE_DIR` - Media file location (default: `{CL_SERVER_DIR}/media`)
- `COMPUTE_STORAGE_DIR` - Compute workspace (default: `{CL_SERVER_DIR}/compute`)
- `MQTT_BROKER` - MQTT hostname (default: `localhost`)
- `MQTT_PORT` - MQTT port (default: `1883`)
- `MQTT_TOPIC` - Event topic (default: `inference/events`)
- `BROADCAST_TYPE` - "mqtt" or other (default: `mqtt`)
- `LOG_LEVEL` - Logging level (default: `INFO`)
- `WORKER_ID` - Worker identifier (default: `worker-default`)
- `WORKER_SUPPORTED_TASKS` - Comma-separated task types
- `WORKER_POLL_INTERVAL` - Seconds between job polls (default: `5`)

Auth-specific:
- `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` - ES256 JWT keys
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` - Default admin credentials
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiry (default: `30`)

## Code Style

- Line length: 100 characters (pyproject.toml:89)
- Python 3.9+ compatibility required
- Ruff for linting: E, F, I, W rules (E501 ignored)
- Type hints required for public APIs

## Public API

**Import Pattern**:
```python
from cl_server_shared import (
    Config,                     # Configuration singleton
    FileStorageService,         # File storage (implements cl_ml_tools.FileStorage)
    Job,                        # Job model
    QueueEntry,                 # Queue model
    SQLAlchemyJobRepository,    # Job repository (implements cl_ml_tools.JobRepository)
)
```

**What's NOT exported**:
- Database utilities (services create their own engines/sessions)
- Base class (import from `cl_server_shared.models`)
- Protocols (use from `cl_ml_tools` package)

## Testing

Tests are organized by component:
- `tests/test_config.py` - Configuration tests
- `tests/test_shared_db.py` - SQLAlchemyJobRepository and model tests
- `tests/test_file_storage.py` - FileStorageService tests

When writing tests:
- Create in-memory SQLite databases for repository tests
- Use temporary directories for file storage tests
- Mock MQTT broadcaster in repository tests
- Test protocol compliance (isinstance checks)
