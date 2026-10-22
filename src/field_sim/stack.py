"""Start plant + DDC + MQTT gateway. Optional BACnet/IP. MQTT is required.

    from field_sim.stack import start_field_sim

    sim = start_field_sim()  # localhost:1883
    sim.plant.write(5001, "OAT-01/OutdoorTemp", 30.0)
    sim.stop()

    sim = start_field_sim(bacnet=True)  # also BAC0 devices on UDP 47820+
    sim.bacnet.address(5001)  # 127.0.0.1:47820

Requires paho-mqtt and a broker (Mosquitto) on host:port.
BACnet extra: pip install BAC0
"""

from __future__ import annotations

from field_sim.controller import OutdoorTempController
from field_sim.mqtt_bridge import MqttBridge
from field_sim.plant import FieldPlant


class FieldSim:
    """Running field_sim stack. Unpack as ``plant, mqtt = start_field_sim()``."""

    def __init__(self, plant: FieldPlant, mqtt: MqttBridge, bacnet=None) -> None:
        self.plant = plant
        self.mqtt = mqtt
        self.bacnet = bacnet

    def stop(self) -> None:
        if self.bacnet is not None:
            self.bacnet.stop()
        self.mqtt.stop()

    def __iter__(self):
        yield self.plant
        yield self.mqtt


def start_field_sim(
    *,
    mqtt_host: str = "localhost",
    mqtt_port: int = 1883,
    prefix: str = "bacnet",
    protocol: str | None = None,
    bacnet: bool = False,
    bacnet_ip: str = "127.0.0.1",
    bacnet_port_start: int = 47820,
) -> FieldSim:
    """Always starts MqttBridge. Optional BAC0 devices when ``bacnet=True``.

    Raises if the MQTT broker is unreachable. BACnet needs ``pip install BAC0``.
    """
    if protocol is None:
        protocol = "bacnet" if bacnet else "field-sim"
    plant = FieldPlant()
    OutdoorTempController(plant)
    mqtt = MqttBridge(
        plant,
        host=mqtt_host,
        port=mqtt_port,
        prefix=prefix,
        protocol=protocol,
    )
    mqtt.start()
    mqtt.wait_connected()
    network = None
    if bacnet:
        from field_sim.bacnet import BacnetNetwork

        network = BacnetNetwork(plant, ip=bacnet_ip, port_start=bacnet_port_start)
        network.start()
    return FieldSim(plant, mqtt, network)
