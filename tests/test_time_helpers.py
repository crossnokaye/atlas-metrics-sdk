from atlas.time_helpers import parse_dt


def test_parse_dt_none_returns_none() -> None:
    assert parse_dt(None) is None
