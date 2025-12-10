from cl_ml_tools import MQTTBroadcaster, NoOpBroadcaster
from typing import Optional, Union, Dict, Any
import logging

logger = logging.getLogger(__name__)

_broadcaster: Optional[Union[MQTTBroadcaster, NoOpBroadcaster]] = None
_broadcaster_config: Optional[Dict[str, Any]] = None


def get_broadcaster(
    broadcast_type: str, broker: str, port: int
) -> Optional[Union[MQTTBroadcaster, NoOpBroadcaster]]:
    """Get or create global broadcaster instance based on config."""
    global _broadcaster, _broadcaster_config

    desired_config = {
        "broadcast_type": broadcast_type,
        "broker": broker,
        "port": port,
    }

    # Check if existing singleton is compatible
    if _broadcaster is not None and _broadcaster_config == desired_config:
        return _broadcaster

    # Config mismatch — shutdown old broadcaster if needed
    if _broadcaster is not None:
        try:
            _broadcaster.disconnect()
            _broadcaster_config = None
        except Exception:
            pass  # Best effort cleanup

    try:
        # Recreate with new config
        if broadcast_type == "mqtt":
            _broadcaster = MQTTBroadcaster(broker, port)
        else:
            _broadcaster = NoOpBroadcaster()
        _broadcaster.connect()

        _broadcaster_config = desired_config
    except Exception as e:
        logger.error(f"Error setting LWT: {e}")
    return _broadcaster


def shutdown_broadcaster():
    """Shutdown global broadcaster."""
    global _broadcaster
    if _broadcaster:
        _broadcaster.disconnect()
        _broadcaster = None
