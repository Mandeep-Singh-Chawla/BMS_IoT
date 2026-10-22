"""In-memory sensor + equipment plant (no BAC0 required).

Copy this package to another project. Optional BACnet/IP is in bacnet.py.
The write/read API stays the same either way.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path

PointValue = bool | int | float | str
WriteListener = Callable[[int, str, PointValue, PointValue], None]

DEFAULT_DEVICES: dict[int, dict[str, PointValue]] = {
    5001: {"OAT-01/OutdoorTemp": 15.0},
    1001: {
        "AHU-01/SupplyFanEnable": False,
        "AHU-01/FanSpeed": 0.0,
        "AHU-01/CoolingValve": 0.0,
        "AHU-01/SupplyAirTempSetpoint": 22.0,
    },
}

SENSOR_ID = 5001
EQUIPMENT_ID = 1001
OAT_POINT = "OAT-01/OutdoorTemp"


def load_devices_yaml(path: str | Path | None = None) -> dict[int, dict[str, PointValue]]:
    """Load device points from devices.yaml, or return built-in defaults."""
    yaml_path = Path(path) if path else Path(__file__).with_name("devices.yaml")
    if not yaml_path.exists():
        return deepcopy(DEFAULT_DEVICES)
    try:
        import yaml
    except ImportError:
        return deepcopy(DEFAULT_DEVICES)

    data = yaml.safe_load(yaml_path.read_text()) or {}
    devices: dict[int, dict[str, PointValue]] = {}
    for section in ("sensor", "equipment"):
        block = data.get(section) or {}
        device_id = int(block["device_id"])
        devices[device_id] = dict(block.get("points") or {})
    return devices or deepcopy(DEFAULT_DEVICES)


class FieldPlant:
    """Virtual field side: write a sensor, read equipment, notify listeners."""

    def __init__(self, devices: dict[int, dict[str, PointValue]] | None = None) -> None:
        self._devices = deepcopy(devices) if devices is not None else load_devices_yaml()
        self._listeners: list[WriteListener] = []
        self._lock = threading.Lock()

    def on_write(self, listener: WriteListener) -> None:
        self._listeners.append(listener)

    def write(self, device_id: int, point_name: str, value: PointValue) -> PointValue:
        with self._lock:
            points = self._devices.get(device_id)
            if points is None or point_name not in points:
                raise KeyError(f"Unknown point {device_id}/{point_name}")
            old = points[point_name]
            points[point_name] = value
        for listener in list(self._listeners):
            listener(device_id, point_name, old, value)
        return value

    def read(self, device_id: int, point_name: str) -> PointValue:
        with self._lock:
            points = self._devices.get(device_id)
            if points is None or point_name not in points:
                raise KeyError(f"Unknown point {device_id}/{point_name}")
            return points[point_name]

    def snapshot(self, device_id: int) -> dict[str, PointValue]:
        with self._lock:
            points = self._devices.get(device_id)
            if points is None:
                raise KeyError(f"Unknown device {device_id}")
            return dict(points)

    def as_dict(self) -> dict[int, dict[str, PointValue]]:
        with self._lock:
            return deepcopy(self._devices)
