"""Copy of the BMS positive E2E, written for portable field_sim.

Same business flow as tests/integration/test_e2e_bms_positive_flow.py:
  1. Inject OAT = 30°C
  2. MQTT telemetry for OAT (protocol tag bacnet)
  3. Controller starts cooling (fan / speed / valve)
  4. Observer can read OAT
  5. BMS publishes MQTT command valve = 90
  6. MQTT write_status success
  7. Equipment valve is 90
  8. MQTT telemetry valve = 90

Not in this copy (field_sim has no FastAPI):
  4b GET /ui Dashboard — covered only in the lab E2E file.

BACnet/IP (optional, not this file):
  start_field_sim(bacnet=True) or tests/system/test_field_sim_bacnet.py

APIs (instead of REST):
  plant.write / plant.read / plant.snapshot
  start_field_sim() + MqttBridge + capmqtt

Requires: paho-mqtt, Mosquitto on localhost:1883 (or pytest-mqtt Docker).

Other projects: copy src/field_sim and this test pattern.
"""

from __future__ import annotations

import asyncio
import json
import socket

import pytest

from field_sim import (
    EQUIPMENT_ID,
    OAT_POINT,
    SENSOR_ID,
    command_topic,
    start_field_sim,
    telemetry_topic,
    write_status_topic,
)

pytest_plugins = ["pytest_mqtt"]

MQTT_PREFIX = "bacnet"
MQTT_HOST = "localhost"
MQTT_PORT = 1883
COOLING_VALVE = "AHU-01/CoolingValve"
SUPPLY_FAN_ENABLE = "AHU-01/SupplyFanEnable"
FAN_SPEED = "AHU-01/FanSpeed"
SENSOR_TEMP_C = 30.0
BMS_VALVE_COMMAND = 90.0


def _mqtt_broker_up(host: str = MQTT_HOST, port: int = MQTT_PORT) -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


@pytest.fixture
def field_sim_plant(request):
    if not _mqtt_broker_up():
        try:
            request.getfixturevalue("mosquitto")
        except Exception as exc:
            pytest.skip(f"No MQTT broker on localhost:1883: {exc}")
    if not _mqtt_broker_up():
        pytest.skip("No MQTT broker on localhost:1883")

    sim = start_field_sim(
        mqtt_host=MQTT_HOST,
        mqtt_port=MQTT_PORT,
        prefix=MQTT_PREFIX,
        protocol="bacnet",
    )
    try:
        yield sim.plant
    finally:
        sim.stop()


def _payload_on_topic(messages, topic: str):
    for msg in reversed(messages):
        if getattr(msg, "topic", None) == topic:
            return json.loads(msg.payload)
    return None


@pytest.mark.capmqtt_decode_utf8
@pytest.mark.asyncio
async def test_e2e_sensor_to_equipment_and_command_back_down(field_sim_plant, capmqtt):
    """Same positive flow as the lab E2E, on field_sim (no /ui)."""

    # 1. Inject OAT = 30°C (lab E2E: PUT /api/devices/5001/points)
    field_sim_plant.write(SENSOR_ID, OAT_POINT, SENSOR_TEMP_C)

    await asyncio.sleep(0.6)

    # 2 / 2b. MQTT telemetry OAT = 30, protocol tag bacnet
    oat_mqtt = _payload_on_topic(
        capmqtt.messages,
        telemetry_topic(MQTT_PREFIX, SENSOR_ID, OAT_POINT),
    )
    assert oat_mqtt is not None
    assert float(oat_mqtt["present_value"]) == SENSOR_TEMP_C
    assert oat_mqtt["protocol"] == "bacnet"

    # 3. Controller: fan ON, speed 75, valve 80 (lab E2E: GET /api/devices/1001)
    ahu = field_sim_plant.snapshot(EQUIPMENT_ID)
    assert ahu[SUPPLY_FAN_ENABLE] is True
    assert ahu[FAN_SPEED] == 75.0
    assert ahu[COOLING_VALVE] == 80.0

    # 4. Observer reads OAT (lab E2E: GET /api/devices/5001)
    assert field_sim_plant.read(SENSOR_ID, OAT_POINT) == SENSOR_TEMP_C

    # 4b omitted: GET /ui Dashboard — not part of field_sim

    # 5. BMS MQTT command valve = 90
    capmqtt.publish(
        topic=command_topic(MQTT_PREFIX, EQUIPMENT_ID),
        payload=json.dumps(
            {
                "device_id": EQUIPMENT_ID,
                "point_name": COOLING_VALVE,
                "value": BMS_VALVE_COMMAND,
            }
        ),
    )

    await asyncio.sleep(0.6)

    # 6. write_status success, value 90
    status = _payload_on_topic(
        capmqtt.messages,
        write_status_topic(MQTT_PREFIX, EQUIPMENT_ID, COOLING_VALVE),
    )
    assert status is not None
    assert status["success"] is True
    assert float(status["value"]) == BMS_VALVE_COMMAND

    # 7. Equipment valve = 90 (lab E2E: GET /api/devices/1001)
    assert field_sim_plant.read(EQUIPMENT_ID, COOLING_VALVE) == BMS_VALVE_COMMAND

    # 8. MQTT telemetry valve = 90
    valve_mqtt = _payload_on_topic(
        capmqtt.messages,
        telemetry_topic(MQTT_PREFIX, EQUIPMENT_ID, COOLING_VALVE),
    )
    assert valve_mqtt is not None
    assert float(valve_mqtt["present_value"]) == BMS_VALVE_COMMAND
