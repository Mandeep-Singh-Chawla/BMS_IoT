"""One E2E positive flow aligned with the BMS diagram (with lab limits noted).

Production diagram (telemetry up, gray):
  Sensor → Controller → Gateway (MQTT publish) → BMS Platform → Dashboard

Production diagram (command down, coral):
  Dashboard → BMS Platform (MQTT command publish) → Gateway → Controller → Equipment

What this lab actually implements:
  - Field devices + controller rules + equipment: YAML + FakeNetwork
  - Controller rules: OutdoorTempCoolingController
  - Gateway: BacnetMqttGateway (BACnet-side events ↔ MQTT)
  - FastAPI /ui: read-only dashboard stand-in (GET only in the command half)

Important — two independent write paths into DeviceService (see devices.py):
  - PUT /api/devices/{id}/points  →  write_point_by_name()  (no MQTT)
  - MQTT …/command                →  BacnetMqttGateway       →  write_point_by_name()

There is NO code here where a Dashboard REST write triggers an MQTT publish.
Part 2 uses capmqtt.publish() to simulate an *external BMS platform* sending the
MQTT command topic, not a Dashboard action inside this lab.

Requires: pip install -e '.[dev]'  (pytest-mqtt / Mosquitto)

Portable field_sim copy of this flow:
  tests/integration/test_e2e_field_sim_positive_flow.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

pytest_plugins = ["pytest_mqtt"]

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_api import make_test_client  # noqa: E402

from bacnet_lab.adapters.mqtt.gateway import (  # noqa: E402
    command_topic,
    telemetry_topic,
    write_status_topic,
)

MQTT_PREFIX = "bacnet"
OAT_DEVICE_ID = 5001
AHU_DEVICE_ID = 1001
OUTDOOR_TEMP_POINT = "OAT-01/OutdoorTemp"
COOLING_VALVE = "AHU-01/CoolingValve"
SUPPLY_FAN_ENABLE = "AHU-01/SupplyFanEnable"
FAN_SPEED = "AHU-01/FanSpeed"
SENSOR_TEMP_C = 30.0
BMS_VALVE_COMMAND = 90.0


@pytest.fixture
async def e2e_client(mosquitto):
    async with make_test_client(mqtt_broker=("localhost", 1883), mqtt_topic_prefix=MQTT_PREFIX) as ac:
        yield ac


def _payload_on_topic(messages, topic: str):
    for msg in reversed(messages):
        if getattr(msg, "topic", None) == topic:
            return json.loads(msg.payload)
    return None


def _point_map(device_json: dict) -> dict:
    return {p["object_name"]: p["present_value"] for p in device_json["points"]}


@pytest.mark.capmqtt_decode_utf8
@pytest.mark.asyncio
async def test_e2e_sensor_to_equipment_and_command_back_down(e2e_client, capmqtt):
    """Telemetry up via gateway MQTT; command down via external BMS MQTT publish."""

    # --- Part 1: Telemetry up (Sensor → Controller → Gateway → BMS observer) ---
    write = await e2e_client.put(
        f"/api/devices/{OAT_DEVICE_ID}/points",
        json={"point_name": OUTDOOR_TEMP_POINT, "value": SENSOR_TEMP_C},
    )
    assert write.status_code == 200

    await asyncio.sleep(0.6)

    oat_mqtt = _payload_on_topic(
        capmqtt.messages,
        telemetry_topic(MQTT_PREFIX, OAT_DEVICE_ID, OUTDOOR_TEMP_POINT),
    )
    assert oat_mqtt is not None
    assert float(oat_mqtt["present_value"]) == SENSOR_TEMP_C
    assert oat_mqtt["protocol"] == "bacnet"

    ahu = _point_map((await e2e_client.get(f"/api/devices/{AHU_DEVICE_ID}")).json())
    assert ahu[SUPPLY_FAN_ENABLE] is True
    assert ahu[FAN_SPEED] == 75.0
    assert ahu[COOLING_VALVE] == 80.0

    oat = _point_map((await e2e_client.get(f"/api/devices/{OAT_DEVICE_ID}")).json())
    assert oat[OUTDOOR_TEMP_POINT] == SENSOR_TEMP_C
    ui = await e2e_client.get("/ui")
    assert ui.status_code == 200
    assert "Dashboard" in ui.text

    # --- Part 2: Command down (external BMS → Gateway MQTT → Equipment) ---
    capmqtt.publish(
        topic=command_topic(MQTT_PREFIX, AHU_DEVICE_ID),
        payload=json.dumps(
            {
                "device_id": AHU_DEVICE_ID,
                "point_name": COOLING_VALVE,
                "value": BMS_VALVE_COMMAND,
            }
        ),
    )

    await asyncio.sleep(0.6)

    status = _payload_on_topic(
        capmqtt.messages,
        write_status_topic(MQTT_PREFIX, AHU_DEVICE_ID, COOLING_VALVE),
    )
    assert status is not None
    assert status["success"] is True
    assert float(status["value"]) == BMS_VALVE_COMMAND

    ahu_after = _point_map((await e2e_client.get(f"/api/devices/{AHU_DEVICE_ID}")).json())
    assert ahu_after[COOLING_VALVE] == BMS_VALVE_COMMAND

    valve_mqtt = _payload_on_topic(
        capmqtt.messages,
        telemetry_topic(MQTT_PREFIX, AHU_DEVICE_ID, COOLING_VALVE),
    )
    assert valve_mqtt is not None
    assert float(valve_mqtt["present_value"]) == BMS_VALVE_COMMAND
