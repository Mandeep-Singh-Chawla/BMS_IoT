"""BACnet → MQTT gateway simulator.

Publishes BACnet point changes to MQTT (telemetry) and accepts MQTT writes
(commands) that update BACnet present values via DeviceService.

Topic layout (default prefix ``bacnet``):
  bacnet/{device_id}/telemetry/{point_slug}   — point value updates
  bacnet/{device_id}/command                  — write present value (JSON)
  bacnet/{device_id}/write_status/{point_slug} — command success/failure

Enable for a local run (MQTT is off by default):
  BACNET_LAB_MQTT_ENABLED=1
  BACNET_LAB_MQTT_HOST=localhost
  BACNET_LAB_MQTT_PORT=1883
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from bacnet_lab.domain.events import DomainEvent, PointValueChanged
from bacnet_lab.ports.event_publisher import EventPublisherPort

logger = logging.getLogger(__name__)


def point_name_to_slug(point_name: str) -> str:
    return point_name.replace("/", ".")


def telemetry_topic(prefix: str, device_id: int, point_name: str) -> str:
    return f"{prefix}/{device_id}/telemetry/{point_name_to_slug(point_name)}"


def command_topic(prefix: str, device_id: int | str = "+") -> str:
    """Exact command topic, or wildcard when ``device_id`` is ``'+'``."""
    return f"{prefix}/{device_id}/command"


def write_status_topic(prefix: str, device_id: int, point_name: str) -> str:
    return f"{prefix}/{device_id}/write_status/{point_name_to_slug(point_name)}"


class BacnetMqttGateway:
    """Simulates a field gateway that bridges BACnet point changes to MQTT."""

    def __init__(
        self,
        device_service: object,
        event_publisher: EventPublisherPort,
        *,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        topic_prefix: str = "bacnet",
        username: str = "",
        password: str = "",
        subscribe_commands: bool = True,
    ) -> None:
        self._device_service = device_service
        self._broker_host = broker_host
        self._broker_port = broker_port
        self._topic_prefix = topic_prefix.rstrip("/")
        self._subscribe_commands = subscribe_commands
        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username, password or None)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        event_publisher.subscribe(self._on_event)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._client.user_data_set({"gateway": self, "loop": self._loop})
        await asyncio.to_thread(self._client.connect, self._broker_host, self._broker_port, 60)
        self._client.loop_start()
        self._started = True
        logger.info(
            "BACnet→MQTT gateway started (%s:%d, prefix=%s)",
            self._broker_host,
            self._broker_port,
            self._topic_prefix,
        )

    async def stop(self) -> None:
        self._started = False
        self._client.loop_stop()
        await asyncio.to_thread(self._client.disconnect)

    def _is_ready(self) -> bool:
        return self._started and self._client.is_connected()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: dict,
        _connect_flags,
        reason_code,
        _properties=None,
    ) -> None:
        if reason_code != 0:
            logger.error("MQTT connect failed: %s", reason_code)
            return
        logger.info(
            "MQTT connected to %s:%d",
            self._broker_host,
            self._broker_port,
        )
        if self._subscribe_commands:
            pattern = command_topic(self._topic_prefix, "+")
            client.subscribe(pattern, qos=1)
            logger.info("Subscribed to %s", pattern)

    def _on_disconnect(
        self,
        _client: mqtt.Client,
        _userdata: dict,
        _disconnect_flags,
        reason_code,
        _properties=None,
    ) -> None:
        logger.warning(
            "MQTT disconnected from %s:%d (reason=%s); paho will auto-reconnect",
            self._broker_host,
            self._broker_port,
            reason_code,
        )

    def _on_message(self, _client: mqtt.Client, userdata: dict, msg: mqtt.MQTTMessage) -> None:
        gateway: BacnetMqttGateway = userdata["gateway"]
        loop: asyncio.AbstractEventLoop = userdata["loop"]
        asyncio.run_coroutine_threadsafe(gateway._handle_command(msg), loop)

    async def _publish(self, topic: str, payload: str) -> bool:
        if not self._is_ready():
            logger.debug("Skip MQTT publish (not connected): %s", topic)
            return False
        await asyncio.to_thread(self._client.publish, topic, payload, qos=1)
        return True

    async def _publish_write_status(
        self,
        device_id: int,
        point_name: str,
        *,
        success: bool,
        value: object = None,
        error: str | None = None,
    ) -> None:
        payload = json.dumps(
            {
                "device_id": device_id,
                "point_name": point_name,
                "success": success,
                "value": value,
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            default=str,
        )
        topic = write_status_topic(self._topic_prefix, device_id, point_name)
        await self._publish(topic, payload)

    async def _on_event(self, event: DomainEvent) -> None:
        if not isinstance(event, PointValueChanged):
            return
        if not self._is_ready():
            logger.debug(
                "Skip telemetry publish (MQTT not connected) for %s",
                event.point_name,
            )
            return
        payload = json.dumps(
            {
                "device_id": event.device_id,
                "point_name": event.point_name,
                "old_value": event.old_value,
                "present_value": event.new_value,
                "timestamp": event.timestamp.isoformat(),
                "protocol": "bacnet",
            },
            default=str,
        )
        topic = telemetry_topic(self._topic_prefix, event.device_id, event.point_name)
        await self._publish(topic, payload)

    async def _handle_command(self, msg: mqtt.MQTTMessage) -> None:
        device_id: int | None = None
        point_name: str | None = None
        value = None
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            device_id = int(data["device_id"])
            point_name = str(data["point_name"])
            value = data["value"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
            logger.warning("Invalid MQTT command on %s: %s", msg.topic, e)
            # Best-effort status if we can parse device/point from topic path
            parts = msg.topic.strip("/").split("/")
            if len(parts) >= 2 and parts[-1] == "command":
                try:
                    await self._publish_write_status(
                        int(parts[-2]),
                        "unknown",
                        success=False,
                        error=f"invalid_command_payload: {e}",
                    )
                except ValueError:
                    pass
            return

        try:
            await self._device_service.write_point_by_name(device_id, point_name, value)
            logger.info("MQTT command applied: device=%d point=%s", device_id, point_name)
            await self._publish_write_status(
                device_id, point_name, success=True, value=value
            )
        except Exception as e:
            logger.error("MQTT command failed for %s: %s", msg.topic, e)
            await self._publish_write_status(
                device_id, point_name, success=False, value=value, error=str(e)
            )
