from datetime import UTC, datetime

import pytest

from atlas.time_helpers import parse_dt


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        # ISO-8601 with Z
        ("2026-07-10T19:07:00Z", datetime(2026, 7, 10, 19, 7, 0, tzinfo=UTC)),
        # ISO-8601 with explicit UTC offset
        ("2026-07-10T19:07:00+00:00", datetime(2026, 7, 10, 19, 7, 0, tzinfo=UTC)),
        ("2026-07-10T19:07:00-00:00", datetime(2026, 7, 10, 19, 7, 0, tzinfo=UTC)),
        # ISO-8601 without timezone (UTC assumed)
        ("2026-07-10T19:07:00", datetime(2026, 7, 10, 19, 7, 0, tzinfo=UTC)),
        ("2026-01-01T00:00:00", datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)),
        ("2026-12-31T23:59:59", datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)),
        # "YYYY-MM-DD HH:MM:SS" without timezone (UTC assumed)
        ("2026-07-10 19:07:00", datetime(2026, 7, 10, 19, 7, 0, tzinfo=UTC)),
        ("2026-01-01 00:00:00", datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)),
        # Fractional seconds
        ("2026-07-10T19:07:00.123Z", datetime(2026, 7, 10, 19, 7, 0, 123_000, tzinfo=UTC)),
        ("2026-07-10T19:07:00.123456Z", datetime(2026, 7, 10, 19, 7, 0, 123_456, tzinfo=UTC)),
        ("2026-07-10T19:07:00.5", datetime(2026, 7, 10, 19, 7, 0, 500_000, tzinfo=UTC)),
        ("2026-07-10 19:07:00.25", datetime(2026, 7, 10, 19, 7, 0, 250_000, tzinfo=UTC)),
        # Non-UTC offsets normalized to UTC
        ("2026-07-10T19:07:00+05:00", datetime(2026, 7, 10, 14, 7, 0, tzinfo=UTC)),
        ("2026-07-10T19:07:00-04:00", datetime(2026, 7, 10, 23, 7, 0, tzinfo=UTC)),
        ("2026-07-10T19:07:00+05:30", datetime(2026, 7, 10, 13, 37, 0, tzinfo=UTC)),
        ("2026-07-10 19:07:00+05:00", datetime(2026, 7, 10, 14, 7, 0, tzinfo=UTC)),
    ],
    ids=lambda p: str(p),
)
def test_parse_dt(value: str | None, expected: datetime | None) -> None:
    result = parse_dt(value)
    assert result == expected
    if result is not None:
        assert result.tzinfo is UTC


@pytest.mark.parametrize("value", ["not-a-datetime", "2026-13-45T99:99:99", "2026/07/10 19:07:00"])
def test_parse_dt_raises(value: str) -> None:
    with pytest.raises(ValueError):
        parse_dt(value)
