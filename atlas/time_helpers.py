from datetime import datetime, timezone

def parse_dt(value: str | None) -> datetime | None:
    """Parse a datetime string into a timezone-aware UTC datetime.

    Accepts ISO-8601 (including "Z") or "YYYY-MM-DD HH:MM:SS". If no timezone
    is provided, UTC is assumed.
    """
    if value is None:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        dt = datetime.strptime(v, "%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt