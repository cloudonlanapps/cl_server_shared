"""Shared utilities for CL Server services."""

# Database utilities
from .database import (
    Base,
    enable_wal_mode,
    create_db_engine,
    create_session_factory,
    get_db_session,
)

# Models
from .models.job import Job
from .models.queue import QueueEntry

# MQTT
from .mqtt_instance import (
    get_broadcaster,
    shutdown_broadcaster,
)

# File storage
from .file_storage import FileStorageService

# Configuration - new unified Config class
from .config import (
    Config,
    # Backward compatibility: helper functions
    get_cl_server_dir,
    get_config_value,
    get_int_config,
    get_bool_config,
    # Backward compatibility: individual variables
    WORKER_DATABASE_URL,
    WORKER_ID,
    WORKER_SUPPORTED_TASKS,
    WORKER_POLL_INTERVAL,
    LOG_LEVEL,
    MQTT_HEARTBEAT_INTERVAL,
    CAPABILITY_TOPIC_PREFIX,
    BROADCAST_TYPE,
    MQTT_BROKER,
    MQTT_PORT,
    MQTT_TOPIC,
    COMPUTE_STORAGE_DIR,
)

# Configuration module (all services)
from . import config


__all__ = [
    # Database
    "Base",
    "enable_wal_mode",
    "create_db_engine",
    "create_session_factory",
    "get_db_session",
    # Models
    "Job",
    "QueueEntry",
    # MQTT Instance
    "get_broadcaster",
    "shutdown_broadcaster",
    # File storage
    "FileStorageService",
    # Config - NEW: use Config class
    "Config",
    # Config - Backward compatibility
    "get_cl_server_dir",
    "get_config_value",
    "get_int_config",
    "get_bool_config",
    "config",
    # Config Variables (backward compatibility)
    "WORKER_DATABASE_URL",
    "WORKER_ID",
    "WORKER_SUPPORTED_TASKS",
    "WORKER_POLL_INTERVAL",
    "LOG_LEVEL",
    "MQTT_HEARTBEAT_INTERVAL",
    "CAPABILITY_TOPIC_PREFIX",
    "BROADCAST_TYPE",
    "MQTT_BROKER",
    "MQTT_PORT",
    "MQTT_TOPIC",
    "COMPUTE_STORAGE_DIR",
]
