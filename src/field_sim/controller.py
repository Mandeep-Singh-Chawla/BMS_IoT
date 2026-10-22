"""DDC simulator: if outdoor temp > 28°C then AHU cooling ON.

This is the controller program. It is not a BACnet device YAML.
"""

from __future__ import annotations

from field_sim.plant import (
    EQUIPMENT_ID,
    OAT_POINT,
    SENSOR_ID,
    FieldPlant,
    PointValue,
)

THRESHOLD_C = 28.0
FAN_SPEED_ON = 75.0
COOLING_VALVE_ON = 80.0
SETPOINT_ON = 22.0


def cooling_should_run(outdoor_temp_c: float, threshold_c: float = THRESHOLD_C) -> bool:
    return outdoor_temp_c > threshold_c


class OutdoorTempController:
    """Apply cooling sequence when OAT-01/OutdoorTemp changes."""

    def __init__(self, plant: FieldPlant, threshold_c: float = THRESHOLD_C) -> None:
        self._plant = plant
        self._threshold_c = threshold_c
        plant.on_write(self._on_write)

    def _on_write(
        self,
        device_id: int,
        point_name: str,
        _old: PointValue,
        new: PointValue,
    ) -> None:
        if device_id != SENSOR_ID or point_name != OAT_POINT:
            return
        try:
            outdoor_temp = float(new)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return
        self.apply(outdoor_temp)

    def apply(self, outdoor_temp_c: float) -> None:
        plant = self._plant
        if cooling_should_run(outdoor_temp_c, self._threshold_c):
            plant.write(EQUIPMENT_ID, "AHU-01/SupplyFanEnable", True)
            plant.write(EQUIPMENT_ID, "AHU-01/FanSpeed", FAN_SPEED_ON)
            plant.write(EQUIPMENT_ID, "AHU-01/CoolingValve", COOLING_VALVE_ON)
            plant.write(EQUIPMENT_ID, "AHU-01/SupplyAirTempSetpoint", SETPOINT_ON)
            return
        plant.write(EQUIPMENT_ID, "AHU-01/SupplyFanEnable", False)
        plant.write(EQUIPMENT_ID, "AHU-01/FanSpeed", 0.0)
        plant.write(EQUIPMENT_ID, "AHU-01/CoolingValve", 0.0)
