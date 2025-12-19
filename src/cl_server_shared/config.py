"""Configuration for all CL Server services.

Usage:
    from cl_server_shared.config import Config

    # Access config values
    database_url = Config.AUTH_DATABASE_URL
    storage_dir = Config.MEDIA_STORAGE_DIR
"""

import os


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
    def _get_value(key: str, default: str) -> str:
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
    def _get_list(key: str, default: str, separator: str = ",") -> list[str]:
        """Get list configuration value."""
        return os.getenv(key, default).split(separator)

    # ========================================================================
    # Common Configuration
    # ========================================================================

    CL_SERVER_DIR: str = _get_cl_server_dir()

    # ========================================================================
    # Database Configuration - DIFFERENT defaults per service
    # ========================================================================

    # Auth service uses separate database
    AUTH_DATABASE_URL: str = _get_value("DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/user_auth.db")

    # Store service and worker share the same database
    STORE_DATABASE_URL: str = _get_value(
        "DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db"
    )

    WORKER_DATABASE_URL: str = _get_value(
        "DATABASE_URL", f"sqlite:///{CL_SERVER_DIR}/media_store.db"
    )

    # ========================================================================
    # Auth Service Configuration
    # ========================================================================

    PRIVATE_KEY_PATH: str = _get_value("PRIVATE_KEY_PATH", f"{CL_SERVER_DIR}/private_key.pem")
    PUBLIC_KEY_PATH: str = _get_value("PUBLIC_KEY_PATH", f"{CL_SERVER_DIR}/public_key.pem")
    ALGORITHM: str = "ES256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = _get_int("ACCESS_TOKEN_EXPIRE_MINUTES", 30)
    ADMIN_USERNAME: str = _get_value("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = _get_value("ADMIN_PASSWORD", "admin")

    # ========================================================================
    # Store Service Configuration
    # ========================================================================

    MEDIA_STORAGE_DIR: str = _get_value("MEDIA_STORAGE_DIR", f"{CL_SERVER_DIR}/media")
    COMPUTE_STORAGE_DIR: str = _get_value("COMPUTE_STORAGE_DIR", f"{CL_SERVER_DIR}/compute")
    AUTH_DISABLED: bool = _get_bool("AUTH_DISABLED", False)
    READ_AUTH_ENABLED: bool = _get_bool("READ_AUTH_ENABLED", False)

    # ========================================================================
    # Worker Configuration
    # ========================================================================

    LOG_LEVEL: str = _get_value("LOG_LEVEL", "INFO")

    # Worker-specific
    WORKER_ID: str = _get_value("WORKER_ID", "worker-default")
    WORKER_SUPPORTED_TASKS: list[str] = _get_list(
        "WORKER_SUPPORTED_TASKS", "image_resize,image_conversion"
    )
    WORKER_POLL_INTERVAL: int = _get_int("WORKER_POLL_INTERVAL", 5)

    # ========================================================================
    # MQTT Configuration (Store and Worker)
    # ========================================================================

    BROADCAST_TYPE: str = _get_value("BROADCAST_TYPE", "mqtt")
    MQTT_BROKER: str = _get_value("MQTT_BROKER", "localhost")
    MQTT_PORT: int = _get_int("MQTT_PORT", 1883)
    MQTT_TOPIC: str = _get_value("MQTT_TOPIC", "inference/events")
    MQTT_HEARTBEAT_INTERVAL: int = _get_int("MQTT_HEARTBEAT_INTERVAL", 30)
    CAPABILITY_TOPIC_PREFIX: str = _get_value("CAPABILITY_TOPIC_PREFIX", "inference/workers")
    CAPABILITY_CACHE_TIMEOUT: int = _get_int("CAPABILITY_CACHE_TIMEOUT", 10)
