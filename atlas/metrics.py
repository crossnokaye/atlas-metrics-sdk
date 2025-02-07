import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from dateutil import tz
from pydantic import BaseModel

from .atlas_client import AtlasClient
from .models import DeviceMetric, is_valid_metric


class Filter(BaseModel):
    facilities: List[str]
    metrics: List[DeviceMetric]


class MetricValue(BaseModel):
    timestamp: datetime
    value: float


class MetricValues(BaseModel):
    metric: DeviceMetric
    device_name: str
    device_alias: str
    values: List[MetricValue]


class MetricsReader:
    """
    High level API Client for retrieving metrics point values from the ATLAS platform.
    """

    def __init__(self, refresh_token: Optional[str] = None, debug: Optional[bool] = False):
        """
        Parameters
        ----------
        refresh_token : Optional[str], optional
            Refresh token can be provided directly, by default None.
            If not provided, the refresh token will be read from the
            environment variable ATLAS_REFRESH_TOKEN or from the
            config file ~/.config/atlas/config.toml.
        debug : Optional[bool], optional
            Enable debug logging, by default False.
        """
        self.client = AtlasClient(refresh_token=refresh_token, debug=debug)

    def read(
        self, filter: Filter, start: Optional[datetime] = None, end: Optional[datetime] = None, interval: int = 60
    ) -> Dict[str, List[MetricValues]]:
        """
        Retrieve metric values for a given filter and time range.
        Values are averaged over the sampling interval.

        Parameters
        ----------
        filter : Filter
            Filter for metrics values, defines the list of facilities and metrics to retrieve.
        start : Optional[datetime], optional
            Start time of the historical values, by default 10 minutes ago.
        end : Optional[datetime], optional
            End time of the historical values, by default now.
        interval : int, optional
            Sampling interval in seconds, by default 60.

        Returns
        -------
        Dict[str, List[MetricsValues]]
            Dictionary of metrics values time series indexed by facility short name.

        Raises
        ------
        Exception
            Raised if an error occurs.
        """
        if not filter.metrics:
            raise Exception("No metrics provided")

        for metric in filter.metrics:
            if not is_valid_metric(metric):
                raise Exception(f"Invalid metrics type {metric}")

        facilities = self.client.filter_facilities(filter.facilities)

        result = defaultdict(list)
        for facility in facilities:
            agent_id = facility.agents[0].agent_id
            devices = self._get_devices(facility, agent_id)

            for device in devices:
                metrics_filter = [metric for metric in filter.metrics if metric.device_kind == device.kind]
                if not metrics_filter:
                    continue

                alias_filters = self._get_alias_filters(device, metrics_filter)
                if not alias_filters:
                    continue

                aliases = [af["alias"] for af in alias_filters]

                point_map = self._get_point_ids(facility, agent_id, aliases)
                hvalues = self._get_historical_values(facility, agent_id, point_map, start, end, interval)

                self._process_historical_values(result, facility, device, alias_filters, point_map, hvalues)

        return result

    def _get_devices(self, facility, agent_id: str) -> List:
        try:
            return self.client.list_devices(facility.organization_id, agent_id)
        except Exception as e:
            raise Exception(f"Error listing devices for facility {facility.display_name}: {e}")

    def _get_alias_filters(self, device, metrics: List[DeviceMetric]) -> List[Dict[str, str]]:
        properties = device.properties

        # Extract metric names and regex patterns
        metric_names = {metric.name for metric in metrics}
        metric_regexps = [re.compile(metric.alias_regex) for metric in metrics if metric.alias_regex]

        # Create initial filters based on metric names
        filters = [{"alias": prop.value.alias, "filter": prop.key} for prop in properties if prop.key in metric_names]

        # Add filters based on non-empty regex patterns
        regex_filters = [
            {"alias": prop.value.alias, "filter": prop.key}
            for prop in properties
            if any(pattern.match(prop.value.alias) for pattern in metric_regexps)
        ]

        # Append regex-based filters to the main filters list
        filters.extend(regex_filters)
        return filters

    def _get_point_ids(self, facility, agent_id: str, aliases: List[str]) -> Dict[str, str]:
        if not aliases:
            raise Exception(f"No aliases found for facility {facility.short_name}")
        try:
            point_map = self.client.get_point_ids(facility.organization_id, agent_id, aliases)
        except Exception as e:
            raise Exception(f"Error listing points for facility {facility.display_name}: {e}")

        if len(point_map) != len(aliases):
            not_found = set(aliases) - set(point_map.keys())
            raise Exception(f"Points {not_found} not found for facility {facility.short_name}")

        return point_map

    def _get_historical_values(
        self,
        facility,
        agent_id: str,
        point_map: Dict[str, str],
        start: Optional[datetime],
        end: Optional[datetime],
        interval: int,
    ):
        try:
            return self.client.get_historical_values(
                facility.organization_id, agent_id, list(point_map.values()), start, end, interval
            )
        except Exception as e:
            raise Exception(f"Error retrieving historical values for facility {facility.display_name}: {e}")

    def _process_historical_values(
        self,
        result: defaultdict,
        facility,
        device,
        alias_filters: List[Dict[str, str]],
        point_map: Dict[str, str],
        hvalues: List,
    ):
        for agvalues in hvalues:
            point_id = agvalues.point_id
            point_alias = next((alias for alias, pid in point_map.items() if pid == point_id), None)
            point_filter = next((af["filter"] for af in alias_filters if af["alias"] == point_alias), None)
            point_values = agvalues.values["avg"]

            if point_values.analog:
                vals, timestamps = point_values.analog.values, point_values.analog.timestamps
            elif point_values.discrete:
                vals, timestamps = point_values.discrete.values, point_values.discrete.timestamps
            else:
                vals, timestamps = [], []

            metrics_values = MetricValues(
                metric=DeviceMetric(name=point_filter, device_kind=device.kind),
                device_name=device.name,
                device_alias=device.alias,
                values=[
                    MetricValue(timestamp=datetime.fromtimestamp(ts, tz=tz.UTC), value=val)
                    for ts, val in zip(timestamps, vals)
                ],
            )
            result[facility.short_name].append(metrics_values)
