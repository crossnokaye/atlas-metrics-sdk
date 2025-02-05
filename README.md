# ATLAS Metrics SDK

## Overview

The ATLAS Metrics SDK is a Python library that provides a simple interface for
retrieving metrics from the (ATLAS platform)[https://crossnokaye.com].  The
library provides both high-level and low-level APIs, allowing users to choose
the appropriate level of abstraction based on their needs. The high-level API
simplifies usage, while the low-level API offers more flexibility and control.

## Requirements

- Python 3.11 or higher

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
    alias_regexp=".*_motorCurrent"
)
```

### Example Usage

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

## High-Level API: RatesReader

The `RatesReader` class provides a simplified interface for retrieving hourly energy rates.
The class provides a single method `read` that accepts a filter as argument together with
start and end dates.

A filter can specify multiple facilities for which to retrieve rates, if not specified
`read` returns rates for all facilities the user has access to.

### Example Usage

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

### Example Usage

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

# Get point IDs for device aliases
point_aliases = ["alias1", "alias2"]
point_ids = client.get_point_ids(org_id, agent_id, point_aliases)
print(point_ids)

# Get historical values
start_time = datetime(2023, 5, 1, 0, 0, 0)
end_time = datetime(2023, 5, 1, 23, 59, 59)
interval = 60  # 1 minute interval
historical_values = client.get_historical_values(org_id, agent_id, list(point_ids.values()), start=start_time, end=end_time, interval=interval)
print(historical_values)

# Get hourly energy rates
rates = client.get_hourly_rates(org_id, agent_id)
print(rates)
```

## Contributing

Contributions are welcome! Please submit a pull request or open an issue to discuss changes.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
