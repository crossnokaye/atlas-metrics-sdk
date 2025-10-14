import os
import sys
import argparse
from datetime import datetime, timezone

import orjson
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from atlas import CompressorMetric, DeviceKind, DeviceMetric, Filter, MetricsReader, MetricType

"""
This example retrieves the suction pressure and motor current for all
compressors in the given facilities a specified time period, averaging
using the specified interval and prints the values.
"""

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

parser = argparse.ArgumentParser(description="Read compressor metrics from ATLAS")
parser.add_argument("facilities", nargs="+", help="Facility short names to query")
parser.add_argument("--json", action="store_true", help="Print the output in JSON format")
parser.add_argument("--debug", action="store_true", help="Enable debug logging")
parser.add_argument("--flatten", action="store_true", help="Print the output in flattened format")
parser.add_argument(
    "--start",
    type=str,
    help="Start time (ISO 8601, accepts 'Z', or 'YYYY-MM-DD HH:MM:SS'). UTC assumed if no TZ.",
)
parser.add_argument(
    "--end",
    type=str,
    help="End time (ISO 8601, accepts 'Z', or 'YYYY-MM-DD HH:MM:SS'). UTC assumed if no TZ.",
)
parser.add_argument("--interval", type=int, default=60, help="Aggregation interval in seconds")

args = parser.parse_args()

json_output = args.json
debug = args.debug
flatten = args.flatten
interval = args.interval
facilities = args.facilities
start_time = parse_dt(args.start) if args.start else None
end_time = parse_dt(args.end) if args.end else None

device_kind = DeviceKind.compressor
metric_name = CompressorMetric.suction_pressure

compressor_suction_pressure = DeviceMetric(device_kind=device_kind, name=metric_name)
motor_current = DeviceMetric(device_kind=device_kind, metric_type=MetricType.control_point, alias_regex=".*Current.*")
filter = Filter(facilities=facilities, metrics=[compressor_suction_pressure, motor_current])
values = MetricsReader(debug=debug).read(
    filter,
    flatten=flatten,
    start=start_time,
    end=end_time,
    interval=interval,
)

if json_output:
    print(orjson.dumps(values, default=lambda x: x.model_dump() if isinstance(x, BaseModel) else x).decode("utf-8"))
    sys.exit(0)

if flatten:
    # Handle flattened format
    for item in values:
        print(f"{item.facility.capitalize()} - {item.device_name} - {item.metric.name}")
        print(f"  {item.timestamp}: {item.value}")
else:
    # Handle nested format
    for facility, metrics_values in values.items():
        print(facility.capitalize())
        for metric_values in metrics_values:
            if len(metric_values.values) == 0:
                continue
            print(f"{metric_values.device_name} {metric_values.metric.name}")
            for value in metric_values.values:
                print(f"  {value.timestamp}: {value.value}")
