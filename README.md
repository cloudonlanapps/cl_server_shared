# cl-server-shared

[![PyPI version](https://badge.fury.io/py/cl-server-shared.svg)](https://badge.fury.io/py/cl-server-shared)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Shared utilities for CL Server services - database, file storage, MQTT, configuration, and compute modules.

## Features

- **Database utilities** - SQLAlchemy helpers with WAL mode for SQLite concurrent access
- **Models** - Shared Job and QueueEntry models
- **MQTT** - Broadcaster classes for event publishing
- **File storage** - FileStorageService for media file management
- **Configuration** - Unified Config class with environment variable support
- **Compute** - Base classes for compute modules

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
from cl_server_shared.config import Config

# Access configuration as class variables
print(Config.CL_SERVER_DIR)
print(Config.AUTH_DATABASE_URL)
print(Config.MQTT_PORT)
```

### Database

```python
from cl_server_shared import Base, create_db_engine, create_session_factory
from cl_server_shared.config import Config

engine = create_db_engine(Config.STORE_DATABASE_URL)
SessionLocal = create_session_factory(engine)
```

### File Storage

```python
from cl_server_shared import FileStorageService
from cl_server_shared.config import Config

file_storage = FileStorageService(Config.MEDIA_STORAGE_DIR)
```

### MQTT Broadcasting

```python
from cl_ml_tools import get_broadcaster, shutdown_broadcaster
from cl_server_shared.config import Config

broadcaster = get_broadcaster(
    Config.BROADCAST_TYPE,
    Config.MQTT_BROKER,
    Config.MQTT_PORT,
    Config.MQTT_TOPIC
)
```

## Usage Guide

### SQLAlchemyJobRepository

The `SQLAlchemyJobRepository` adapter bridges the `cl_ml_tools` JobRepository protocol with SQLAlchemy database operations. It handles mapping between the library's minimal Job schema and the database's full Job model.

```python
from cl_server_shared import create_db_engine, create_session_factory
from cl_server_shared.adapters import SQLAlchemyJobRepository
from cl_server_shared.config import Config
from cl_ml_tools import Job as LibraryJob
from uuid import uuid4

# Setup database and repository
engine = create_db_engine(Config.STORE_DATABASE_URL)
session_factory = create_session_factory(engine)
repository = SQLAlchemyJobRepository(session_factory)

# Add a job
job = LibraryJob(
    job_id=str(uuid4()),
    task_type="image_resize",
    params={
        "input_paths": ["/path/to/input.jpg"],
        "output_paths": ["/path/to/output.jpg"],
        "width": 800,
        "height": 600
    },
    status="queued",
    progress=0
)
repository.add_job(job, created_by="user123", priority=5)

# Fetch next job (worker)
next_job = repository.fetch_next_job(["image_resize", "image_conversion"])
if next_job:
    print(f"Processing job: {next_job.job_id}")

    # Update progress
    repository.update_job(next_job.job_id, progress=50)

    # Mark complete
    repository.update_job(
        next_job.job_id,
        status="completed",
        progress=100,
        task_output={"output_files": ["/path/to/output.jpg"]}
    )

# Get job status
job = repository.get_job(job_id)
print(f"Status: {job.status}, Progress: {job.progress}")
```

Key methods:
- `add_job(job, created_by=None, priority=None)` - Add job to database
- `get_job(job_id)` - Retrieve job by ID
- `update_job(job_id, **kwargs)` - Update job fields (status, progress, task_output, error_message)
- `fetch_next_job(task_types)` - Atomically claim next queued job (for workers)
- `delete_job(job_id)` - Delete job from database

### FileStorageAdapter

The `FileStorageAdapter` wraps `FileStorageService` to implement the `cl_ml_tools` FileStorage protocol. It manages job directories and file operations.

```python
from cl_server_shared import FileStorageService
from cl_server_shared.adapters import FileStorageAdapter
from cl_server_shared.config import Config
from fastapi import UploadFile
from uuid import uuid4

# Setup file storage
file_storage_service = FileStorageService(Config.MEDIA_STORAGE_DIR)
file_storage = FileStorageAdapter(file_storage_service)

# Create job directory
job_id = str(uuid4())
job_dir = file_storage.create_job_directory(job_id)
print(f"Job directory: {job_dir}")
print(f"Input directory: {file_storage.get_input_path(job_id)}")
print(f"Output directory: {file_storage.get_output_path(job_id)}")

# Save uploaded file (in FastAPI endpoint)
async def upload_file(file: UploadFile):
    file_info = await file_storage.save_input_file(
        job_id=job_id,
        filename=file.filename,
        file=file
    )
    # file_info contains: filename, path (absolute), size, hash
    return file_info

# Cleanup job files
file_storage.cleanup_job(job_id)
```

Key methods:
- `create_job_directory(job_id)` - Create job directory with input/output subdirectories
- `get_input_path(job_id)` - Get absolute path to input directory
- `get_output_path(job_id)` - Get absolute path to output directory
- `save_input_file(job_id, filename, file)` - Save uploaded file (async)
- `cleanup_job(job_id)` - Delete job directory and all files

### MQTTBroadcaster

The `MQTTBroadcaster` publishes job events and worker status to an MQTT broker. It's used internally by `run_compute_job` but can also be used directly for custom event broadcasting.

```python
from cl_ml_tools import MQTTBroadcaster
from cl_server_shared.mqtt_instance import get_broadcaster, shutdown_broadcaster
from cl_server_shared.config import Config
import json
import time

# Option 1: Use global singleton (recommended)
broadcaster = get_broadcaster(
    broadcast_type=Config.BROADCAST_TYPE,  # "mqtt" or other
    broker=Config.MQTT_BROKER,
    port=Config.MQTT_PORT,
    topic=Config.MQTT_TOPIC
)

# Option 2: Create instance directly
broadcaster = MQTTBroadcaster(
    broker="localhost",
    port=1883,
    topic="inference/events"
)
broadcaster.connect()

# Publish job lifecycle events
job_id = "job-12345"

# Job started
broadcaster.publish_event(
    event_type="started",
    job_id=job_id,
    data={"status": "processing"}
)

# Progress update
broadcaster.publish_event(
    event_type="progress",
    job_id=job_id,
    data={"progress": 50}
)

# Job completed
broadcaster.publish_event(
    event_type="completed",
    job_id=job_id,
    data={"task_output": {"output_files": ["/path/to/output.jpg"]}}
)

# Job failed
broadcaster.publish_event(
    event_type="failed",
    job_id=job_id,
    data={"error": "File not found"}
)

# Publish custom events to other topics
broadcaster.publish_retained(
    topic="workers/worker-1/status",
    payload=json.dumps({"status": "online", "timestamp": int(time.time() * 1000)}),
    qos=1
)

# Clear a retained message (publishes empty payload to remove sticky message)
broadcaster.clear_retained(topic="workers/worker-1/status")

# Cleanup
shutdown_broadcaster()  # If using global singleton
# or
broadcaster.disconnect()  # If using direct instance
```

Event payload format:
```json
{
  "job_id": "job-12345",
  "event_type": "progress",
  "timestamp": 1234567890123,
  "progress": 50
}
```

Key methods:
- `connect()` - Connect to MQTT broker
- `disconnect()` - Disconnect from broker
- `publish_event(event_type, job_id, data)` - Publish job event
- `publish_retained(topic, payload, qos=1)` - Publish retained message
- `clear_retained(topic, qos=1)` - Clear retained message (removes sticky message from broker)
- `set_will(topic, payload, qos=1, retain=True)` - Set Last Will and Testament

### run_compute_job

The `run_compute_job` function executes compute modules from `cl_ml_tools`. It handles the complete job lifecycle including database updates, MQTT events, progress tracking, and error handling.

```python
# my_image_module.py
from cl_ml_tools import ComputeModule
from cl_server_shared import run_compute_job
from PIL import Image
from pathlib import Path

class ImageResizeModule(ComputeModule):
    """Example compute module for image resizing."""

    @property
    def supported_task_types(self):
        return ["image_resize"]

    async def process(self, job_id, task_type, params, progress_callback=None):
        """Process image resize job.

        Args:
            job_id: Unique job identifier
            task_type: Task type (e.g., "image_resize")
            params: Dict with input_paths, output_paths, width, height
            progress_callback: Optional callback(percentage: int)

        Returns:
            Dict with status, task_output, and optional error
        """
        try:
            # Parse params (run_compute_job provides raw dict)
            input_paths = params["input_paths"]
            output_paths = params["output_paths"]
            width = params["width"]
            height = params["height"]

            # Report progress
            if progress_callback:
                progress_callback(10)

            output_files = []
            for i, (input_path, output_path) in enumerate(zip(input_paths, output_paths)):
                # Process image
                img = Image.open(input_path)
                img_resized = img.resize((width, height))
                img_resized.save(output_path)

                output_files.append({
                    "path": str(output_path),
                    "size": Path(output_path).stat().st_size
                })

                # Update progress
                if progress_callback:
                    progress = 10 + int((i + 1) / len(input_paths) * 90)
                    progress_callback(progress)

            return {
                "status": "ok",
                "task_output": {
                    "output_files": output_files,
                    "dimensions": {"width": width, "height": height}
                }
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

if __name__ == "__main__":
    # Run the module
    module = ImageResizeModule()
    run_compute_job(module)
```

Run the module:
```bash
# Set required environment variable
export CL_SERVER_DIR=/path/to/data

# Execute module with job ID
python my_image_module.py --job-id job-12345
```

What `run_compute_job` handles:
- ✅ Parsing `--job-id` command line argument
- ✅ Database connection setup (using `Config.WORKER_DATABASE_URL`)
- ✅ Job retrieval and status updates (queued → processing → completed/error)
- ✅ MQTT event publishing (started, progress, completed, failed)
- ✅ Timestamp tracking (started_at, completed_at)
- ✅ Progress callback management
- ✅ Error handling and retry logic
- ✅ Automatic cleanup on exit

## Components

### Configuration (`config.py`)

Unified `Config` class with all configuration values:

| Config | Description | Default |
|--------|-------------|---------|
| `CL_SERVER_DIR` | Base directory (required env var) | - |
| `AUTH_DATABASE_URL` | Auth service database | `sqlite:///{CL_SERVER_DIR}/user_auth.db` |
| `STORE_DATABASE_URL` | Store service database | `sqlite:///{CL_SERVER_DIR}/media_store.db` |
| `MEDIA_STORAGE_DIR` | Media file storage directory | `{CL_SERVER_DIR}/media` |
| `MQTT_BROKER` | MQTT broker hostname | `localhost` |
| `MQTT_PORT` | MQTT broker port | `1883` |

### Database (`database.py`)

- `Base` - SQLAlchemy declarative base class
- `enable_wal_mode()` - Enable SQLite WAL mode for concurrent access
- `create_db_engine()` - Create engine with WAL mode
- `create_session_factory()` - Create session factory
- `get_db_session()` - FastAPI dependency for sessions

### Models (`models/`)

- `Job` - Compute job model with status tracking
- `QueueEntry` - Priority queue model

### MQTT (`mqtt.py`)

- `MQTTBroadcaster` - MQTT event publisher
- `NoOpBroadcaster` - No-op broadcaster for testing
- `get_broadcaster()` - Get or create global broadcaster
- `shutdown_broadcaster()` - Cleanup broadcaster

### File Storage (`file_storage.py`)

- `FileStorageService` - Media file storage and management
  - `save_file()` - Save uploaded files
  - `delete_file()` - Delete files
  - `create_job_directory()` - Create job-specific directories
  - `cleanup_job()` - Remove job files

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `CL_SERVER_DIR` | Yes | Base directory for all data |
| `DATABASE_URL` | No | Override default database URL |
| `MEDIA_STORAGE_DIR` | No | Override media storage location |
| `MQTT_BROKER` | No | MQTT broker hostname |
| `MQTT_PORT` | No | MQTT broker port |
| `LOG_LEVEL` | No | Logging level (default: INFO) |

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    Your Application                        │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Auth Service │  │Store Service │  │   Worker     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│         │                 │                 │              │
│         └─────────────────┼─────────────────┘              │
│                           │                                │
│                           ▼                                │
│  ┌────────────────────────────────────────────────────┐   │
│  │              cl-server-shared                      │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────────┐  │   │
│  │  │ Config │ │Database│ │  MQTT  │ │FileStorage │  │   │
│  │  └────────┘ └────────┘ └────────┘ └────────────┘  │   │
│  └────────────────────────────────────────────────────┘   │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

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
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
