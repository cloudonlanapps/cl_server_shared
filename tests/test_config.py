"""Unit tests for Config class."""

import os
import tempfile
from pathlib import Path

import pytest

from cl_server_shared import Config


class TestConfig:
    """Test suite for Config class."""

    def test_config_has_required_attributes(self):
        """Test that Config class has all required configuration attributes."""
        # Database configuration
        assert hasattr(Config, "CL_SERVER_DIR")
        assert hasattr(Config, "AUTH_DATABASE_URL")
        assert hasattr(Config, "STORE_DATABASE_URL")
        assert hasattr(Config, "WORKER_DATABASE_URL")

        # Storage configuration
        assert hasattr(Config, "MEDIA_STORAGE_DIR")
        assert hasattr(Config, "COMPUTE_STORAGE_DIR")

        # MQTT configuration
        assert hasattr(Config, "MQTT_BROKER")
        assert hasattr(Config, "MQTT_PORT")
        assert hasattr(Config, "MQTT_TOPIC")
        assert hasattr(Config, "BROADCAST_TYPE")

        # Worker configuration
        assert hasattr(Config, "WORKER_ID")
        assert hasattr(Config, "WORKER_SUPPORTED_TASKS")
        assert hasattr(Config, "WORKER_POLL_INTERVAL")
        assert hasattr(Config, "LOG_LEVEL")

    def test_config_values_are_strings_or_int(self):
        """Test that Config values have appropriate types."""
        assert isinstance(Config.CL_SERVER_DIR, (str, Path))
        assert isinstance(Config.MQTT_PORT, int)
        assert isinstance(Config.WORKER_POLL_INTERVAL, int)

    def test_database_url_format(self):
        """Test that database URLs are properly formatted."""
        assert Config.AUTH_DATABASE_URL.startswith("sqlite:///")
        assert Config.STORE_DATABASE_URL.startswith("sqlite:///")
        assert Config.WORKER_DATABASE_URL.startswith("sqlite:///")

        # Worker and Store should share the same database
        assert Config.WORKER_DATABASE_URL == Config.STORE_DATABASE_URL

    def test_storage_directories_under_cl_server_dir(self):
        """Test that storage directories are under CL_SERVER_DIR."""
        media_dir = Path(Config.MEDIA_STORAGE_DIR)
        compute_dir = Path(Config.COMPUTE_STORAGE_DIR)
        base_dir = Path(Config.CL_SERVER_DIR)

        # Check media directory is under base
        assert str(media_dir).startswith(str(base_dir))

        # Check compute directory is under base
        assert str(compute_dir).startswith(str(base_dir))

    def test_mqtt_defaults(self):
        """Test MQTT default values."""
        assert Config.MQTT_BROKER == "localhost" or os.getenv("MQTT_BROKER")
        assert Config.MQTT_PORT == 1883 or os.getenv("MQTT_PORT")
        assert Config.MQTT_TOPIC == "inference/events" or os.getenv("MQTT_TOPIC")
        assert Config.BROADCAST_TYPE == "mqtt" or os.getenv("BROADCAST_TYPE")

    def test_worker_defaults(self):
        """Test worker default values."""
        assert Config.WORKER_ID.startswith("worker-") or os.getenv("WORKER_ID")
        assert Config.WORKER_POLL_INTERVAL == 5 or os.getenv("WORKER_POLL_INTERVAL")
        assert Config.LOG_LEVEL in ["DEBUG", "INFO", "WARNING", "ERROR"] or os.getenv(
            "LOG_LEVEL"
        )

    def test_config_is_singleton(self):
        """Test that Config behaves as a singleton (class variables)."""
        # Access from class
        dir1 = Config.CL_SERVER_DIR
        dir2 = Config.CL_SERVER_DIR

        # Should be the same value
        assert dir1 == dir2

    def test_database_paths_exist_in_url(self):
        """Test that database URLs contain valid paths."""
        # Extract path from sqlite:///path
        auth_path = Config.AUTH_DATABASE_URL.replace("sqlite:///", "")
        store_path = Config.STORE_DATABASE_URL.replace("sqlite:///", "")

        # Paths should be absolute
        assert Path(auth_path).is_absolute()
        assert Path(store_path).is_absolute()

        # Paths should contain the database names
        assert "user_auth.db" in auth_path
        assert "media_store.db" in store_path
