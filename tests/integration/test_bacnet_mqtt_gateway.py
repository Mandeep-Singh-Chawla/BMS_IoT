"""BACnet → MQTT gateway tests using pytest-mqtt (Mosquitto broker).

Simulates a field gateway: BACnet point changes are published to MQTT,
and MQTT commands write back to BACnet points.

Requires: pip install -e '.[dev]'  (includes pytest-mqtt)
Docs: https://github.com/mqtt-tools/pytest-mqtt

Local app note: MQTT is off by default. Enable with BACNET_LAB_MQTT_ENABLED=1
and a broker on BACNET_LAB_MQTT_HOST:BACNET_LAB_MQTT_PORT.
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

OAT_DEVICE_ID = 5001
OUTDOOR_TEMP_POINT = "OAT-01/OutdoorTemp"
CURRENT_TEMP_C = 30.0
MQTT_PREFIX = "bacnet"


@pytest.fixture
async def mqtt_app_client(mosquitto):
    async with make_test_client(mqtt_broker=("localhost", 1883), mqtt_topic_prefix=MQTT_PREFIX) as ac:
        yield ac


def _find_json_on_topic(messages, topic: str):
    for msg in messages:
        if getattr(msg, "topic", None) == topic:
            return json.loads(msg.payload)
    return None


def _find_telemetry(messages, device_id: int, point_name: str):
    return _find_json_on_topic(messages, telemetry_topic(MQTT_PREFIX, device_id, point_name))


def test_command_topic_helper_matches_subscribe_pattern():
    assert command_topic(MQTT_PREFIX, "+") == f"{MQTT_PREFIX}/+/command"
    assert command_topic(MQTT_PREFIX, OAT_DEVICE_ID) == f"{MQTT_PREFIX}/{OAT_DEVICE_ID}/command"


@pytest.mark.capmqtt_decode_utf8
@pytest.mark.asyncio
async def test_bacnet_point_change_published_to_mqtt(mqtt_app_client, capmqtt):
    """BACnet write (HTTP) → gateway → MQTT telemetry topic."""
    resp = await mqtt_app_client.put(
        f"/api/devices/{OAT_DEVICE_ID}/points",
        json={"point_name": OUTDOOR_TEMP_POINT, "value": CURRENT_TEMP_C},
    )
    assert resp.status_code == 200

    await asyncio.sleep(0.5)

    payload = _find_telemetry(capmqtt.messages, OAT_DEVICE_ID, OUTDOOR_TEMP_POINT)
    assert payload is not None
    assert payload["device_id"] == OAT_DEVICE_ID
    assert payload["point_name"] == OUTDOOR_TEMP_POINT
    assert float(payload["present_value"]) == CURRENT_TEMP_C
    assert payload["protocol"] == "bacnet"


@pytest.mark.capmqtt_decode_utf8
@pytest.mark.asyncio
async def test_mqtt_command_writes_bacnet_point_and_publishes_status(mqtt_app_client, capmqtt):
    """MQTT command → gateway → BACnet point + write_status success."""
    capmqtt.publish(
        topic=command_topic(MQTT_PREFIX, OAT_DEVICE_ID),
        payload=json.dumps(
            {
                "device_id": OAT_DEVICE_ID,
                "point_name": OUTDOOR_TEMP_POINT,
                "value": CURRENT_TEMP_C,
            }
        ),
    )

    await asyncio.sleep(0.5)

    resp = await mqtt_app_client.get(f"/api/devices/{OAT_DEVICE_ID}")
    assert resp.status_code == 200
    points = {p["object_name"]: p["present_value"] for p in resp.json()["points"]}
    assert points[OUTDOOR_TEMP_POINT] == CURRENT_TEMP_C

    payload = _find_telemetry(capmqtt.messages, OAT_DEVICE_ID, OUTDOOR_TEMP_POINT)
    assert payload is not None
    assert float(payload["present_value"]) == CURRENT_TEMP_C

    status = _find_json_on_topic(
        capmqtt.messages,
        write_status_topic(MQTT_PREFIX, OAT_DEVICE_ID, OUTDOOR_TEMP_POINT),
    )
    assert status is not None
    assert status["success"] is True
    assert float(status["value"]) == CURRENT_TEMP_C


@pytest.mark.capmqtt_decode_utf8
@pytest.mark.asyncio
async def test_mqtt_command_failure_publishes_write_status(mqtt_app_client, capmqtt):
    """Invalid point → write_status success=false on MQTT."""
    bad_point = "OAT-01/DoesNotExist"
    capmqtt.publish(
        topic=command_topic(MQTT_PREFIX, OAT_DEVICE_ID),
        payload=json.dumps(
            {
                "device_id": OAT_DEVICE_ID,
                "point_name": bad_point,
                "value": 1.0,
            }
        ),
    )

    await asyncio.sleep(0.5)

    status = _find_json_on_topic(
        capmqtt.messages,
        write_status_topic(MQTT_PREFIX, OAT_DEVICE_ID, bad_point),
    )
    assert status is not None
    assert status["success"] is False
    assert status["error"]
