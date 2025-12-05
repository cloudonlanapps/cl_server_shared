"""MQTT broadcaster for job events and worker capabilities."""
import json
import logging
import time
from typing import Optional
import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

class MQTTBroadcaster:
    """MQTT event broadcaster for job progress and worker status."""

    def __init__(self, broker: str, port: int, topic: str):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.client: Optional[mqtt.Client] = None
        self.connected = False

    def connect(self) -> bool:
        try:
            self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            self.client.on_connect = self._on_connect
            self.client.connect(self.broker, self.port, keepalive=60)
            self.client.loop_start()
            self.connected = True
            return True
        except Exception as e:
            logger.warning(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False

    def publish_event(self, event_type: str, job_id: str, data: dict) -> bool:
        if not self.connected or not self.client:
            return False
        try:
            payload = {
                "job_id": job_id,
                "event_type": event_type,
                "timestamp": int(time.time() * 1000),
                **data,
            }
            result = self.client.publish(self.topic, json.dumps(payload), qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing event: {e}")
            return False

    def set_will(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
        """Set MQTT Last Will and Testament message."""
        if not self.client:
            return False
        try:
            self.client.will_set(topic, payload, qos=qos, retain=retain)
            return True
        except Exception as e:
            logger.error(f"Error setting LWT: {e}")
            return False

    def publish_retained(self, topic: str, payload: str, qos: int = 1) -> bool:
        """Publish a retained MQTT message."""
        if not self.connected or not self.client:
            return False
        try:
            result = self.client.publish(topic, payload, qos=qos, retain=True)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error(f"Error publishing retained message: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        self.connected = (rc == 0)


class NoOpBroadcaster:
    """No-operation broadcaster for testing or when MQTT disabled."""
    def connect(self) -> bool:
        return True
    def disconnect(self):
        pass
    def publish_event(self, event_type: str, job_id: str, data: dict) -> bool:
        return True
    def set_will(self, topic: str, payload: str, qos: int = 1, retain: bool = True) -> bool:
        return True
    def publish_retained(self, topic: str, payload: str, qos: int = 1) -> bool:
        return True


_broadcaster: Optional[object] = None

def get_broadcaster(broadcast_type: str, broker: str, port: int, topic: str):
    """Get or create global broadcaster instance."""
    global _broadcaster
    if _broadcaster is not None:
        return _broadcaster

    if broadcast_type == "mqtt":
        _broadcaster = MQTTBroadcaster(broker, port, topic)
        _broadcaster.connect()
    else:
        _broadcaster = NoOpBroadcaster()
        _broadcaster.connect()

    return _broadcaster

def shutdown_broadcaster():
    """Shutdown global broadcaster."""
    global _broadcaster
    if _broadcaster:
        _broadcaster.disconnect()
        _broadcaster = None
