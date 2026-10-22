# Simulation Scenarios

BACnet Lab includes 4 built-in scenarios that simulate realistic HVAC behavior. Scenarios run as async background tasks and can be started/stopped via the REST API or web dashboard.

## Starting a Scenario

**Via API:**

```bash
curl -X POST http://localhost:8080/api/scenarios/hvac_day_cycle/start \
  -H "Content-Type: application/json" \
  -d '{"params": {"cycle_seconds": 60, "interval": 2}}'
```

**Via Dashboard:** Navigate to the Scenarios tab and click Start.

## Stopping a Scenario

```bash
curl -X POST http://localhost:8080/api/scenarios/hvac_day_cycle/stop
```

## HVAC Day/Night Cycle

**ID:** `hvac_day_cycle`

Simulates a compressed 24-hour HVAC operation cycle. All 7 devices are updated in sync to create a realistic building automation scenario.

### Behavior

The scenario compresses a full day into `cycle_seconds` (default: 120s). At each `interval` tick:

- **Outdoor temperature** varies sinusoidally: minimum ~8°C at 5:00, maximum ~32°C at 15:00
- **Occupied hours** are 7:00–19:00
- During occupied hours: supply air setpoint = 22°C, fan speed = 75%
- During unoccupied hours: setpoint drops to 18°C, fan speed = 30%
- **Cooling valve** opens proportionally when outdoor temp exceeds 22°C
- **Heating valve** opens when outdoor temp drops below 18°C (unoccupied mode)
- **Room temperatures** drift slightly based on outdoor conditions
- **FCU occupancy sensors** toggle with occupied/unoccupied periods
- **CO2 levels** rise during occupied hours (400–700 ppm) and drop to baseline (~400 ppm) at night
- **Zone controller dampers** open during occupied hours (65%) and close at night (20%)

### Affected Devices

All 7 devices: AHU-01, FCU-01, FCU-02, TSTAT-01, ZC-01, OAT-01, CO2-01

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `cycle_seconds` | 120 | Duration of a full 24h cycle in seconds |
| `interval` | 3 | Update interval in seconds |

### Example

Run a fast 60-second cycle with updates every 2 seconds:

```bash
curl -X POST http://localhost:8080/api/scenarios/hvac_day_cycle/start \
  -H "Content-Type: application/json" \
  -d '{"params": {"cycle_seconds": 60, "interval": 2}}'
```

## Cyclic High Temperature Alarm

**ID:** `alarm_cycle`

Periodically raises and clears a high supply air temperature alarm on AHU-01. Useful for testing alarm handling, webhook event delivery, and monitoring system responses.

### Behavior

1. Sets AHU-01/SupplyAirTemp to `high_temp` (default: 35°C)
2. Publishes an `alarm_raised` event with severity HIGH
3. Waits `alarm_duration` seconds
4. Sets AHU-01/SupplyAirTemp back to `normal_temp` (default: 22.5°C)
5. Publishes an `alarm_cleared` event
6. Waits `clear_duration` seconds
7. Repeats until stopped

### Affected Devices

AHU-01 only

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `alarm_duration` | 15 | How long the alarm stays active (seconds) |
| `clear_duration` | 20 | How long until the next alarm cycle (seconds) |
| `high_temp` | 35.0 | Temperature value that triggers the alarm |
| `normal_temp` | 22.5 | Normal temperature value after alarm clears |

## Temporary Device Offline

**ID:** `device_offline`

Simulates a device going offline and recovering. Useful for testing failover logic, monitoring alerts, and device status handling.

### Behavior

1. Sets the target device status to `offline`
2. Publishes a `device_status_changed` event
3. Waits `offline_duration` seconds
4. Sets the device status back to `online`
5. Publishes another `device_status_changed` event
6. Waits `online_duration` seconds
7. Repeats until stopped

### Affected Devices

Configurable (default: FCU-01)

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `device_id` | 2001 | Target device ID |
| `offline_duration` | 15 | How long the device stays offline (seconds) |
| `online_duration` | 30 | How long the device stays online before next outage (seconds) |

## Manual Override

**ID:** `manual_override`

Overrides a specific point to a fixed value, then restores the original value after a duration. Runs once (not cyclic).

### Behavior

1. Sets the target point to `override_value`
2. Waits `hold_duration` seconds
3. Restores the point to `original_value`
4. Scenario ends

### Affected Devices

Configurable (default: AHU-01 cooling valve)

### Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `device_id` | 1001 | Target device ID |
| `point_name` | AHU-01/CoolingValve | Point to override |
| `override_value` | 100.0 | Value to force |
| `original_value` | 45.0 | Value to restore after hold |
| `hold_duration` | 30 | How long to hold the override (seconds) |

### Example

Override a different point:

```bash
curl -X POST http://localhost:8080/api/scenarios/manual_override/start \
  -H "Content-Type: application/json" \
  -d '{
    "params": {
      "device_id": 2001,
      "point_name": "FCU-01/FanSpeed",
      "override_value": 100.0,
      "original_value": 50.0,
      "hold_duration": 60
    }
  }'
```

## Running Multiple Scenarios

Multiple scenarios can run simultaneously. For example, you can run the HVAC day/night cycle alongside the alarm cycle to test how your system handles both dynamic point changes and alarm events at the same time.

Each running scenario generates events through the event bus, which are persisted and delivered to webhook endpoints.
