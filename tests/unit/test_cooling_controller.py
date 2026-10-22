from bacnet_lab.application.cooling_controller import (
    OUTDOOR_TEMP_THRESHOLD_C,
    cooling_should_run,
)


def test_cooling_runs_when_outdoor_temp_exceeds_28():
    assert cooling_should_run(30.0) is True
    assert cooling_should_run(28.1) is True


def test_cooling_off_at_or_below_28():
    assert cooling_should_run(28.0) is False
    assert cooling_should_run(20.0) is False
    assert cooling_should_run(OUTDOOR_TEMP_THRESHOLD_C) is False
