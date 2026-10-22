"""BACnet object map for field_sim (no BAC0 required)."""

from field_sim.bacnet import (
    from_bac0_present,
    infer_object_type,
    load_bacnet_specs,
    object_identifier,
    to_bac0_present,
    values_equal,
)
from field_sim.plant import EQUIPMENT_ID, OAT_POINT, SENSOR_ID, FieldPlant


def test_infer_sensor_and_equipment_types():
    assert infer_object_type("sensor", 15.0) == "analogInput"
    assert infer_object_type("equipment", True) == "binaryOutput"
    assert infer_object_type("equipment", 80.0) == "analogOutput"


def test_yaml_bacnet_map_matches_devices_yaml():
    plant = FieldPlant()
    specs = {s.device_id: s for s in load_bacnet_specs(plant)}
    oat = specs[SENSOR_ID].object_for(OAT_POINT)
    assert oat.object_type == "analogInput"
    assert oat.instance == 1
    assert object_identifier(oat) == "analogInput 1"

    valve = specs[EQUIPMENT_ID].object_for("AHU-01/CoolingValve")
    assert valve.object_type == "analogOutput"
    assert valve.instance == 1
    fan = specs[EQUIPMENT_ID].object_for("AHU-01/SupplyFanEnable")
    assert fan.object_type == "binaryOutput"
    assert object_identifier(fan) == "binaryOutput 1"


def test_bac0_present_value_roundtrip():
    plant = FieldPlant()
    valve = load_bacnet_specs(plant)[1].object_for("AHU-01/CoolingValve")
    encoded = to_bac0_present(valve, 90.0)
    assert encoded == 90.0
    assert from_bac0_present(valve, encoded, 0.0) == 90.0
    assert values_equal(valve, 90.0, 90.0)

    fan = load_bacnet_specs(plant)[1].object_for("AHU-01/SupplyFanEnable")
    assert to_bac0_present(fan, True) == "active"
    assert from_bac0_present(fan, "active", False) is True
    assert values_equal(fan, True, "active")
