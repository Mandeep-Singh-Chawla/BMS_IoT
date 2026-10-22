# Configuration

BACnet Lab is configured through YAML files, environment variables, or both. Environment variables take precedence over YAML settings.

## Configuration Sources

Settings are loaded in this order (later sources override earlier ones):

1. **Hardcoded defaults** in the application code
2. **YAML file** at `config/settings.yaml`
3. **Environment variables** prefixed with `BACNET_LAB_`

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACNET_LAB_HTTP_HOST` | `0.0.0.0` | HTTP server bind address |
| `BACNET_LAB_HTTP_PORT` | `8080` | HTTP server port |
| `BACNET_LAB_BACNET_IP` | `0.0.0.0` | BACnet bind IP address |
| `BACNET_LAB_BACNET_PORT_START` | `47808` | First UDP port for BACnet devices |
| `BACNET_LAB_DB_PATH` | `bacnet_lab.db` | SQLite database file path |
| `BACNET_LAB_LOG_LEVEL` | `INFO` | Log level (DEBUG, INFO, WARNING, ERROR) |
| `BACNET_LAB_AUTH_USERNAME` | *(empty)* | HTTP Basic Auth username |
| `BACNET_LAB_AUTH_PASSWORD` | *(empty)* | HTTP Basic Auth password |

## YAML Configuration

The default configuration file is `config/settings.yaml`:

```yaml
http:
  host: "0.0.0.0"
  port: 8080

bacnet:
  ip: "0.0.0.0"
  port_start: 47808

db_path: "bacnet_lab.db"
log_level: "INFO"
devices_dir: "config/devices"
```

## Authentication

BACnet Lab supports optional HTTP Basic Auth. When enabled, the browser shows a native login dialog (same UX as Apache htaccess).

### Enabling Authentication

Set both environment variables:

```bash
export BACNET_LAB_AUTH_USERNAME=admin
export BACNET_LAB_AUTH_PASSWORD=your-secure-password
```

Or in your `.env` file:

```
BACNET_LAB_AUTH_USERNAME=admin
BACNET_LAB_AUTH_PASSWORD=your-secure-password
```

### Disabling Authentication

Leave both variables empty (or unset). Auth is disabled when either username or password is empty.

### API Requests with Auth

```bash
curl -u admin:your-secure-password http://localhost:8080/api/devices
```

## BACnet Network Settings

### IP Address

`BACNET_LAB_BACNET_IP` controls which network interface BACnet devices bind to:

- `0.0.0.0` (default) — bind to all interfaces
- A specific IP (e.g., `192.168.1.100`) — bind to one interface, useful when the machine has multiple network interfaces

### UDP Ports

Each simulated device gets its own UDP port, assigned sequentially starting from `BACNET_LAB_BACNET_PORT_START` (default: 47808). With 7 devices, ports 47808–47814 are used.

Make sure these ports are available and not blocked by a firewall.

## Docker Configuration

### .env File

For Docker deployments, copy the example environment file and customize it:

```bash
cp .env.example .env
```

The `.env` file is automatically loaded by Docker Compose.

### Linux (Production)

The default `docker-compose.yml` uses `network_mode: host`, which shares the host's network stack with the container. This is required for BACnet UDP broadcast to work across the network.

### macOS/Windows (Development)

Use the development override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

This switches to bridge networking with port mapping. BACnet devices won't be discoverable from the host network, but the API and web dashboard work normally.

## Database

BACnet Lab uses SQLite with zero configuration. The database file is created automatically at the path specified by `BACNET_LAB_DB_PATH`.

The database stores:
- Device and point metadata
- Webhook endpoints
- Event log
- Alarm history

Database migrations run automatically at startup.
