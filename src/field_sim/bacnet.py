"""Optional BACnet/IP face for FieldPlant. No bacnet_lab imports.

Plant remains the source of truth:
  plant write  → local BAC0 presentValue (MQTT via MqttBridge)
  BACnet write → plant write → MQTT

Requires BAC0 (bacpypes3). MQTT is a separate adapter (mqtt_bridge.py).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

from field_sim.plant import FieldPlant, PointValue

logger = logging.getLogger(__name__)

DEFAULT_IP = "127.0.0.1"
DEFAULT_PORT_START = 47820
POLL_INTERVAL_S = 0.25

_BINARY_TYPES = frozenset({"binaryInput", "binaryOutput", "binaryValue"})
_ANALOG_TYPES = frozenset({"analogInput", "analogOutput", "analogValue"})


@dataclass(frozen=True)
class BacnetObjectSpec:
    point_name: str
    object_type: str
    instance: int
    units: str | None = None


@dataclass
class BacnetDeviceSpec:
    device_id: int
    name: str
    udp_port: int
    objects: list[BacnetObjectSpec] = field(default_factory=list)

    def object_for(self, point_name: str) -> BacnetObjectSpec:
        for spec in self.objects:
            if spec.point_name == point_name:
                return spec
        raise KeyError(f"No BACnet object for {self.device_id}/{point_name}")


def infer_object_type(section: str, value: PointValue) -> str:
    """Guess a BACnet object type when devices.yaml has no bacnet.objects."""
    if isinstance(value, bool):
        return "binaryInput" if section == "sensor" else "binaryOutput"
    if section == "sensor":
        return "analogInput"
    return "analogOutput"


def load_bacnet_specs(
    plant: FieldPlant,
    *,
    yaml_path: str | Path | None = None,
    port_start: int = DEFAULT_PORT_START,
) -> list[BacnetDeviceSpec]:
    """Build per-device BACnet maps from devices.yaml, else infer from plant."""
    path = Path(yaml_path) if yaml_path else Path(__file__).with_name("devices.yaml")
    yaml_by_id: dict[int, tuple[str, str, dict]] = {}
    if path.exists():
        try:
            import yaml as yaml_lib
        except ImportError:
            yaml_lib = None
        if yaml_lib is not None:
            data = yaml_lib.safe_load(path.read_text()) or {}
            for section in ("sensor", "equipment"):
                block = data.get(section)
                if not isinstance(block, dict) or "device_id" not in block:
                    continue
                device_id = int(block["device_id"])
                name = str(block.get("name") or f"device-{device_id}")
                yaml_by_id[device_id] = (section, name, dict(block.get("bacnet") or {}))

    specs: list[BacnetDeviceSpec] = []
    for index, (device_id, points) in enumerate(plant.as_dict().items()):
        section, name, bacnet_cfg = yaml_by_id.get(
            device_id,
            ("sensor" if index == 0 else "equipment", f"device-{device_id}", {}),
        )
        udp_port = int(bacnet_cfg.get("port") or (port_start + index))
        declared = bacnet_cfg.get("objects") or {}
        objects: list[BacnetObjectSpec] = []
        type_instances: dict[str, int] = {}
        for point_name, value in points.items():
            raw = declared.get(point_name) if isinstance(declared, dict) else None
            if isinstance(raw, dict) and raw.get("type"):
                object_type = str(raw["type"])
                instance = int(raw["instance"])
                units = raw.get("units")
            else:
                object_type = infer_object_type(section, value)
                type_instances[object_type] = type_instances.get(object_type, 0) + 1
                instance = type_instances[object_type]
                units = "degreesCelsius" if "Temp" in point_name else None
            objects.append(
                BacnetObjectSpec(
                    point_name=str(point_name),
                    object_type=object_type,
                    instance=instance,
                    units=str(units) if units else None,
                )
            )
        specs.append(
            BacnetDeviceSpec(
                device_id=device_id,
                name=name,
                udp_port=udp_port,
                objects=objects,
            )
        )
    return specs


def object_identifier(spec: BacnetObjectSpec) -> str:
    """BACnet ReadProperty object spec, e.g. ``analogInput 1``."""
    return f"{spec.object_type} {spec.instance}"


def _unwrap(raw: object) -> object:
    value = getattr(raw, "value", None)
    if value is not None and not isinstance(raw, (bool, int, float, str)):
        return value
    return raw


def to_bac0_present(spec: BacnetObjectSpec, value: PointValue) -> object:
    if spec.object_type in _BINARY_TYPES:
        return "active" if value else "inactive"
    if spec.object_type.startswith("multiState"):
        return int(value)  # type: ignore[arg-type]
    return float(value)  # type: ignore[arg-type]


def from_bac0_present(spec: BacnetObjectSpec, raw: object, plant_sample: PointValue) -> PointValue:
    raw = _unwrap(raw)
    if spec.object_type in _BINARY_TYPES:
        if isinstance(raw, str):
            return raw.lower() in ("active", "true", "1")
        return bool(raw)
    if isinstance(plant_sample, bool):
        return bool(raw)
    if isinstance(plant_sample, int) and not isinstance(plant_sample, bool):
        return int(float(raw))  # type: ignore[arg-type]
    return float(raw)  # type: ignore[arg-type]


def values_equal(spec: BacnetObjectSpec, plant_value: PointValue, bac0_raw: object) -> bool:
    converted = from_bac0_present(spec, bac0_raw, plant_value)
    if spec.object_type in _ANALOG_TYPES:
        try:
            return abs(float(converted) - float(plant_value)) < 0.001  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return converted == plant_value
    return converted == plant_value


def _remove_invalid_fd_bbmd_address(instance: object) -> None:
    """BAC0 workaround: drop malformed fdBBMDAddress outside foreign mode."""
    try:
        application = instance.this_application.app
        network_port = application.get_object_name("NetworkPort-1")
    except AttributeError:
        return
    if network_port is None:
        return
    fd_bbmd_address = getattr(network_port, "fdBBMDAddress", None)
    if fd_bbmd_address is None or getattr(fd_bbmd_address, "host", None) is not None:
        return
    del network_port.fdBBMDAddress


def _build_local_object(spec: BacnetObjectSpec, value: PointValue):
    from BAC0.core.devices.local.factory import (
        analog_input,
        analog_output,
        analog_value,
        binary_input,
        binary_output,
        binary_value,
        multistate_input,
        multistate_output,
        multistate_value,
    )

    common = {
        "name": spec.point_name,
        "instance": spec.instance,
        "description": spec.point_name,
    }
    present = to_bac0_present(spec, value)
    match spec.object_type:
        case "analogInput":
            return analog_input(
                **common,
                presentValue=float(present),  # type: ignore[arg-type]
                properties={"units": spec.units or "noUnits"},
            )
        case "analogOutput":
            return analog_output(
                **common,
                presentValue=float(present),  # type: ignore[arg-type]
                properties={"units": spec.units or "noUnits"},
            )
        case "analogValue":
            return analog_value(
                **common,
                presentValue=float(present),  # type: ignore[arg-type]
                properties={"units": spec.units or "noUnits"},
                is_commandable=True,
            )
        case "binaryInput":
            return binary_input(**common, presentValue=present)
        case "binaryOutput":
            return binary_output(**common, presentValue=present)
        case "binaryValue":
            return binary_value(**common, presentValue=present, is_commandable=True)
        case "multiStateInput":
            return multistate_input(**common, presentValue=int(present))  # type: ignore[arg-type]
        case "multiStateOutput":
            return multistate_output(**common, presentValue=int(present))  # type: ignore[arg-type]
        case "multiStateValue":
            return multistate_value(
                **common, presentValue=int(present), is_commandable=True  # type: ignore[arg-type]
            )
        case _:
            raise ValueError(f"Unsupported BACnet object type: {spec.object_type}")


class BacnetNetwork:
    """One BAC0.lite device per plant device. Does not import bacnet_lab."""

    def __init__(
        self,
        plant: FieldPlant,
        *,
        ip: str = DEFAULT_IP,
        port_start: int = DEFAULT_PORT_START,
        yaml_path: str | Path | None = None,
        poll_interval_s: float = POLL_INTERVAL_S,
    ) -> None:
        self._plant = plant
        self._ip = ip
        self._specs = load_bacnet_specs(
            plant, yaml_path=yaml_path, port_start=port_start
        )
        self._poll_interval_s = poll_interval_s
        self._instances: dict[int, object] = {}
        self._spec_by_id: dict[int, BacnetDeviceSpec] = {s.device_id: s for s in self._specs}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._started = False

    @property
    def specs(self) -> list[BacnetDeviceSpec]:
        return list(self._specs)

    def address(self, device_id: int) -> str:
        spec = self._spec_by_id[device_id]
        return f"{self._ip}:{spec.udp_port}"

    def object_identifier(self, device_id: int, point_name: str) -> str:
        return object_identifier(self._spec_by_id[device_id].object_for(point_name))

    def start(self) -> None:
        if self._started:
            return
        try:
            import BAC0  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "BACnet support needs BAC0. Install with: pip install BAC0"
            ) from e
        self._ready.clear()
        self._error = None
        self._thread = threading.Thread(
            target=self._thread_main, name="field-sim-bacnet", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=40):
            raise TimeoutError("BACnet devices did not start within 40s")
        if self._error is not None:
            raise RuntimeError("BACnet failed to start") from self._error
        self._started = True
        self._plant.on_write(self._on_plant_write)

    def stop(self) -> None:
        self._started = False
        loop = self._loop
        if loop is not None and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
            try:
                fut.result(timeout=15)
            except Exception as e:  # noqa: BLE001
                logger.warning("BACnet shutdown error: %s", e)
            loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=8)
        self._loop = None

    def present_value(self, device_id: int, point_name: str) -> PointValue:
        if self._loop is None:
            raise RuntimeError("BACnet network is not started")
        fut = asyncio.run_coroutine_threadsafe(
            self._read_local(device_id, point_name), self._loop
        )
        return fut.result(timeout=5)

    def simulate_client_write(
        self, device_id: int, point_name: str, value: PointValue
    ) -> None:
        """Set local presentValue as a BACnet client would. Poll copies it into the plant."""
        if self._loop is None:
            raise RuntimeError("BACnet network is not started")
        fut = asyncio.run_coroutine_threadsafe(
            self._write_local(device_id, point_name, value), self._loop
        )
        fut.result(timeout=5)

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._boot())
            self._poll_task = loop.create_task(self._poll_external_writes())
            self._ready.set()
            loop.run_forever()
        except Exception as e:  # noqa: BLE001
            self._error = e
            self._ready.set()
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                logger.debug("BACnet loop shutdown_asyncgens failed", exc_info=True)
            loop.close()

    async def _boot(self) -> None:
        from BAC0.core.devices.local.factory import ObjectFactory

        for spec in self._specs:
            await self._start_device(spec, ObjectFactory)

    async def _start_device(self, spec: BacnetDeviceSpec, object_factory) -> None:
        import BAC0

        instance = BAC0.lite(
            ip=f"{self._ip}/24:{spec.udp_port}",
            deviceId=spec.device_id,
            localObjName=spec.name,
        )
        for _ in range(50):
            if getattr(instance, "_initialized", False):
                break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError(f"BAC0 device {spec.device_id} did not initialize")

        _remove_invalid_fd_bbmd_address(instance)
        for obj in spec.objects:
            value = self._plant.read(spec.device_id, obj.point_name)
            factory = _build_local_object(obj, value)
            factory.add_objects_to_application(instance)
            object_factory.clear_objects()
        self._instances[spec.device_id] = instance
        logger.info(
            "field_sim BACnet device %s (ID=%d) on %s:%d",
            spec.name,
            spec.device_id,
            self._ip,
            spec.udp_port,
        )

    async def _read_local(self, device_id: int, point_name: str) -> PointValue:
        spec = self._spec_by_id[device_id].object_for(point_name)
        raw = self._instances[device_id][point_name].presentValue
        return from_bac0_present(spec, raw, self._plant.read(device_id, point_name))

    async def _write_local(self, device_id: int, point_name: str, value: PointValue) -> None:
        spec = self._spec_by_id[device_id].object_for(point_name)
        obj = self._instances[device_id][point_name]
        obj.presentValue = to_bac0_present(spec, value)

    def _on_plant_write(
        self,
        device_id: int,
        point_name: str,
        _old: PointValue,
        new: PointValue,
    ) -> None:
        if not self._started or self._loop is None:
            return
        try:
            self._spec_by_id[device_id].object_for(point_name)
        except KeyError:
            return
        asyncio.run_coroutine_threadsafe(
            self._write_local(device_id, point_name, new), self._loop
        )

    async def _poll_external_writes(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._poll_interval_s)
                await self._sync_bac0_into_plant()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.debug("BACnet poll: %s", e)

    async def _sync_bac0_into_plant(self) -> None:
        for spec in self._specs:
            instance = self._instances.get(spec.device_id)
            if instance is None:
                continue
            for obj in spec.objects:
                try:
                    raw = instance[obj.point_name].presentValue
                    plant_value = self._plant.read(spec.device_id, obj.point_name)
                    if values_equal(obj, plant_value, raw):
                        continue
                    new_value = from_bac0_present(obj, raw, plant_value)
                    self._plant.write(spec.device_id, obj.point_name, new_value)
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        "BACnet sync %s/%s: %s", spec.device_id, obj.point_name, e
                    )

    async def _shutdown(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                logger.debug("BACnet poll task cancelled")
            self._poll_task = None
        for device_id, instance in list(self._instances.items()):
            try:
                await instance._disconnect()
            except Exception as e:  # noqa: BLE001
                logger.warning("Error stopping BACnet device %d: %s", device_id, e)
            self._instances.pop(device_id, None)
