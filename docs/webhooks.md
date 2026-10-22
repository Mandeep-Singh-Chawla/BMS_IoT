# Webhooks

BACnet Lab can push real-time events to external systems via webhooks. Each webhook endpoint receives HMAC-SHA256 signed HTTP POST requests whenever subscribed events occur.

You can manage webhook endpoints through the **web dashboard** (Endpoints tab) or the **REST API**.

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/endpoints` | List all webhook endpoints |
| `POST` | `/api/endpoints` | Create a new endpoint |
| `DELETE` | `/api/endpoints/{id}` | Delete an endpoint |
| `POST` | `/api/endpoints/{id}/test` | Send a test event to an endpoint |

### Create an endpoint

```bash
curl -X POST http://localhost:8080/api/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/webhook",
    "event_types": ["point_value_changed", "alarm_raised"]
  }'
```

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | string | yes | The URL to receive webhook POST requests |
| `event_types` | string[] | no | Event types to subscribe to. Omit or set to `null` to receive all events. |

**Response** (201):

```json
{
  "id": "ep-a1b2c3d4",
  "url": "https://example.com/webhook",
  "secret": "whsec_generated_secret_here",
  "enabled": true,
  "event_types": ["point_value_changed", "alarm_raised"],
  "failure_count": 0
}
```

The `secret` is auto-generated and returned only at creation time. Store it securely — you'll need it to verify webhook signatures.

### List endpoints

```bash
curl http://localhost:8080/api/endpoints
```

### Delete an endpoint

```bash
curl -X DELETE http://localhost:8080/api/endpoints/ep-a1b2c3d4
```

### Test an endpoint

Sends a test event to verify connectivity. Returns `200` on success or `502` if delivery fails.

```bash
curl -X POST http://localhost:8080/api/endpoints/ep-a1b2c3d4/test
```

## Event Types

| Event Type | Description |
|------------|-------------|
| `point_value_changed` | A BACnet point's present value changed |
| `device_status_changed` | A device went online, offline, or entered an error state |
| `alarm_raised` | An alarm condition was detected |
| `alarm_cleared` | A previously raised alarm was cleared |
| `scenario_started` | A simulation scenario was started |
| `scenario_stopped` | A simulation scenario was stopped |
| `telemetry_snapshot` | Periodic snapshot of all point values for a device |

## Delivery Format

Each webhook delivery is an HTTP `POST` request with a JSON body and the following headers:

| Header | Description |
|--------|-------------|
| `Content-Type` | `application/json` |
| `X-BACnetLab-Signature` | HMAC-SHA256 signature: `sha256=<hex_digest>` |
| `X-BACnetLab-Event` | The event type (e.g. `alarm_raised`) |

### Body structure

```json
{
  "id": "evt-unique-id",
  "event_type": "point_value_changed",
  "timestamp": "2026-03-09T14:30:00+00:00",
  "payload": { }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique event identifier |
| `event_type` | string | One of the event types listed above |
| `timestamp` | string | ISO 8601 timestamp of when the event occurred |
| `payload` | object | Event-specific data (see examples below) |

## Payload Examples

### point_value_changed

```json
{
  "id": "evt-001",
  "event_type": "point_value_changed",
  "timestamp": "2026-03-09T14:30:00+00:00",
  "payload": {
    "device_id": 1001,
    "point_name": "AHU-01/SupplyAirTemp",
    "object_type": "analogInput",
    "object_instance": 1,
    "old_value": 22.5,
    "new_value": 23.1,
    "units": "degreesCelsius"
  }
}
```

### device_status_changed

```json
{
  "id": "evt-002",
  "event_type": "device_status_changed",
  "timestamp": "2026-03-09T14:31:00+00:00",
  "payload": {
    "device_id": 2001,
    "device_name": "FCU-01",
    "old_status": "online",
    "new_status": "offline"
  }
}
```

### alarm_raised

```json
{
  "id": "evt-003",
  "event_type": "alarm_raised",
  "timestamp": "2026-03-09T14:32:00+00:00",
  "payload": {
    "alarm_id": "alm-abc123",
    "device_id": 1001,
    "point_name": "AHU-01/SupplyAirTemp",
    "severity": "high",
    "message": "Supply air temperature exceeded 35\u00b0C"
  }
}
```

### alarm_cleared

```json
{
  "id": "evt-004",
  "event_type": "alarm_cleared",
  "timestamp": "2026-03-09T14:45:00+00:00",
  "payload": {
    "alarm_id": "alm-abc123",
    "device_id": 1001,
    "point_name": "AHU-01/SupplyAirTemp",
    "severity": "high",
    "message": "Supply air temperature returned to normal"
  }
}
```

### scenario_started

```json
{
  "id": "evt-005",
  "event_type": "scenario_started",
  "timestamp": "2026-03-09T15:00:00+00:00",
  "payload": {
    "scenario_id": "hvac_day_night",
    "scenario_name": "HVAC Day/Night Cycle",
    "params": {}
  }
}
```

### scenario_stopped

```json
{
  "id": "evt-006",
  "event_type": "scenario_stopped",
  "timestamp": "2026-03-09T15:30:00+00:00",
  "payload": {
    "scenario_id": "hvac_day_night",
    "scenario_name": "HVAC Day/Night Cycle",
    "reason": "user_stopped"
  }
}
```

### telemetry_snapshot

```json
{
  "id": "evt-007",
  "event_type": "telemetry_snapshot",
  "timestamp": "2026-03-09T15:00:00+00:00",
  "payload": {
    "device_id": 1001,
    "device_name": "AHU-01",
    "points": {
      "SupplyAirTemp": 23.1,
      "ReturnAirTemp": 24.0,
      "FanSpeed": 75,
      "CoolingValve": 60.0,
      "FanStatus": true
    }
  }
}
```

## Signature Verification

Every webhook request includes an `X-BACnetLab-Signature` header containing an HMAC-SHA256 signature of the raw request body. Verify this signature to ensure the request is authentic and hasn't been tampered with.

The signature format is `sha256=<hex_digest>`, where the digest is computed over the raw JSON body using your endpoint's `secret` as the HMAC key.

### Python example

```python
import hashlib
import hmac

def verify_signature(body: bytes, secret: str, signature_header: str) -> bool:
    """Verify the X-BACnetLab-Signature header."""
    expected = hmac.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    received = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, received)

# Usage in a Flask/FastAPI handler:
# body = await request.body()
# signature = request.headers["X-BACnetLab-Signature"]
# if not verify_signature(body, WEBHOOK_SECRET, signature):
#     return Response(status_code=401)
```

> Use `hmac.compare_digest()` instead of `==` to prevent timing attacks.

## Failure Handling

- **Timeout**: Deliveries time out after **10 seconds**. If your endpoint doesn't respond within this window, the delivery is marked as failed.
- **Success**: Any HTTP `2xx` response is considered successful.
- **Failure counting**: Each failed delivery increments the endpoint's `failure_count`. You can monitor this via `GET /api/endpoints`.
- **Retries**: Failed deliveries are not automatically retried. Use the test endpoint (`POST /api/endpoints/{id}/test`) to verify connectivity after fixing issues.
