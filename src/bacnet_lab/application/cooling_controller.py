"""Simulated DDC: if outdoor temp > 28°C then AHU cooling ON.

YAML devices only expose points. This service is the controller program.
It subscribes to point changes and writes AHU/TSTAT outputs.
"""

from __future__ import annotations

import logging

from bacnet_lab.domain.events import DomainEvent, PointValueChanged
from bacnet_lab.ports.event_publisher import EventPublisherPort

logger = logging.getLogger(__name__)

OAT_DEVICE_ID = 5001
TSTAT_DEVICE_ID = 3001
AHU_DEVICE_ID = 1001

OUTDOOR_TEMP_POINT = "OAT-01/OutdoorTemp"
TSTAT_MODE_POINT = "TSTAT-01/Mode"
SUPPLY_SETPOINT = "AHU-01/SupplyAirTempSetpoint"
SUPPLY_FAN_ENABLE = "AHU-01/SupplyFanEnable"
FAN_SPEED = "AHU-01/FanSpeed"
COOLING_VALVE = "AHU-01/CoolingValve"

OUTDOOR_TEMP_THRESHOLD_C = 28.0
TSTAT_MODE_COOL = 2
TSTAT_MODE_AUTO = 4
COOLING_SETPOINT_C = 22.0
FAN_SPEED_ON = 75.0
COOLING_VALVE_ON = 80.0


def cooling_should_run(outdoor_temp_c: float, threshold_c: float = OUTDOOR_TEMP_THRESHOLD_C) -> bool:
    return outdoor_temp_c > threshold_c


class OutdoorTempCoolingController:
    """AHU cooling sequence driven by OAT-01 (virtual DDC)."""

    def __init__(self, device_service: object, event_publisher: EventPublisherPort) -> None:
        self._device_service = device_service
        event_publisher.subscribe(self._on_event)
        logger.info(
            "OutdoorTempCoolingController started (threshold=%s°C)",
            OUTDOOR_TEMP_THRESHOLD_C,
        )

    async def _on_event(self, event: DomainEvent) -> None:
        if not isinstance(event, PointValueChanged):
            return
        if event.device_id != OAT_DEVICE_ID or event.point_name != OUTDOOR_TEMP_POINT:
            return
        try:
            outdoor_temp = float(event.new_value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            logger.warning("Ignoring non-numeric outdoor temp: %s", event.new_value)
            return
        await self._apply(outdoor_temp)

    async def _apply(self, outdoor_temp_c: float) -> None:
        ds = self._device_service
        if cooling_should_run(outdoor_temp_c):
            logger.info("Outdoor temp %.1f°C > %.1f°C — cooling ON", outdoor_temp_c, OUTDOOR_TEMP_THRESHOLD_C)
            await ds.write_point_by_name(TSTAT_DEVICE_ID, TSTAT_MODE_POINT, TSTAT_MODE_COOL)
            await ds.write_point_by_name(AHU_DEVICE_ID, SUPPLY_SETPOINT, COOLING_SETPOINT_C)
            await ds.write_point_by_name(AHU_DEVICE_ID, SUPPLY_FAN_ENABLE, True)
            await ds.write_point_by_name(AHU_DEVICE_ID, FAN_SPEED, FAN_SPEED_ON)
            await ds.write_point_by_name(AHU_DEVICE_ID, COOLING_VALVE, COOLING_VALVE_ON)
            return

        logger.info("Outdoor temp %.1f°C <= %.1f°C — cooling OFF", outdoor_temp_c, OUTDOOR_TEMP_THRESHOLD_C)
        await ds.write_point_by_name(TSTAT_DEVICE_ID, TSTAT_MODE_POINT, TSTAT_MODE_AUTO)
        await ds.write_point_by_name(AHU_DEVICE_ID, SUPPLY_FAN_ENABLE, False)
        await ds.write_point_by_name(AHU_DEVICE_ID, FAN_SPEED, 0.0)
        await ds.write_point_by_name(AHU_DEVICE_ID, COOLING_VALVE, 0.0)
