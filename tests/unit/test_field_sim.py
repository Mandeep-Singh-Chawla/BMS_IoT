"""Portable field_sim: sensor inject → controller → equipment (no BAC0 / MQTT)."""

from field_sim import (
    EQUIPMENT_ID,
    OAT_POINT,
    SENSOR_ID,
    FieldPlant,
    OutdoorTempController,
    cooling_should_run,
)


def test_cooling_rule():
    assert cooling_should_run(30.0) is True
    assert cooling_should_run(28.0) is False


def test_hot_day_starts_cooling():
    plant = FieldPlant()
    OutdoorTempController(plant)
    plant.write(SENSOR_ID, OAT_POINT, 30.0)
    ahu = plant.snapshot(EQUIPMENT_ID)
    assert ahu["AHU-01/SupplyFanEnable"] is True
    assert ahu["AHU-01/FanSpeed"] == 75.0
    assert ahu["AHU-01/CoolingValve"] == 80.0
    assert plant.read(SENSOR_ID, OAT_POINT) == 30.0


def test_cool_day_stops_cooling_then_bms_override():
    plant = FieldPlant()
    OutdoorTempController(plant)
    plant.write(SENSOR_ID, OAT_POINT, 20.0)
    assert plant.read(EQUIPMENT_ID, "AHU-01/SupplyFanEnable") is False
    plant.write(EQUIPMENT_ID, "AHU-01/CoolingValve", 90.0)
    assert plant.read(EQUIPMENT_ID, "AHU-01/CoolingValve") == 90.0
