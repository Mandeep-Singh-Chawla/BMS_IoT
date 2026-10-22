# API Reference

BACnet Lab exposes a REST API on the configured HTTP port (default: 8080). All endpoints return JSON.

If HTTP Basic Auth is enabled (see [Configuration](configuration.md)), include credentials with every request:

```bash
curl -u admin:password http://localhost:8080/api/devices
```

## Health

### GET /api/health

Returns the application status.

```bash
curl http://localhost:8080/api/health
```

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "devices_count": 7,
  "active_scenarios": 0
}
```

## Devices

### GET /api/devices

List all simulated devices.

```bash
curl http://localhost:8080/api/devices
```

**Response:**

```json
[
  {
    "device_id": 1001,
    "name": "AHU-01",
    "description": "Air Handling Unit - Main Building",
    "status": "online",
    "point_count": 12
  },
  ...
]
```

### GET /api/devices/{device_id}

Get device details including all BACnet points.

```bash
curl http://localhost:8080/api/devices/1001
```

**Response:**

```json
{
  "device_id": 1001,
  "name": "AHU-01",
  "description": "Air Handling Unit - Main Building",
  "status": "online",
  "points": [
    {
      "object_type": "analogInput",
      "object_instance": 1,
      "object_name": "AHU-01/SupplyAirTemp",
      "description": "Supply air temperature",
      "present_value": 22.5,
      "units": "degreesCelsius"
    },
    ...
  ]
}
```

### PUT /api/devices/{device_id}/points

Write a value to a BACnet point. You can identify the point by name or by object type and instance.

**By point name:**

```bash
curl -X PUT http://localhost:8080/api/devices/1001/points \
  -H "Content-Type: application/json" \
  -d '{"point_name": "AHU-01/CoolingValve", "value": 80.0}'
```

**By object type and instance:**

```bash
curl -X PUT http://localhost:8080/api/devices/1001/points \
  -H "Content-Type: application/json" \
  -d '{"object_type": "analogOutput", "object_instance": 1, "value": 80.0}'
```

**Response:** `200 OK` with the updated point.

## Scenarios

### GET /api/scenarios

List all available simulation scenarios.

```bash
curl http://localhost:8080/api/scenarios
```

**Response:**

```json
[
  {
    "id": "hvac_day_cycle",
    "name": "HVAC Day/Night Cycle",
    "description": "Compressed 24h HVAC simulation",
    "status": "stopped"
  },
  ...
]
```

### POST /api/scenarios/{scenario_id}/start

Start a scenario. Optionally pass parameters.

```bash
curl -X POST http://localhost:8080/api/scenarios/hvac_day_cycle/start \
  -H "Content-Type: application/json" \
  -d '{"params": {}}'
```

**Response:** `200 OK` with the scenario status.

### POST /api/scenarios/{scenario_id}/stop

Stop a running scenario.

```bash
curl -X POST http://localhost:8080/api/scenarios/hvac_day_cycle/stop
```

**Response:** `200 OK` with the scenario status.

## Webhook Endpoints

See [Webhooks documentation](webhooks.md) for full details on event delivery, signatures, and payload examples.

### GET /api/endpoints

List all registered webhook endpoints.

```bash
curl http://localhost:8080/api/endpoints
```

### POST /api/endpoints

Create a new webhook endpoint.

```bash
curl -X POST http://localhost:8080/api/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/webhook",
    "event_types": ["point_value_changed", "alarm_raised"]
  }'
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | URL to receive webhook POST requests |
| `event_types` | string[] | no | Event types to subscribe to. Omit to receive all events. |

**Response (201):** Returns the endpoint with the auto-generated `secret`. Store it securely.

### DELETE /api/endpoints/{endpoint_id}

Delete a webhook endpoint.

```bash
curl -X DELETE http://localhost:8080/api/endpoints/ep-a1b2c3d4
```

### POST /api/endpoints/{endpoint_id}/test

Send a test event to verify connectivity.

```bash
curl -X POST http://localhost:8080/api/endpoints/ep-a1b2c3d4/test
```

Returns `200` on success, `502` if delivery fails.

## Events

### GET /api/events

Get recent events.

```bash
curl http://localhost:8080/api/events
```

**Response:**

```json
[
  {
    "id": "evt-001",
    "event_type": "point_value_changed",
    "timestamp": "2026-03-09T14:30:00+00:00",
    "payload": { ... },
    "delivered": true
  },
  ...
]
```

### GET /api/alarms

Get recent alarms.

```bash
curl http://localhost:8080/api/alarms
```

**Response:**

```json
[
  {
    "id": "alm-001",
    "device_id": 1001,
    "point_name": "AHU-01/SupplyAirTemp",
    "severity": "high",
    "message": "Supply air temperature exceeded 35°C",
    "raised_at": "2026-03-09T14:32:00+00:00",
    "cleared_at": null
  },
  ...
]
```
