"""Full BMS IoT flow: Sensor → DDC → Network → BMS → Dashboard → Equipment.

If outdoor temp > 28°C, HVAC turns ON. Input: OAT-01 current temp = 30°C.

The cooling rule lives in OutdoorTempCoolingController (src/), not in this test.

Production protocols this test actually uses:
  BMS API / dashboard:  HTTP REST JSON + HTTP HTML (httpx → FastAPI)
  Analytics:            HTTP POST webhooks with HMAC-SHA256
  Field / gateway:      FakeNetwork (in-memory). Live BACnet/IP is BAC0Engine
                        and is not started in this pytest on purpose.

Sensor:     config/devices/temp_sensor_01.yaml (OAT-01)
Controller: src/bacnet_lab/application/cooling_controller.py
Equipment:  config/devices/ahu_01.yaml (AHU-01)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import socket
import sys
from pathlib import Path

import pytest
import uvicorn
from fastapi import FastAPI, Request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_api import make_test_client  # noqa: E402

OAT_DEVICE_ID = 5001
TSTAT_DEVICE_ID = 3001
AHU_DEVICE_ID = 1001

OUTDOOR_TEMP_POINT = "OAT-01/OutdoorTemp"
TSTAT_MODE_POINT = "TSTAT-01/Mode"
SUPPLY_SETPOINT = "AHU-01/SupplyAirTempSetpoint"
SUPPLY_FAN_ENABLE = "AHU-01/SupplyFanEnable"
FAN_SPEED = "AHU-01/FanSpeed"
COOLING_VALVE = "AHU-01/CoolingValve"

TSTAT_MODE_COOL = 2
CURRENT_TEMP_C = 30.0
COOLING_SETPOINT_C = 22.0


@pytest.fixture
async def client():
    async with make_test_client() as ac:
        yield ac


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _webhook_app(received: list[dict]) -> FastAPI:
    app = FastAPI()

    @app.post("/webhook")
    async def webhook(request: Request) -> dict:
        raw = await request.body()
        received.append(
            {
                "raw": raw,
                "signature": request.headers.get("x-bacnetlab-signature", ""),
                "event": request.headers.get("x-bacnetlab-event", ""),
                "json": json.loads(raw),
            }
        )
        return {"status": "ok"}

    return app


async def _start_webhook_server(app: FastAPI, port: int):
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    for _ in range(100):
        if server.started:
            break
        await asyncio.sleep(0.05)
    else:
        task.cancel()
        raise RuntimeError("Webhook HTTP server did not start")
    return server, task


@pytest.fixture
async def analytics_webhook(client):
    """Production analytics hop: HMAC-signed HTTP POST webhooks."""
    received: list[dict] = []
    port = _free_port()
    server, task = await _start_webhook_server(_webhook_app(received), port)
    url = f"http://127.0.0.1:{port}/webhook"
    try:
        created = await client.post(
            "/api/endpoints",
            json={"url": url, "event_types": ["point_value_changed"]},
        )
        assert created.status_code == 201, created.text
        yield received, created.json()["secret"]
    finally:
        server.should_exit = True
        await task


def _point_map(device_payload: dict) -> dict:
    return {p["object_name"]: p["present_value"] for p in device_payload["points"]}


async def _write_point(client, device_id: int, point_name: str, value):
    resp = await client.put(
        f"/api/devices/{device_id}/points",
        json={"point_name": point_name, "value": value},
    )
    assert resp.status_code == 200, resp.text
    return resp


async def _read_device(client, device_id: int) -> dict:
    resp = await client.get(f"/api/devices/{device_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _verify_webhook_hmac(secret: str, raw: bytes, signature_header: str) -> None:
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert signature_header == f"sha256={expected}"


def _webhook_point_values(received: list[dict]) -> dict:
    values = {}
    for item in received:
        payload = item["json"].get("payload") or {}
        name = payload.get("point_name")
        if name:
            values[name] = payload.get("new_value")
    return values


@pytest.mark.asyncio
async def test_full_bms_flow_hvac_on_when_outdoor_temp_is_30(client, analytics_webhook):
    """Sensor → Controller → Gateway → BMS → Dashboard → Command → Equipment."""
    received, webhook_secret = analytics_webhook

    # --- 7. Equipment starts OFF so later ON is not a YAML default ---
    await _write_point(client, AHU_DEVICE_ID, SUPPLY_FAN_ENABLE, False)
    await _write_point(client, AHU_DEVICE_ID, FAN_SPEED, 0.0)
    await _write_point(client, AHU_DEVICE_ID, COOLING_VALVE, 0.0)

    # --- 1. Sensor / Field Device (OAT-01) via HTTP REST ---
    await _write_point(client, OAT_DEVICE_ID, OUTDOOR_TEMP_POINT, CURRENT_TEMP_C)
    oat = _point_map(await _read_device(client, OAT_DEVICE_ID))
    current_temp = oat[OUTDOOR_TEMP_POINT]
    assert current_temp == CURRENT_TEMP_C

    # --- 2. Controller (DDC): OutdoorTempCoolingController applied the rule ---
    tstat = _point_map(await _read_device(client, TSTAT_DEVICE_ID))
    ahu_after_ddc = _point_map(await _read_device(client, AHU_DEVICE_ID))
    assert tstat[TSTAT_MODE_POINT] == TSTAT_MODE_COOL
    assert ahu_after_ddc[SUPPLY_SETPOINT] == COOLING_SETPOINT_C
    assert ahu_after_ddc[SUPPLY_FAN_ENABLE] is True
    assert ahu_after_ddc[FAN_SPEED] == 75.0
    assert ahu_after_ddc[COOLING_VALVE] == 80.0

    # --- 3. Gateway / Network: FakeNetwork present values (not live BACnet/IP) ---
    oat_on_network = _point_map(await _read_device(client, OAT_DEVICE_ID))
    assert oat_on_network[OUTDOOR_TEMP_POINT] == CURRENT_TEMP_C

    # --- 4. BMS Platform: HTTP REST supervisory read ---
    health = await client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["devices_count"] == 7

    devices = await client.get("/api/devices")
    assert devices.status_code == 200
    names = {d["name"] for d in devices.json()}
    assert {"OAT-01", "TSTAT-01", "AHU-01"}.issubset(names)

    # --- 5. Dashboard (HTTP HTML) + Analytics (HMAC HTTP webhooks) ---
    dashboard = await client.get("/ui")
    assert dashboard.status_code == 200
    assert "text/html" in dashboard.headers["content-type"]
    assert "Dashboard" in dashboard.text

    devices_page = await client.get("/ui/devices")
    assert devices_page.status_code == 200
    assert "OAT-01" in devices_page.text
    assert "AHU-01" in devices_page.text

    oat_points = await client.get(f"/ui/partials/points/{OAT_DEVICE_ID}")
    assert oat_points.status_code == 200
    assert OUTDOOR_TEMP_POINT in oat_points.text

    events = await client.get("/api/events")
    assert events.status_code == 200
    event_points = {e["payload"].get("point_name") for e in events.json()}
    assert OUTDOOR_TEMP_POINT in event_points

    alarms = await client.get("/api/alarms")
    assert alarms.status_code == 200

    assert received, "expected HMAC-signed HTTP webhook deliveries"
    for item in received:
        assert item["event"] == "point_value_changed"
        _verify_webhook_hmac(webhook_secret, item["raw"], item["signature"])
    webhook_values = _webhook_point_values(received)
    assert webhook_values[OUTDOOR_TEMP_POINT] == CURRENT_TEMP_C

    # --- 6–7. Equipment: controller already commanded AHU-01 ON ---
    ahu = _point_map(await _read_device(client, AHU_DEVICE_ID))
    assert ahu[SUPPLY_FAN_ENABLE] is True
    assert ahu[FAN_SPEED] == 75.0
    assert ahu[COOLING_VALVE] == 80.0

    ahu_points_ui = await client.get(f"/ui/partials/points/{AHU_DEVICE_ID}")
    assert ahu_points_ui.status_code == 200
    assert COOLING_VALVE in ahu_points_ui.text
    assert SUPPLY_FAN_ENABLE in ahu_points_ui.text

    webhook_values = _webhook_point_values(received)
    assert webhook_values[SUPPLY_FAN_ENABLE] is True
    assert webhook_values[COOLING_VALVE] == 80.0
