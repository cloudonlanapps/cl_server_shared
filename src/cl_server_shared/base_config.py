"""Common configuration validation utilities."""
import os
from pathlib import Path

def get_cl_server_dir() -> str:
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
        raise ValueError(f"CL_SERVER_DIR does not exist or no write permission: {cl_server_dir}")

    return cl_server_dir

def get_config_value(key: str, default: str = None) -> str:
    """Get configuration value from environment with optional default."""
    return os.getenv(key, default)

def get_int_config(key: str, default: int) -> int:
    """Get integer configuration value."""
    return int(os.getenv(key, str(default)))

def get_bool_config(key: str, default: bool = False) -> bool:
    """Get boolean configuration value."""
    return os.getenv(key, str(default)).lower() in ("true", "1", "yes")
