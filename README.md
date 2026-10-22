# BMS IoT

Tests and a lab for a BMS / IoT app that uses BACnet and MQTT. Virtual HVAC points (outdoor sensor + AHU), a local cooling rule, an MQTT gateway, and optional BACnet/IP. A REST API and dashboard sit on the same plant.

## What you need

- macOS
- Python 3.11 or newer
- Docker Desktop, running (starts Mosquitto for MQTT tests)
- Port 1883 free

BACnet/IP system tests are optional. They need extra UDP ports and `BAC0`. Most tests do not start BACnet devices.

## Setup

```bash
git clone https://github.com/Mandeep-Singh-Chawla/BMS_IoT.git
cd BMS_IoT
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv sync --extra dev
```

## Run the tests

```bash
pytest tests -v
```

You should see the default suite pass (BACnet/IP system tests stay skipped). Docker starts the MQTT broker for the gateway and E2E tests.

| Test | What it checks |
|------|----------------|
| `test_e2e_field_sim_positive_flow` | Outdoor temp 30 °C → MQTT telemetry → cooling on → BMS command sets valve to 90 |
| `test_e2e_bms_positive_flow` | Same flow through the lab REST API and MQTT gateway |
| `test_bacnet_mqtt_gateway` | Point change publishes telemetry; MQTT command writes the point and returns status |
| `test_hvac_outdoor_temp_control` | Local rule: outdoor temp above 28 °C starts AHU cooling |
| `test_field_sim` / `test_cooling_controller` | Plant write/read and DDC sequence without a broker |
| `test_api` | REST devices, points, dashboard |
| `test_sqlite_repos` | Device, endpoint, event, and alarm persistence |

Optional BACnet/IP (real BAC0 devices):

```bash
RUN_BACNET_SYSTEM_TESTS=1 pytest tests/system -v
```

## Run the lab on its own

```bash
# terminal 1 — MQTT broker (or use Docker Mosquitto)
mosquitto -p 1883

# terminal 2
export BACNET_LAB_MQTT_ENABLED=1
python -m bacnet_lab
```

The API and dashboard listen on [http://localhost:8080](http://localhost:8080). Open [http://localhost:8080/ui](http://localhost:8080/ui).

```bash
curl -X PUT http://localhost:8080/api/devices/5001/points \
  -H "Content-Type: application/json" \
  -d '{"point_name":"OAT-01/OutdoorTemp","value":30}'
```

MQTT topics (prefix `bacnet`):

- `bacnet/{device_id}/telemetry/{point}`
- `bacnet/{device_id}/command`
- `bacnet/{device_id}/write_status/{point}`

## Portable field simulator

`src/field_sim` is the field + gateway only (no FastAPI). Copy that folder into another project.

```bash
mosquitto -p 1883
python -m field_sim 30
```

Add `--bacnet` to also expose the same points as BACnet/IP devices.

## License

MIT. Copyright (c) 2026 Mandeep Singh Chawla.
