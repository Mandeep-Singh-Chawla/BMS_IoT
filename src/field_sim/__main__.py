"""Demo: python -m field_sim 30   (MQTT required; --bacnet needs BAC0)"""

from __future__ import annotations

import argparse
import json
import time

from field_sim.plant import EQUIPMENT_ID, OAT_POINT, SENSOR_ID
from field_sim.stack import start_field_sim


def main() -> None:
    parser = argparse.ArgumentParser(
        description="OAT → AHU cooling simulator with MQTT (optional BACnet/IP)"
    )
    parser.add_argument("oat", nargs="?", type=float, default=30.0, help="Outdoor temp °C")
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    parser.add_argument(
        "--bacnet",
        action="store_true",
        help="Expose plant points as BACnet/IP devices (requires BAC0)",
    )
    parser.add_argument("--bacnet-ip", default="127.0.0.1")
    parser.add_argument("--bacnet-port-start", type=int, default=47820)
    args = parser.parse_args()

    sim = start_field_sim(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        bacnet=args.bacnet,
        bacnet_ip=args.bacnet_ip,
        bacnet_port_start=args.bacnet_port_start,
    )
    try:
        sim.plant.write(SENSOR_ID, OAT_POINT, args.oat)
        print(json.dumps({"oat": args.oat, "ahu": sim.plant.snapshot(EQUIPMENT_ID)}, indent=2))
        print(f"MQTT gateway on {args.mqtt_host}:{args.mqtt_port}.")
        if sim.bacnet is not None:
            for spec in sim.bacnet.specs:
                print(
                    f"BACnet {spec.name} id={spec.device_id} "
                    f"{sim.bacnet.address(spec.device_id)}"
                )
        print("Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        sim.stop()


if __name__ == "__main__":
    main()
