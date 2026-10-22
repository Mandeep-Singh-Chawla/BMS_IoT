"""Optional field_sim BACnet/IP tests (not part of default pytest).

Starts BacnetNetwork (BAC0.lite, no bacnet_lab) on its own event loop.
Does not start a second BAC0 client in-process (BAC0 task manager is
one-loop-per-process). External tools (YABE, another process) still talk UDP.

Run:
  RUN_BACNET_SYSTEM_TESTS=1 pytest tests/system/test_field_sim_bacnet.py -v
"""

from __future__ import annotations

import os
import time

import pytest

from field_sim.bacnet import BacnetNetwork
from field_sim.controller import OutdoorTempController
from field_sim.plant import EQUIPMENT_ID, OAT_POINT, SENSOR_ID, FieldPlant

pytestmark = [
    pytest.mark.bacnet,
    pytest.mark.skipif(
        os.getenv("RUN_BACNET_SYSTEM_TESTS") != "1",
        reason="Set RUN_BACNET_SYSTEM_TESTS=1 to run BACnet/IP system tests",
    ),
]

PORT_START = 47920


@pytest.fixture
def field_sim_bacnet():
    pytest.importorskip("BAC0")
    plant = FieldPlant()
    OutdoorTempController(plant)
    net = BacnetNetwork(plant, ip="127.0.0.1", port_start=PORT_START)
    net.start()
    try:
        yield plant, net
    finally:
        net.stop()


def test_field_sim_plant_write_updates_bacnet(field_sim_bacnet):
    """plant.write OAT → local BACnet presentValue; controller cooling on AO1."""
    plant, net = field_sim_bacnet
    plant.write(SENSOR_ID, OAT_POINT, 30.0)
    time.sleep(0.4)

    assert float(net.present_value(SENSOR_ID, OAT_POINT)) == pytest.approx(30.0)
    assert float(net.present_value(EQUIPMENT_ID, "AHU-01/CoolingValve")) == pytest.approx(
        80.0
    )
    assert net.object_identifier(SENSOR_ID, OAT_POINT) == "analogInput 1"
    assert net.address(SENSOR_ID) == f"127.0.0.1:{PORT_START}"


def test_field_sim_bacnet_write_updates_plant(field_sim_bacnet):
    """BACnet presentValue change → plant (MQTT telemetry would follow)."""
    plant, net = field_sim_bacnet
    point = "AHU-01/SupplyAirTempSetpoint"
    net.simulate_client_write(EQUIPMENT_ID, point, 19.0)
    for _ in range(20):
        if float(plant.read(EQUIPMENT_ID, point)) == pytest.approx(19.0):
            break
        time.sleep(0.1)
    else:
        pytest.fail("plant setpoint did not follow BACnet write")
