"""Portable BMS field simulator: sensor + DDC + equipment + MQTT, optional BACnet.

MQTT is required for the full stack (paho-mqtt + Mosquitto or any broker).
BACnet/IP is optional (BAC0) and does not import bacnet_lab.

    from field_sim import start_field_sim

    sim = start_field_sim()  # MQTT only
    sim.plant.write(5001, "OAT-01/OutdoorTemp", 30.0)
    sim.stop()

    sim = start_field_sim(bacnet=True)  # MQTT + BACnet/IP
    sim.stop()

Plant-only (no broker) is still available for unit-testing the DDC rule.
"""

from field_sim.bacnet import (
    BacnetNetwork,
    infer_object_type,
    load_bacnet_specs,
    object_identifier,
)
from field_sim.controller import OutdoorTempController, cooling_should_run
from field_sim.mqtt_bridge import MqttBridge, command_topic, telemetry_topic, write_status_topic
from field_sim.plant import (
    EQUIPMENT_ID,
    OAT_POINT,
    SENSOR_ID,
    FieldPlant,
    load_devices_yaml,
)
from field_sim.stack import FieldSim, start_field_sim

__all__ = [
    "EQUIPMENT_ID",
    "OAT_POINT",
    "SENSOR_ID",
    "BacnetNetwork",
    "FieldPlant",
    "FieldSim",
    "MqttBridge",
    "OutdoorTempController",
    "command_topic",
    "cooling_should_run",
    "infer_object_type",
    "load_bacnet_specs",
    "load_devices_yaml",
    "object_identifier",
    "start_field_sim",
    "telemetry_topic",
    "write_status_topic",
]
