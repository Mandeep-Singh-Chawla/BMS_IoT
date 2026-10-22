# Architecture

BACnet Lab follows a **hexagonal architecture** (ports & adapters) organized as a modular monolith. This design cleanly separates business logic from infrastructure, making the codebase testable and extensible.

## Project Structure

```
src/bacnet_lab/
├── domain/                 # Core business logic (no external dependencies)
│   ├── models/             # Device, Point, Endpoint, Event, Scenario
│   ├── events.py           # Domain events (PointValueChanged, AlarmRaised, ...)
│   ├── enums.py            # PointType, DeviceStatus, EventType, AlarmSeverity
│   └── value_objects.py    # PointValue, DeviceAddress
│
├── ports/                  # Abstract interfaces (dependency inversion)
│   ├── device_network.py   # BACnet device lifecycle & read/write
│   ├── event_publisher.py  # Pub/sub event interface
│   ├── event_delivery.py   # Webhook delivery contract
│   ├── repositories.py     # Data persistence abstractions
│   └── scenario_runner.py  # Scenario execution interface
│
├── application/            # Use cases (orchestration layer)
│   ├── device_service.py   # Initialize devices, read/write points
│   ├── scenario_service.py # Start/stop scenarios
│   ├── endpoint_service.py # Webhook endpoint CRUD
│   ├── event_service.py    # Event delivery coordination
│   └── telemetry_service.py # Periodic telemetry snapshots
│
├── adapters/               # Infrastructure implementations
│   ├── bacnet/             # BAC0 engine, device factory, object builder
│   ├── http/               # FastAPI app, routers, auth, schemas
│   ├── web/                # Jinja2 templates, HTMX dashboard
│   ├── persistence/        # SQLite repositories, migrations
│   ├── webhook/            # HMAC-signed HTTP delivery
│   ├── event_bus/          # In-process pub/sub
│   └── scenarios/          # Scenario implementations & registry
│
├── infrastructure/         # Cross-cutting concerns
│   ├── config.py           # Settings loader (YAML + env vars)
│   └── logging.py          # Logging setup
│
├── bootstrap.py            # Dependency injection container
└── __main__.py             # Application entry point
```

## Layers

### Domain

The core of the application. Contains models, events, enums, and value objects with zero external dependencies. This layer defines _what_ the application does without knowing _how_.

Key models:
- **Device** — a BACnet device with an ID, name, status, and a list of points
- **Point** — a BACnet object (analog input, binary output, etc.) with a present value
- **Endpoint** — a webhook endpoint with URL, secret, event type filters
- **Event** — a domain event with type, timestamp, and payload

### Ports

Abstract interfaces (Python ABCs) that define contracts between the domain and the outside world. Adapters implement these ports.

| Port | Responsibility |
|------|----------------|
| `DeviceNetworkPort` | Create/destroy BACnet devices, read/write point values |
| `EventPublisherPort` | Publish and subscribe to domain events |
| `EventDeliveryPort` | Deliver events to external systems (webhooks) |
| `RepositoryPort` (x4) | Persist devices, endpoints, events, alarms |
| `ScenarioRunnerPort` | Start/stop simulation scenarios |

### Application Services

Orchestrate domain objects and ports to implement use cases. No business logic here — just coordination.

### Adapters

Concrete implementations of ports. Each adapter can be swapped independently:

| Adapter | Implements | Technology |
|---------|-----------|------------|
| `BAC0Engine` | `DeviceNetworkPort` | BAC0 / BACpypes3 |
| `InProcessEventPublisher` | `EventPublisherPort` | In-memory pub/sub |
| `WebhookDeliveryAdapter` | `EventDeliveryPort` | httpx HTTP client |
| `SqliteXyzRepository` | Repository ports | aiosqlite |
| `ScenarioRegistry` | `ScenarioRunnerPort` | asyncio tasks |

## Key Design Decisions

### Async from the ground up

BAC0 24.x (based on BACpypes3) is fully async. The entire application uses `async/await` — from the FastAPI handlers to the BACnet engine to the SQLite repositories. No `run_in_executor` calls needed.

### One BAC0 instance per device

Each simulated device runs its own BAC0 instance on a dedicated UDP port (starting at 47808). This mirrors how real BACnet devices work and allows independent lifecycle management.

### Event bus for decoupling

All state changes (point writes, alarm conditions, device status changes) emit domain events through an in-process event bus. Handlers for persistence, webhooks, and telemetry subscribe independently. An exception in one handler doesn't affect others.

### YAML-based device definitions

Devices are defined in YAML files under `config/devices/`. This makes it easy to add, remove, or modify devices without changing code. The `DeviceFactory` loads these files at startup.

### Server-rendered UI

The web dashboard uses Jinja2 templates with HTMX for dynamic updates — no JavaScript build step, no npm, no webpack. Pico CSS provides minimal styling. This keeps the frontend simple and self-contained.

## Data Flow

### Point Write

```
HTTP PUT /api/devices/1001/points
  → DeviceService.write_point_by_name()
    → BAC0Engine.write_point_value()  (updates BACnet object)
    → EventPublisher.publish(PointValueChanged)
      → EventService: saves to event log
      → WebhookDelivery: sends to registered endpoints
      → TelemetryService: updates snapshot
```

### Scenario Execution

```
POST /api/scenarios/hvac_day_cycle/start
  → ScenarioService.start_scenario()
    → ScenarioRegistry.start()  (spawns asyncio task)
      → HvacDayCycleScenario.run()  (loop while is_running)
        → Computes time-based values (outdoor temp, valve positions, ...)
        → Calls DeviceService.write_point_by_name() for each update
        → Events generated automatically through the event bus
```

## Testing Strategy

The hexagonal architecture makes testing straightforward:

- **Unit tests** use domain objects directly — no adapters needed
- **Integration tests** swap `BAC0Engine` for a `FakeNetwork` mock and test through the HTTP API
- No BACnet network or BAC0 dependency required for the test suite
