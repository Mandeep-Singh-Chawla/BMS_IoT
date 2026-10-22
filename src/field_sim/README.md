# field_sim — portable BMS field simulator

Sensor + DDC controller + equipment + **MQTT gateway**, optional **BACnet/IP**.

Does **not** depend on `bacnet_lab`, FastAPI, or this lab’s `BAC0Engine`.
Copy the `field_sim` folder into another project.

**MQTT** is required for the full stack: `pip install paho-mqtt` and a broker (Mosquitto) on `localhost:1883`.

**BACnet** is optional: `pip install BAC0`. Same plant, extra UDP devices. No `bacnet_lab` imports.

| Role | This package |
|------|----------------|
| Sensor | device `5001` / `OAT-01/OutdoorTemp` |
| Controller | `OutdoorTempController` (`if OAT > 28°C → cooling ON`) |
| Equipment | device `1001` AHU fan / speed / valve |
| MQTT gateway | `MqttBridge` (always started by `start_field_sim()`) |
| BACnet/IP | `BacnetNetwork` when `start_field_sim(bacnet=True)` |
| Broker | Mosquitto (separate process — not this package) |

Plant is the source of truth. MQTT and BACnet are faces of the same points:

- `plant.write` → MQTT telemetry **and** BACnet `presentValue`
- MQTT command → plant → BACnet
- BACnet WriteProperty → plant → MQTT telemetry

## MQTT only (default)

```python
from field_sim import start_field_sim, SENSOR_ID, EQUIPMENT_ID, OAT_POINT

sim = start_field_sim()  # localhost:1883
sim.plant.write(SENSOR_ID, OAT_POINT, 30.0)
assert sim.plant.read(EQUIPMENT_ID, "AHU-01/CoolingValve") == 80.0
sim.stop()
```

`plant, mqtt = start_field_sim()` still works; call `sim.stop()` if BACnet is enabled so UDP devices shut down.

```bash
# terminal 1
mosquitto -p 1883

# terminal 2
python -m field_sim 30
python -m field_sim 30 --bacnet
```

Topics: `bacnet/{id}/telemetry/...`, `bacnet/{id}/command`, `bacnet/{id}/write_status/...`

## MQTT + BACnet/IP

```python
sim = start_field_sim(bacnet=True)  # devices on 127.0.0.1:47820 (OAT), :47821 (AHU)
sim.plant.write(5001, "OAT-01/OutdoorTemp", 30.0)
# BACnet ReadProperty analogInput 1 @ 127.0.0.1:47820 → 30
# analogOutput 1 @ 127.0.0.1:47821 → cooling valve 80
sim.stop()
```

Object map is in `devices.yaml` under each device’s `bacnet.objects`.

BACnet-only (no broker) for protocol tests:

```python
from field_sim import FieldPlant, OutdoorTempController, BacnetNetwork

plant = FieldPlant()
OutdoorTempController(plant)
net = BacnetNetwork(plant)
net.start()
plant.write(5001, "OAT-01/OutdoorTemp", 30.0)
assert float(net.present_value(5001, "OAT-01/OutdoorTemp")) == 30.0
net.stop()
```

## DDC unit tests only (no broker, no BAC0)

```python
from field_sim import FieldPlant, OutdoorTempController, SENSOR_ID, EQUIPMENT_ID, OAT_POINT

plant = FieldPlant()
OutdoorTempController(plant)
plant.write(SENSOR_ID, OAT_POINT, 30.0)
```

Default `start_field_sim()` is **not** BACnet-on-the-wire until you pass `bacnet=True`.
