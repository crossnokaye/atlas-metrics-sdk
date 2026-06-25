# ATLAS Metrics SDK

## Overview

The ATLAS Metrics SDK is a Python library that provides a simple interface for
retrieving metrics from the [ATLAS platform](https://crossnokaye.com).  The
library provides both high-level and low-level APIs, allowing users to choose
the appropriate level of abstraction based on their needs. The high-level API
simplifies usage, while the low-level API offers more flexibility and control.

## Requirements

- Python 3.11 or later

## Installation

1. Clone the repository:

    ```bash
    git clone https://github.com/crossnokaye/atlas-metrics-sdk.git
    cd atlas-metrics-sdk
    ```

2. Create a virtual environment and install the dependencies:

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```

## Configuration

Create a configuration file at `~/.config/atlas/config.toml` with the following
content:

```toml
[production]
refresh_token = "your_refresh_token_here"
```

## Get Started

The `examples` directory contains sample code that demonstrates how to use the
library. To run the examples, execute the following command:

```bash
python examples/list_facilities.py
python examples/read_metrics.py <facility short name>
```

The examples are:

- `read_metrics.py`: Demonstrates how to retrieve metric values using the high-level API.
- `read_rates.py`: Demonstrates how to retrieve hourly energy rates using the high-level API.
- `list_facilities.py`: Demonstrates how to list facilities using the low-level API.
- `list_devices.py`: Demonstrates how to list devices for a facility using the low-level API.

Each example can print the output in plain text or JSON format. To print the output in JSON format, add the `--json` flag:

```bash
python examples/list_facilities.py --json
```

## High-Level API: MetricsReader

The `MetricsReader` class provides a simplified interface for retrieving metric point values.
The class provides a single method `read` that accepts a filter as argument together with
start and end dates and a sample interval.

A filter can specify multiple facilities for which to retrieve metrics, if not specified
`read` returns metrics for all facilities the user has access to. A filter also specifies
which device metrics to retrieve. A device metric consists of a device kind and a device
kind specific metric name.

For example the following filter retrieves the suction pressure for all compressors across
all facilities:

```python
Filter(metrics=[DeviceMetric(
    device_kind=DeviceKind.compressor,
    name=CompressorMetric.suction_pressure,
)
```

While the following filter retrieves both the discharge pressure of condensers and
compressors at the "oxnard" and "riverside" facilities:

```python
Filter(
    facilities=["oxnard", "riverside"],
    metrics=[
    DeviceMetric(
        device_kind=DeviceKind.condenser,
        name=CondenserMetric.discharge_pressure),
    DeviceMetric(
        device_kind=DeviceKind.compressor,
        name=CompressorMetric.discharge_pressure)
])

```

The list of available device kinds and metric names are listed in the `atlas` package
[models.py](atlas/models.py) file.

The list of availble facilities and their short names can be retrieved using the
`list_facilities.py` example.

Additionally a `DeviceMetric` can be configured with a regular expression to
match property aliases. For example the following filter retrieves the motor
current for all compressors:

```python
Filter(metrics=[DeviceMetric(
    device_kind=DeviceKind.compressor,
    alias_regexp=".*_motorCurrent",
    metric_type=MetricType.control_point
)
```

### Example Usage 1

```python
from datetime import datetime
from atlas import MetricsReader, Filter, DeviceMetric, CompressorMetric, DeviceKind

# Define a filter
filter = Filter(
    facilities=["facility"],
    metrics=[DeviceMetric(
        device_kind=DeviceKind.compressor,
        name=CompressorMetric.suction_pressure,
    )]
)

# Retrieve metric values
start_time = datetime(2023, 5, 1, 0, 0, 0)
end_time = datetime(2023, 5, 1, 23, 59, 59)
interval = 60  # 1 minute interval

data = MetricsReader().read(filter, start=start_time, end=end_time, interval=interval)
```

### Metrics Query Limits

Metrics queries are subject to limits to help ensure reliable access to metrics data.
Applications which require spans of data which exceed limits can break their query
down into multiple queries, each with a shorter time span.

The supported sampling `interval` is limited by three factors:

- the query time range (`end` - `start`)
- the number of requested sources (not the number of aggregations applied to each source)
- the retention for the requested interval

The following table details supported combinations of time range, number of
sources, and retention. Retention defines the maximum age of the data that can
be queried — the query's `start` may not come before the retention period.

| Interval | Max Time Range (<= 10 sources) | Max Time Range (> 10 sources) | Retention |
| --- | --- | --- | --- |
| 1s | 1h | 5m | 31d |
| 5s | 6h | 30m | 31d |
| 10s | 12h | 1h | 31d |
| 15s | 12h | 2h | 31d |
| 1m | 1d | 6h | 365d |
| 5m | 7d | 1d | 365d |
| 15m | 32d | 4d | 731d |
| 30m | 92d | 7d | 731d |
| 1h | 183d | 14d | 731d |
| 12h | 731d | 192d | 731d |
| 1d | 731d | 366d | 731d |

For example, if an application requires 1m resolution data for 50 sources at a
time, the query's maximum time range is 7d and the `start` of the query cannot be
more than 365 days ago. If an application requires only 24h resolution for a
single data source, the query's time range can be up to 365 days, and may start
as far back as 730 days ago.

Raw data from more than 31 days ago is not supported (time range limits also
apply to queries for raw data).

## High-Level API: RatesReader

The `RatesReader` class provides a simplified interface for retrieving hourly energy rates.
The class provides a single method `read` that accepts a filter as argument together with
start and end dates.

A filter can specify multiple facilities for which to retrieve rates, if not specified
`read` returns rates for all facilities the user has access to.

### Example Usage 2

```python
from datetime import datetime
from atlas import RatesReader

# Define a filter
filter = RateFilter(facilities=["facility"])

# Retrieve hourly energy rates
start_time = datetime(2023, 5, 1, 0, 0, 0)
end_time = datetime(2023, 5, 1, 23, 59, 59)

rates = RatesReader().read(filter, start=start_time, end=end_time)
```

## Low-Level API: AtlasClient

The `AtlasClient` class provides a more flexible and lower-level interface for
interacting with the ATLAS platform. This class allows for more complex
operations and greater control over the API interactions. The class also
provides access to hourly energy rates.

### Example Usage 3

```Python
from atlas import AtlasClient

# Initialize AtlasClient
client = AtlasClient()

# List facilities
facilities = client.list_facilities()
print(facilities)

# List devices for a facility
org_id = "organization_id"
agent_id = "agent_id"
devices = client.list_devices(org_id, agent_id)
print(devices)

# Find point ids on devices
device = devices[0]
# control points:
print(device.control_points)
# metrics
print(device.metrics)
# outputs
print(device.outputs)
# conditions
print(device.conditions)
# settings
print(device.settings)

point_ids = ["73e697c8-6eae-44e1-a512-6c8083ea7904", "068fb8bb-4680-4cf1-ba29-57e71a80eb5a"]
print(point_ids)

# Get historical values
start_time = datetime(2023, 5, 1, 0, 0, 0)
end_time = datetime(2023, 5, 1, 23, 59, 59)
interval = 60  # 1 minute interval
historical_values = client.get_historical_reading_values(org_id, agent_id, list(point_ids.values()), start=start_time, end=end_time, interval=interval)
print(historical_values)

# Get hourly energy rates
rates = client.get_hourly_rates(org_id, agent_id)
print(rates)
```

## Contributing

Contributions are welcome! Please submit a pull request or open an issue to discuss changes.

### Environment Setup

Follow setup in [Installation](#installation), but when creating a virtual environment, install the dev dependencies:

 ```bash
 python3 -m venv .venv
 source .venv/bin/activate
 pip install -r requirements-dev.txt
 ```

### Linting

Ruff check is used to lint the source code. Ruff check is required to pass for the rules specified in [pyproject.toml](pyproject.toml) before merging a pull request. Ruff check can run for the entire source, or an additional parameter can scope it to a file, directory, or glob.

```bash
ruff check
```

The --fix argument can be used to automatically fix some linting errors. Beware that this modifies files in-place.

```bash
ruff check --fix
```

### Formatting

Ruff format is used to format the source code. Ruff format check is required to pass for a consistent source shape. Ruff format can run for the entire source, or an additional parameter can scope it to a file, directory, or glob.

```bash
ruff format
```

### Type Checking

Mypy is used to perform static type checking on the source code. The Mypy check is required to pass. Mypy can run as configured in pyproject.toml, or an additional parameter can scope it to a file, directory, or glob.

```bash
mypy
```

### API Changes Detection

[Griffe](https://github.com/mkdocstrings/griffe) checks the public API surface for breaking changes against a baseline branch. This is used to monitor SemVer compliance on release and identify potentially breaking changes before they are merged.

The pull request CI pipeline runs Griffe and publishes a detailed summary. This check is intentionally non-blocking: it reports API changes but never prevents a merge, leaving final design and compatibility decisions to the developer and reviewers.

Griffe can be run to check the atlas package against a branch or git ref.

```bash
griffe check atlas --search . --against origin/main
```

## License

This project is licensed under the MIT License. See the LICENSE file for details.
