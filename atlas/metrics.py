import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional, Union

from pydantic import BaseModel

from atlas.atlas_client import AtlasClient
from atlas.models import (
    AggregateBy,
    ControlledDeviceConstruct,
    Device,
    DeviceMetric,
    Facility,
    ReadingQuery,
    ReadingSourceResult,
    MetricType,
    is_valid_metric,
)


class Filter(BaseModel):
    facilities: list[str]
    metrics: list[DeviceMetric]


class MetricValue(BaseModel):
    timestamp: datetime
    value: float


class DetailedMetricValue(BaseModel):
    facility: str
    metric: DeviceMetric
    device_name: str
    device_alias: str
    device_kind: str
    device_id: str
    aggregation: str
    timestamp: datetime
    value: float


class MetricValues(BaseModel):
    metric: DeviceMetric
    device_name: str
    device_alias: str
    device_id: str
    aggregation: str
    values: list[MetricValue]


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
        self,
        filter: Filter,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        interval: int = 60,
        aggregate_by: list[str] = ["avg"],
        flatten: bool = False,
    ) -> Union[dict[str, list[MetricValues]], list[DetailedMetricValue]]:
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
        aggregate_by: List of strings, optional.
            Aggregation function to use over the interval, defaults to "avg".
            Available agg functions are listed in the /models.AggregateBy class
        flatten : bool, optional
            If True, returns a flattened list of DetailedMetricValue objects.
            If False, returns the nested structure dict[str, list[MetricValues]].

        Returns
        -------
        Union[Dict[str, List[MetricsValues]], List[DetailedMetricValue]]
            If flatten=False: Dictionary of metrics values time series indexed by facility short name.
            If flatten=True: List of DetailedMetricValue objects with all metric details.

        Raises
        ------
        Exception
            Raised if an error occurs.
        """
        if not filter.metrics:
            raise Exception("No metrics provided")

        metrics_by_device_kind = defaultdict(list)
        for metric in filter.metrics:
            if not is_valid_metric(metric):
                raise Exception(f"Invalid metrics type {metric}")
            metrics_by_device_kind[metric.device_kind].append(metric)

        facilities = self.client.filter_facilities(filter.facilities)

        result = defaultdict(list)
        for facility in facilities:
            agent_id = facility.agents[0].agent_id
            devices = self._get_devices(facility, agent_id)
            devices_dict = {}

            # find relevant constructs (sources)
            filtered_constructs_by_id = {}
            # query all devices at once
            queries: list[ReadingQuery] = []
            # map constructs (sources) back to devices
            construct_to_device_id = {}
            
            for device in devices:
                devices_dict[device.id] = device
                metrics_filter = metrics_by_device_kind[device.kind]
                if not metrics_filter:
                    continue

                new_filtered_constructs_by_id = self._get_filtered_constructs_by_id(device, metrics_filter)
                if not new_filtered_constructs_by_id:
                    continue
                filtered_constructs_by_id.update(new_filtered_constructs_by_id)

                construct_ids = list(filtered_constructs_by_id.keys())
                agg_enums = [AggregateBy(a) for a in aggregate_by]
                for source_id in construct_ids:
                    construct_to_device_id[source_id] = device.id
                    queries.append(ReadingQuery(source_id=source_id, aggregate_by=agg_enums))

            hvalues = self._get_historical_values(
                facility, agent_id, start, end, interval, queries
            )
            self._process_historical_values(result, facility, devices_dict, construct_to_device_id, filtered_constructs_by_id, hvalues)

        if flatten:
            return self._flatten_result(result)

        return result

    def _flatten_result(self, result: dict[str, list[MetricValues]]) -> list[DetailedMetricValue]:
        """
        Flatten the nested result structure into a list of DetailedMetricValue objects.

        Parameters
        ----------
        result : dict[str, list[MetricValues]]
            The nested result from the read method

        Returns
        -------
        list[DetailedMetricValue]
            List of DetailedMetricValue objects with all metric details
        """
        flattened = []
        for facility_name, metric_values_list in result.items():
            for metric_values in metric_values_list:
                for value in metric_values.values:
                    flattened.append(
                        DetailedMetricValue(
                            facility=facility_name,
                            metric=metric_values.metric,
                            device_name=metric_values.device_name,
                            device_alias=metric_values.device_alias,
                            device_kind=metric_values.metric.device_kind,
                            device_id=metric_values.device_id,
                            aggregation=metric_values.aggregation,
                            timestamp=value.timestamp,
                            value=value.value,
                        )
                    )
        flattened.sort(key=lambda x: (x.device_id, x.timestamp))
        return flattened

    def _get_devices(self, facility: Facility, agent_id: str) -> list[Device]:
        try:
            return self.client.list_devices(facility.organization_id, agent_id)
        except Exception as e:
            raise Exception(f"Error listing devices for facility {facility.display_name}: {e}")

    def _get_filtered_constructs_by_id(
        self, device: Device, metrics: list[DeviceMetric]
    ) -> dict[str, ControlledDeviceConstruct]:
        result: dict[str, ControlledDeviceConstruct] = {}

        for metric_type in MetricType:
            # Extract metric names and regex patterns
            metric_names = {metric.name for metric in metrics if metric.metric_type == metric_type}
            metric_regexps = [
                re.compile(metric.alias_regex)
                for metric in metrics
                if metric.metric_type == metric_type and metric.alias_regex
            ]
            if not metric_names and not metric_regexps:
                continue

            contructs: list[ControlledDeviceConstruct] = getattr(device, f"{metric_type.value}s")

            for construct in contructs:
                if construct.alias in metric_names:
                    result[construct.id] = construct
                elif any(pattern.match(construct.alias) for pattern in metric_regexps):
                    result[construct.id] = construct

        return result

    def _get_historical_values(
        self,
        facility: Facility,
        agent_id: str,
        start: Optional[datetime],
        end: Optional[datetime],
        interval: int,
        queries: list[ReadingQuery],
    ) -> list[ReadingSourceResult]:
        try:
            return self.client.get_historical_values(
                facility.organization_id, agent_id, start, end, queries, interval
            )
        except Exception as e:
            raise Exception(f"Error retrieving historical values for facility {facility.display_name}: {e}")

    def _process_historical_values(
        self,
        result: defaultdict[str, list[MetricValues]],
        facility: Facility,
        device_dict: defaultdict[str, Device],
        construct_to_device_id: dict[str, str],
        filtered_constructs_by_id: list[dict[str, ControlledDeviceConstruct]],
        source_results: list[ReadingSourceResult],
    ) -> None:
        # Results are ordered by timestamp, but are not grouped by source
        # Group readings by (device_id, source_alias, metric_type, aggregation)
        # only using avg for now, but be flexible
        grouped: dict[tuple[str, str, str, str], dict] = {}

        for source_result in source_results:
            source_id = source_result.source_id
            source = filtered_constructs_by_id[source_id]
            device = device_dict[construct_to_device_id[source_id]]

            reading_timestamp = datetime.fromisoformat(source_result.time.replace('Z', '+00:00'))

            for res in source_result.results:
                aggregation_key = str(res.aggregation) if res.aggregation else "avg"
                group_key = (device.id, source.alias, source.metric_type, aggregation_key)

                if group_key not in grouped:
                    grouped[group_key] = {
                        "metric": DeviceMetric(name=source.alias, device_kind=device.kind, metric_type=source.metric_type),
                        "device_name": device.name,
                        "device_alias": device.alias,
                        "device_id": device.id,
                        "aggregation": aggregation_key,
                        "values": [],
                    }

                grouped[group_key]["values"].append(
                    MetricValue(
                        timestamp=reading_timestamp,
                        value=res.numberValue.scaled if res.numberValue else None,
                    )
                )

        for _, mv in grouped.items():
            result[facility.short_name].append(MetricValues(**mv))
