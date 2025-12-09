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
pytest tests/test_adapters.py -v
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
   - Implements `ComputeModule` base class for tasks

### Database Sharing Model

**Critical**: Store service and worker share the **same database** (`media_store.db`) with different access patterns:
- Store service: Creates jobs, reads results
- Worker: Claims jobs, updates status/progress
- Auth service: Uses separate database for user data

All SQLite databases use **WAL mode** (Write-Ahead Logging) enabled via `enable_wal_mode()` for concurrent access. This is critical for multi-process scenarios.

### Configuration System

The `Config` class (config.py:16) is a **centralized configuration singleton**:
- All values are class variables accessed directly: `Config.CL_SERVER_DIR`
- Values loaded from environment variables with service-specific defaults
- Backward compatibility: individual module-level variables exported

**Important**: `CL_SERVER_DIR` environment variable is **required** and must be writable. All file paths default relative to this directory.

### MQTT Event Broadcasting

Global singleton pattern via `get_broadcaster()`:
- `MQTTBroadcaster` for production (paho-mqtt)
- `NoOpBroadcaster` for testing/dev
- Always call `shutdown_broadcaster()` on cleanup

Events published: `started`, `progress`, `completed`, `failed` with job_id and metadata.

### Compute Module Pattern

To create a new compute module:

1. Subclass `ComputeModule` (compute.py:35)
2. Implement `supported_task_types` property returning list of task type strings
3. Implement async `process()` method with signature:
   ```python
   async def process(
       self, job_id: str, task_type: str,
       params: ComputeJobParams,
       progress_callback: Optional[Callable[[int], None]] = None
   ) -> Dict[str, Any]
   ```
4. Return dict with keys: `status` ("ok"/"error"), `task_output`, `error` (optional)
5. Call `run_compute_job(module)` in `if __name__ == "__main__"`

The `run_compute_job()` function handles all infrastructure:
- CLI argument parsing (--job-id)
- Database connection setup
- Job status updates
- MQTT event publishing
- Progress callbacks
- Error handling and retries

### Parameter Validation

All compute job parameters use **Pydantic models** (schemas.py):
- `ComputeJobParams` - Base class with input/output paths
- `ImageResizeParams` - Extends base with width/height
- `ImageConversionParams` - Extends base with format/quality

Validators ensure:
- Output paths are unique
- Input and output path counts match
- At least one input path provided

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
All models inherit from `Base` (database.py:6). When creating new models:
```python
from cl_server_shared.database import Base
from sqlalchemy.orm import Mapped, mapped_column

class MyModel(Base):
    __tablename__ = "my_table"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
```

### Session Factory Pattern
```python
from cl_server_shared import create_db_engine, create_session_factory
from cl_server_shared.config import Config

engine = create_db_engine(Config.STORE_DATABASE_URL)
SessionLocal = create_session_factory(engine)

# Use in FastAPI
from cl_server_shared import get_db_session
app.dependency(Depends(lambda: get_db_session(SessionLocal)))
```

### File Storage Service
`FileStorageService` manages media files with job-specific directories:
- `save_file()` - Save uploaded files with UUID naming
- `create_job_directory()` - Create isolated job workspace
- `cleanup_job()` - Remove job files on completion/failure

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
