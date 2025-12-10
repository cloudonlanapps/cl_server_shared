"""Configuration for all CL Server services.

Usage:
    from cl_server_shared.config import Config

    # Access config values
    database_url = Config.AUTH_DATABASE_URL
    storage_dir = Config.MEDIA_STORAGE_DIR
"""

import os
from pathlib import Path
from typing import List, Optional


class Config:
    """Centralized configuration for all CL Server services.

    All configuration values are class variables that can be accessed directly.
    Values are loaded from environment variables with sensible defaults.

    Example:
        from cl_server_shared.config import Config

        print(Config.CL_SERVER_DIR)
        print(Config.AUTH_DATABASE_URL)
    """

    # ========================================================================
    # Helper methods (static)
    # ========================================================================

    @staticmethod
    def _get_cl_server_dir() -> str:
        """Get and validate CL_SERVER_DIR environment variable.

        Returns:
            Validated CL_SERVER_DIR path

        Raises:
            ValueError: If CL_SERVER_DIR not set or not writable
        """
        cl_server_dir = os.getenv("CL_SERVER_DIR")
        if not cl_server_dir:
            raise ValueError("CL_SERVER_DIR environment variable must be set")

        if not os.access(cl_server_dir, os.W_OK):
            raise ValueError(
                f"CL_SERVER_DIR does not exist or no write permission: {cl_server_dir}"
            )

        return cl_server_dir

    @staticmethod
    def _get_value(key: str, default: Optional[str] = None) -> Optional[str]:
        """Get configuration value from environment with optional default."""
        return os.getenv(key, default)

    @staticmethod
    def _get_int(key: str, default: int) -> int:
        """Get integer configuration value."""
        return int(os.getenv(key, str(default)))

    @staticmethod
    def _get_bool(key: str, default: bool = False) -> bool:
        """Get boolean configuration value."""
        return os.getenv(key, str(default)).lower() in ("true", "1", "yes")

    @staticmethod
    def _get_list(key: str, default: str, separator: str = ",") -> List[str]:
        """Get list configuration value."""
        return os.getenv(key, default).split(separator)

    # ========================================================================
    # Common Configuration
    # ========================================================================

    CL_SERVER_DIR: str = _get_cl_server_dir.__func__()

    # ========================================================================
    # Database Configuration - DIFFERENT defaults per service
    # ========================================================================

    # Auth service uses separate database
    AUTH_DATABASE_URL: str = _get_value.__func__(
        "DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/user_auth.db"
    )

    # Store service and worker share the same database
    STORE_DATABASE_URL: str = _get_value.__func__(
        "DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db"
    )

    WORKER_DATABASE_URL: str = _get_value.__func__(
        "DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db"
    )

    # ========================================================================
    # Auth Service Configuration
    # ========================================================================

    PRIVATE_KEY_PATH: str = _get_value.__func__(
        "PRIVATE_KEY_PATH", f"{CL_SERVER_DIR}/private_key.pem"
    )
    PUBLIC_KEY_PATH: str = _get_value.__func__(
        "PUBLIC_KEY_PATH", f"{CL_SERVER_DIR}/public_key.pem"
    )
    ALGORITHM: str = "ES256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _get_int.__func__(
        "ACCESS_TOKEN_EXPIRE_MINUTES", 30
    )
    ADMIN_USERNAME: str = _get_value.__func__("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = _get_value.__func__("ADMIN_PASSWORD", "admin")

    # ========================================================================
    # Store Service Configuration
    # ========================================================================

    MEDIA_STORAGE_DIR: str = _get_value.__func__(
        "MEDIA_STORAGE_DIR", f"{CL_SERVER_DIR}/media"
    )
    COMPUTE_STORAGE_DIR: str = _get_value.__func__(
        "COMPUTE_STORAGE_DIR", f"{CL_SERVER_DIR}/compute"
    )
    AUTH_DISABLED: bool = _get_bool.__func__("AUTH_DISABLED", False)
    READ_AUTH_ENABLED: bool = _get_bool.__func__("READ_AUTH_ENABLED", False)

    # ========================================================================
    # Worker Configuration
    # ========================================================================

    LOG_LEVEL: str = _get_value.__func__("LOG_LEVEL", "INFO")

    # Worker-specific
    WORKER_ID: str = _get_value.__func__("WORKER_ID", "worker-default")
    WORKER_SUPPORTED_TASKS: List[str] = _get_list.__func__(
        "WORKER_SUPPORTED_TASKS", "image_resize,image_conversion"
    )
    WORKER_POLL_INTERVAL: int = _get_int.__func__("WORKER_POLL_INTERVAL", 5)

    # ========================================================================
    # MQTT Configuration (Store and Worker)
    # ========================================================================

    BROADCAST_TYPE: str = _get_value.__func__("BROADCAST_TYPE", "mqtt")
    MQTT_BROKER: str = _get_value.__func__("MQTT_BROKER", "localhost")
    MQTT_PORT: int = _get_int.__func__("MQTT_PORT", 1883)
    MQTT_TOPIC: str = _get_value.__func__("MQTT_TOPIC", "inference/events")
    MQTT_HEARTBEAT_INTERVAL: int = _get_int.__func__("MQTT_HEARTBEAT_INTERVAL", 30)
    CAPABILITY_TOPIC_PREFIX: str = _get_value.__func__(
        "CAPABILITY_TOPIC_PREFIX", "inference/workers"
    )
    CAPABILITY_CACHE_TIMEOUT: int = _get_int.__func__("CAPABILITY_CACHE_TIMEOUT", 10)


# ============================================================================
# Backward Compatibility - Export individual variables
# ============================================================================
# These are provided for backward compatibility with existing code.
# New code should use Config.VARIABLE_NAME instead.

CL_SERVER_DIR = Config.CL_SERVER_DIR

# Database
AUTH_DATABASE_URL = Config.AUTH_DATABASE_URL
STORE_DATABASE_URL = Config.STORE_DATABASE_URL
WORKER_DATABASE_URL = Config.WORKER_DATABASE_URL

# Auth
PRIVATE_KEY_PATH = Config.PRIVATE_KEY_PATH
PUBLIC_KEY_PATH = Config.PUBLIC_KEY_PATH
ALGORITHM = Config.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = Config.ACCESS_TOKEN_EXPIRE_MINUTES
ADMIN_USERNAME = Config.ADMIN_USERNAME
ADMIN_PASSWORD = Config.ADMIN_PASSWORD

# Store
MEDIA_STORAGE_DIR = Config.MEDIA_STORAGE_DIR
COMPUTE_STORAGE_DIR = Config.COMPUTE_STORAGE_DIR
AUTH_DISABLED = Config.AUTH_DISABLED
READ_AUTH_ENABLED = Config.READ_AUTH_ENABLED

# Worker
LOG_LEVEL = Config.LOG_LEVEL
WORKER_ID = Config.WORKER_ID
WORKER_SUPPORTED_TASKS = Config.WORKER_SUPPORTED_TASKS
WORKER_POLL_INTERVAL = Config.WORKER_POLL_INTERVAL

# MQTT
BROADCAST_TYPE = Config.BROADCAST_TYPE
MQTT_BROKER = Config.MQTT_BROKER
MQTT_PORT = Config.MQTT_PORT
MQTT_TOPIC = Config.MQTT_TOPIC
MQTT_HEARTBEAT_INTERVAL = Config.MQTT_HEARTBEAT_INTERVAL
CAPABILITY_TOPIC_PREFIX = Config.CAPABILITY_TOPIC_PREFIX
CAPABILITY_CACHE_TIMEOUT = Config.CAPABILITY_CACHE_TIMEOUT


# ============================================================================
# Backward Compatibility - Helper functions from base_config
# ============================================================================


def get_cl_server_dir() -> str:
    """Get and validate CL_SERVER_DIR. Use Config.CL_SERVER_DIR instead."""
    return Config._get_cl_server_dir()


def get_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Get config value. Use Config._get_value() instead."""
    return Config._get_value(key, default)


def get_int_config(key: str, default: int) -> int:
    """Get int config. Use Config._get_int() instead."""
    return Config._get_int(key, default)


def get_bool_config(key: str, default: bool = False) -> bool:
    """Get bool config. Use Config._get_bool() instead."""
    return Config._get_bool(key, default)
