"""MQTT gateway for field_sim. Requires paho-mqtt and a running broker (e.g. Mosquitto).

Topics (prefix default ``bacnet``):
  {prefix}/{device_id}/telemetry/{point_slug}
  {prefix}/{device_id}/command
  {prefix}/{device_id}/write_status/{point_slug}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from field_sim.plant import FieldPlant, PointValue

def point_slug(point_name: str) -> str:
    return point_name.replace("/", ".")


def telemetry_topic(prefix: str, device_id: int, point_name: str) -> str:
    return f"{prefix}/{device_id}/telemetry/{point_slug(point_name)}"


def command_topic(prefix: str, device_id: int | str = "+") -> str:
    return f"{prefix}/{device_id}/command"


def write_status_topic(prefix: str, device_id: int, point_name: str) -> str:
    return f"{prefix}/{device_id}/write_status/{point_slug(point_name)}"


class MqttBridge:
    """Plant writes → telemetry publish; MQTT command → plant write.

    This is the field_sim gateway (same MQTT topic layout as bacnet_lab's
    BacnetMqttGateway). Mosquitto is the broker; this class is not the broker.
    """

    def __init__(
        self,
        plant: FieldPlant,
        *,
        host: str = "localhost",
        port: int = 1883,
        prefix: str = "bacnet",
        protocol: str = "field-sim",
    ) -> None:
        self._plant = plant
        self._prefix = prefix.rstrip("/")
        self._protocol = protocol
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._host = host
        self._port = port
        plant.on_write(self._on_plant_write)

    def start(self) -> None:
        self._client.connect(self._host, self._port, 60)
        self._client.loop_start()

    def wait_connected(self, timeout_s: float = 5.0) -> None:
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._client.is_connected():
                return
            time.sleep(0.05)
        raise TimeoutError(f"MQTT not connected to {self._host}:{self._port}")

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    def _on_connect(self, client, _userdata, _flags, reason_code, _properties=None) -> None:
        if reason_code != 0:
            return
        client.subscribe(command_topic(self._prefix, "+"), qos=1)

    def _on_plant_write(
        self,
        device_id: int,
        point_name: str,
        old: PointValue,
        new: PointValue,
    ) -> None:
        payload = json.dumps(
            {
                "device_id": device_id,
                "point_name": point_name,
                "old_value": old,
                "present_value": new,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "protocol": self._protocol,
            },
            default=str,
        )
        self._client.publish(
            telemetry_topic(self._prefix, device_id, point_name),
            payload,
            qos=1,
        )

    def _on_message(self, _client, _userdata, msg) -> None:
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            device_id = int(data["device_id"])
            point_name = str(data["point_name"])
            value = data["value"]
            self._plant.write(device_id, point_name, value)
            success, error = True, None
        except Exception as e:
            device_id = 0
            point_name = "unknown"
            value = None
            success, error = False, str(e)
            parts = msg.topic.strip("/").split("/")
            if len(parts) >= 2:
                try:
                    device_id = int(parts[-2])
                except ValueError:
                    pass
        status = json.dumps(
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
        self._client.publish(
            write_status_topic(self._prefix, device_id, point_name),
            status,
            qos=1,
        )
