from __future__ import annotations

from bacnet_lab.domain.enums import PointType
from bacnet_lab.domain.models.device import Point


def build_local_object(point: Point):
    """Create a BAC0 ObjectFactory for a point using the BAC0 factory API.

    Must be called within a running asyncio event loop (bacpypes3 requirement).
    Returns an ObjectFactory instance that can be added to a BAC0 application.
    """
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
        "name": point.object_name,
        "instance": point.object_instance,
        "description": point.description or "",
    }

    match point.object_type:
        case PointType.ANALOG_INPUT:
            return analog_input(
                **common,
                presentValue=float(point.present_value) if not isinstance(point.present_value, bool) else 0.0,
                properties={"units": point.units or "noUnits"},
            )
        case PointType.ANALOG_OUTPUT:
            return analog_output(
                **common,
                presentValue=float(point.present_value) if not isinstance(point.present_value, bool) else 0.0,
                properties={"units": point.units or "noUnits"},
            )
        case PointType.ANALOG_VALUE:
            return analog_value(
                **common,
                presentValue=float(point.present_value) if not isinstance(point.present_value, bool) else 0.0,
                properties={"units": point.units or "noUnits"},
                is_commandable=True,
            )
        case PointType.BINARY_INPUT:
            return binary_input(
                **common,
                presentValue="active" if point.present_value else "inactive",
            )
        case PointType.BINARY_OUTPUT:
            return binary_output(
                **common,
                presentValue="active" if point.present_value else "inactive",
            )
        case PointType.BINARY_VALUE:
            return binary_value(
                **common,
                presentValue="active" if point.present_value else "inactive",
                is_commandable=True,
            )
        case PointType.MULTI_STATE_INPUT:
            return multistate_input(
                **common,
                presentValue=int(point.present_value) if not isinstance(point.present_value, bool) else 1,
            )
        case PointType.MULTI_STATE_OUTPUT:
            return multistate_output(
                **common,
                presentValue=int(point.present_value) if not isinstance(point.present_value, bool) else 1,
            )
        case PointType.MULTI_STATE_VALUE:
            return multistate_value(
                **common,
                presentValue=int(point.present_value) if not isinstance(point.present_value, bool) else 1,
                is_commandable=True,
            )
        case _:
            raise ValueError(f"Unsupported point type: {point.object_type}")
