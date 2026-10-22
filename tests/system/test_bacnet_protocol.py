"""Optional BACnet/IP system tests (not part of default pytest).

Starts BAC0Engine (BAC0.lite / BACpypes3). Does not use FakeNetwork.

A second in-process BAC0 client is not started: BAC0's task manager is
one-loop-per-process, and macOS cannot bind 127.0.0.255 for broadcast.
Assert BACnet object presentValue on the local lite instances instead
(same approach as tests/system/test_field_sim_bacnet.py).

Outdoor analogInput is not commandable on the wire, so the test injects
30°C through DeviceService (same as a writable sensor sim) and asserts
AHU cooling on the BACnet objects.

Run:
  RUN_BACNET_SYSTEM_TESTS=1 pytest tests/system/test_bacnet_protocol.py -v
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from bacnet_lab.adapters.bacnet.device_factory import load_device_from_yaml
from bacnet_lab.adapters.bacnet.engine import BAC0Engine
from bacnet_lab.adapters.event_bus.in_process import InProcessEventPublisher
from bacnet_lab.adapters.persistence.migrations import run_migrations
from bacnet_lab.adapters.persistence.sqlite_repos import SqliteDeviceRepository
from bacnet_lab.application.cooling_controller import OutdoorTempCoolingController
from bacnet_lab.application.device_service import DeviceService

pytestmark = [
    pytest.mark.bacnet,
    pytest.mark.skipif(
        os.getenv("RUN_BACNET_SYSTEM_TESTS") != "1",
        reason="Set RUN_BACNET_SYSTEM_TESTS=1 to run BACnet/IP system tests",
    ),
]

AHU_DEVICE_ID = 1001
OAT_DEVICE_ID = 5001
PORT_START = 47900


def _local_present(engine: BAC0Engine, device_id: int, object_name: str):
    instance = engine._instances[device_id]
    return instance[object_name].presentValue


@pytest.fixture
async def bacnet_lab_stack():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = BAC0Engine(ip="127.0.0.1")
    try:
        await run_migrations(db_path)
        event_publisher = InProcessEventPublisher()
        device_service = DeviceService(
            device_repo=SqliteDeviceRepository(db_path),
            network=engine,
            event_publisher=event_publisher,
            bacnet_port_start=PORT_START,
        )
        OutdoorTempCoolingController(device_service, event_publisher)
        devices = [
            load_device_from_yaml(Path("config/devices/ahu_01.yaml")),
            load_device_from_yaml(Path("config/devices/thermostat_01.yaml")),
            load_device_from_yaml(Path("config/devices/temp_sensor_01.yaml")),
        ]
        await device_service.initialize_devices(devices)
        yield device_service, engine
    finally:
        await engine.stop_all()
        os.unlink(db_path)


@pytest.mark.asyncio
async def test_bacnet_read_outdoor_temp_and_cooling_after_rule(bacnet_lab_stack):
    """Inject 30°C on OAT, then read AHU cooling from local BACnet objects."""
    device_service, engine = bacnet_lab_stack
    await device_service.write_point_by_name(OAT_DEVICE_ID, "OAT-01/OutdoorTemp", 30.0)

    outdoor = _local_present(engine, OAT_DEVICE_ID, "OAT-01/OutdoorTemp")
    cooling = _local_present(engine, AHU_DEVICE_ID, "AHU-01/CoolingValve")
    fan_speed = _local_present(engine, AHU_DEVICE_ID, "AHU-01/FanSpeed")

    assert float(outdoor) == pytest.approx(30.0)
    assert float(cooling) == pytest.approx(80.0)
    assert float(fan_speed) == pytest.approx(75.0)
