from bacnet_lab.adapters.mqtt.gateway import (
    command_topic,
    point_name_to_slug,
    telemetry_topic,
    write_status_topic,
)


def test_topic_helpers():
    assert point_name_to_slug("OAT-01/OutdoorTemp") == "OAT-01.OutdoorTemp"
    assert telemetry_topic("bacnet", 5001, "OAT-01/OutdoorTemp") == (
        "bacnet/5001/telemetry/OAT-01.OutdoorTemp"
    )
    assert command_topic("bacnet", 5001) == "bacnet/5001/command"
    assert command_topic("bacnet", "+") == "bacnet/+/command"
    assert write_status_topic("bacnet", 5001, "OAT-01/OutdoorTemp") == (
        "bacnet/5001/write_status/OAT-01.OutdoorTemp"
    )
