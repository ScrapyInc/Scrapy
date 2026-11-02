from datetime import UTC, datetime

import pytest

from ingestor.runs.schedule import ScheduleError, run_scheduled, schedule_decision


@pytest.mark.parametrize(
    "stamp",
    [
        "2026-01-14T23:00:00",
        "2026-07-14T22:00:00",
        "2026-03-25T23:00:00",
        "2026-03-26T23:00:00",
        "2026-10-23T22:00:00",
        "2026-10-24T22:00:00",
    ],
)
def test_one_am_israel_gate_tracks_both_dst_offsets_and_transitions(stamp):
    result = schedule_decision(datetime.fromisoformat(stamp).replace(tzinfo=UTC))
    assert result.permitted and result.reason == "READY" and result.delay_seconds == 0


@pytest.mark.parametrize(
    "stamp,permitted,reason",
    [
        ("2026-01-14T22:00:00", False, "BEFORE_WINDOW"),
        ("2026-07-15T04:00:00", True, "DELAYED"),
        ("2026-01-15T05:00:00", True, "DELAYED"),
    ],
)
def test_early_starts_skip_and_late_starts_allow_catch_up(stamp, permitted, reason):
    result = schedule_decision(datetime.fromisoformat(stamp).replace(tzinfo=UTC))
    assert result.permitted == permitted and result.reason == reason


def test_startup_delay_is_reported_after_one_am():
    result = schedule_decision(datetime(2026, 7, 14, 22, 7, 12, tzinfo=UTC))
    assert result.permitted and result.reason == "DELAYED" and result.delay_seconds == 432


def test_local_date_is_used_across_utc_midnight_and_naive_time_is_rejected():
    assert str(schedule_decision(datetime(2026, 7, 14, 23, tzinfo=UTC)).local_date) == "2026-07-15"
    with pytest.raises(ScheduleError, match="INVALID_SCHEDULE_TIME"):
        schedule_decision(datetime(2026, 7, 15, 6))


@pytest.mark.parametrize("hour,expected", [(21, 0)])
def test_outside_window_never_opens_connections(hour, expected):
    from ingestor.config import load_settings
    from ingestor.logging import create_logger

    def forbidden(*args):
        pytest.fail("outside-window invocation reached database/source")

    assert (
        run_scheduled(
            settings=load_settings({}),
            execution_id="12345:1",
            connection_factory=forbidden,
            provider_factory=forbidden,
            logger=create_logger(),
            now=datetime(2026, 7, 14, hour, tzinfo=UTC),
        )
        == expected
    )


def test_invalid_identity_and_precancelled_job_do_not_claim_or_echo_input(capsys):
    from threading import Event

    from ingestor.config import load_settings
    from ingestor.logging import create_logger

    def forbidden(*args):
        pytest.fail("preflight reached database/source")

    kwargs = dict(
        settings=load_settings({}),
        connection_factory=forbidden,
        provider_factory=forbidden,
        logger=create_logger(),
    )
    assert run_scheduled(execution_id="synthetic-secret", **kwargs) == 2
    cancelled = Event()
    cancelled.set()
    assert run_scheduled(execution_id="12345:1", cancelled=cancelled, **kwargs) == 130
    assert "synthetic-secret" not in capsys.readouterr().err
