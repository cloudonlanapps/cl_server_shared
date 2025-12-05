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
from cl_server_shared import get_broadcaster, shutdown_broadcaster
from cl_server_shared.config import Config

broadcaster = get_broadcaster(
    Config.BROADCAST_TYPE,
    Config.MQTT_BROKER,
    Config.MQTT_PORT,
    Config.MQTT_TOPIC
)
```

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
