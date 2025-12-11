# cl-server-shared

[![PyPI version](https://badge.fury.io/py/cl-server-shared.svg)](https://badge.fury.io/py/cl-server-shared)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Shared utilities for CL Server services - database models, file storage, configuration, and job repository.

## Features

- **Models** - Shared Job and QueueEntry models for distributed job processing
- **Job Repository** - SQLAlchemyJobRepository implementing cl_ml_tools protocol
- **File Storage** - FileStorageService implementing cl_ml_tools protocol
- **Configuration** - Unified Config class with environment variable support
- **MQTT Integration** - Built-in broadcaster for job lifecycle events

## Installation

```bash
pip install cl-server-shared

# With MQTT support
pip install cl-server-shared[mqtt]

# With FastAPI support
pip install cl-server-shared[fastapi]

# With compute/image processing support
pip install cl-server-shared[compute]

# All extras
pip install cl-server-shared[all]
```

## Quick Start

### Configuration

```python
from cl_server_shared import Config

# Access configuration as class variables
print(Config.CL_SERVER_DIR)
print(Config.AUTH_DATABASE_URL)
print(Config.MQTT_PORT)
```

### Database and Job Repository

```python
from cl_server_shared import Job, QueueEntry, SQLAlchemyJobRepository, Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cl_ml_tools import Job as LibraryJob
from uuid import uuid4

# Services create their own engines and sessions
engine = create_engine(
    Config.STORE_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create repository
repository = SQLAlchemyJobRepository(session_factory)

# Add a job
job = LibraryJob(
    job_id=str(uuid4()),
    task_type="image_resize",
    params={"width": 800, "height": 600},
    status="queued",
    progress=0
)
repository.add_job(job, created_by="user123")

# Worker: Fetch next job
next_job = repository.fetch_next_job(["image_resize"])
if next_job:
    repository.update_job(next_job.job_id, progress=50)
    repository.update_job(next_job.job_id, status="completed", progress=100)
```

### File Storage

```python
from cl_server_shared import FileStorageService, Config
from fastapi import UploadFile
from uuid import uuid4

# Create file storage (implements cl_ml_tools.FileStorage protocol)
file_storage = FileStorageService(Config.MEDIA_STORAGE_DIR)

# Create job directory
job_id = str(uuid4())
file_storage.create_job_directory(job_id)

# Save uploaded file (in FastAPI endpoint)
async def upload_file(file: UploadFile):
    file_info = await file_storage.save_input_file(
        job_id=job_id,
        filename=file.filename,
        file=file
    )
    # file_info contains: filename, path (absolute), size, hash
    return file_info

# Cleanup
file_storage.cleanup_job(job_id)
```

## API Reference

### SQLAlchemyJobRepository

Implements `cl_ml_tools.JobRepository` protocol with SQLAlchemy backend.

**Key Methods:**
- `add_job(job, created_by=None, priority=None)` - Add job to database
- `get_job(job_id)` - Retrieve job by ID
- `update_job(job_id, **kwargs)` - Update job fields (status, progress, task_output, error_message)
- `fetch_next_job(task_types)` - Atomically claim next queued job (for workers)
- `delete_job(job_id)` - Delete job from database

**Features:**
- Maps between library Job (7 fields) and database Job (14 fields)
- JSON serialization for params and task_output
- Automatic timestamp management (created_at, started_at, completed_at)
- Retry logic fields (retry_count, max_retries)
- Optimistic locking for atomic job claiming
- MQTT broadcasting of job progress updates

**Example:**
```python
from cl_server_shared import SQLAlchemyJobRepository, Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from cl_ml_tools import Job as LibraryJob

# Setup database and repository
engine = create_engine(Config.STORE_DATABASE_URL)
session_factory = sessionmaker(bind=engine)
repository = SQLAlchemyJobRepository(session_factory)

# Add job
job = LibraryJob(
    job_id="job-123",
    task_type="image_resize",
    params={"width": 100, "height": 100},
    status="queued"
)
repository.add_job(job, created_by="user123", priority=5)

# Fetch and process
next_job = repository.fetch_next_job(["image_resize"])
if next_job:
    repository.update_job(next_job.job_id, progress=50)
    repository.update_job(
        next_job.job_id,
        status="completed",
        progress=100,
        task_output={"output_files": ["/path/to/output.jpg"]}
    )
```

### FileStorageService

Implements `cl_ml_tools.FileStorage` protocol for job file management.

**Key Methods:**
- `create_job_directory(job_id)` - Create job directory with input/output subdirectories
- `get_input_path(job_id)` - Get absolute path to input directory
- `get_output_path(job_id)` - Get absolute path to output directory
- `save_input_file(job_id, filename, file)` - Save uploaded file (async)
- `cleanup_job(job_id)` - Delete job directory and all files

**Features:**
- Returns absolute paths (protocol compliant)
- SHA256 hash calculation for uploaded files
- Organized media storage: `store/YYYY/MM/DD/{md5}.{ext}`
- Isolated job workspaces: `jobs/{job_id}/input/` and `jobs/{job_id}/output/`

**Example:**
```python
from cl_server_shared import FileStorageService
from fastapi import UploadFile

file_storage = FileStorageService("/path/to/media")

# Create job workspace
job_id = "job-123"
job_dir = file_storage.create_job_directory(job_id)

# Save uploaded file
async def upload_handler(file: UploadFile):
    result = await file_storage.save_input_file(job_id, file.filename, file)
    # Returns: {"filename": "...", "path": "/abs/path", "size": 1234, "hash": "..."}
    return result

# Get paths
input_path = file_storage.get_input_path(job_id)
output_path = file_storage.get_output_path(job_id)

# Cleanup
file_storage.cleanup_job(job_id)
```

### Configuration

**Config Class** - Centralized configuration accessed as class variables:

| Config Variable | Description | Default |
|----------------|-------------|---------|
| `CL_SERVER_DIR` | Base directory (required env var) | - |
| `AUTH_DATABASE_URL` | Auth service database | `sqlite:///{CL_SERVER_DIR}/user_auth.db` |
| `STORE_DATABASE_URL` | Store service database | `sqlite:///{CL_SERVER_DIR}/media_store.db` |
| `WORKER_DATABASE_URL` | Worker database (same as store) | `sqlite:///{CL_SERVER_DIR}/media_store.db` |
| `MEDIA_STORAGE_DIR` | Media file storage | `{CL_SERVER_DIR}/media` |
| `COMPUTE_STORAGE_DIR` | Compute workspace | `{CL_SERVER_DIR}/compute` |
| `MQTT_BROKER` | MQTT broker hostname | `localhost` |
| `MQTT_PORT` | MQTT broker port | `1883` |
| `MQTT_TOPIC` | Event topic | `inference/events` |
| `BROADCAST_TYPE` | Broadcaster type | `mqtt` |

**Example:**
```python
from cl_server_shared import Config

# Access configuration
db_url = Config.STORE_DATABASE_URL
media_dir = Config.MEDIA_STORAGE_DIR
```

### Models

**Job** - Central shared entity for distributed job processing:
- `job_id` - Unique identifier (indexed)
- `task_type` - String identifying compute task
- `params` - JSON-encoded parameters
- `status` - Lifecycle state: queued, processing, completed, error (indexed)
- `progress` - 0-100 percentage
- `created_at`, `started_at`, `completed_at` - Timestamps (milliseconds)
- `task_output` - JSON results from worker
- `retry_count`, `max_retries` - Automatic retry logic
- `created_by` - User attribution (indexed)

**QueueEntry** - Priority queue for job scheduling:
- `job_id` - Unique identifier (indexed)
- `priority` - Priority level (default: 5)
- `enqueued_at` - Timestamp (indexed)

## Architecture

### Service Architecture

The library is designed for a **multi-service architecture**:

1. **Auth Service** - JWT-based authentication
   - Separate database: `user_auth.db`
   - Manages users and access tokens

2. **Store Service** - Media file management and job orchestration
   - Database: `media_store.db`
   - Creates jobs, manages file storage
   - Publishes MQTT events for job lifecycle

3. **Worker Service** - Distributed compute processing
   - Shares database with store: `media_store.db`
   - Claims and processes jobs from shared database
   - Updates job status and progress

### Package Structure

```
cl_server_shared/
├── __init__.py                 # Public API exports
├── config.py                   # Config class
├── file_storage.py             # FileStorageService (implements cl_ml_tools.FileStorage)
├── shared_db.py                # SQLAlchemyJobRepository (implements cl_ml_tools.JobRepository)
└── models/
    ├── __init__.py             # Base, Job, QueueEntry
    ├── job.py                  # Job model
    └── queue.py                # QueueEntry model
```

### Public API

```python
from cl_server_shared import (
    Config,                     # Configuration singleton
    FileStorageService,         # File storage (implements cl_ml_tools.FileStorage)
    Job,                        # Job model
    QueueEntry,                 # Queue model
    SQLAlchemyJobRepository,    # Job repository (implements cl_ml_tools.JobRepository)
)
```

### Database Access Pattern

Services create their own database engines and sessions:

```python
from cl_server_shared import Config, SQLAlchemyJobRepository
from cl_server_shared.models import Base
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

# Create engine with SQLite WAL mode for concurrent access
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
    cursor.close()

# Create tables
Base.metadata.create_all(bind=engine)

# Create session factory
session_factory = sessionmaker(bind=engine)

# Create repository
repository = SQLAlchemyJobRepository(session_factory)
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CL_SERVER_DIR` | **Yes** | Base directory for all data (must exist and be writable) |
| `DATABASE_URL` | No | Override default database URL |
| `MEDIA_STORAGE_DIR` | No | Override media storage location |
| `COMPUTE_STORAGE_DIR` | No | Override compute workspace |
| `MQTT_BROKER` | No | MQTT broker hostname (default: localhost) |
| `MQTT_PORT` | No | MQTT broker port (default: 1883) |
| `MQTT_TOPIC` | No | Event topic (default: inference/events) |
| `BROADCAST_TYPE` | No | Broadcaster type (default: mqtt) |
| `LOG_LEVEL` | No | Logging level (default: INFO) |
| `WORKER_ID` | No | Worker identifier (default: worker-default) |
| `WORKER_SUPPORTED_TASKS` | No | Comma-separated task types |
| `WORKER_POLL_INTERVAL` | No | Seconds between job polls (default: 5) |

Auth-specific:
- `PRIVATE_KEY_PATH` / `PUBLIC_KEY_PATH` - ES256 JWT keys
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` - Default admin credentials
- `ACCESS_TOKEN_EXPIRE_MINUTES` - Token expiry (default: 30)

## Development

```bash
# Clone and install in development mode
git clone https://github.com/cl-server/cl-server-shared.git
cd cl-server-shared
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src/cl_server_shared --cov-report=term-missing

# Lint and format
ruff check src/
ruff format src/
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request
