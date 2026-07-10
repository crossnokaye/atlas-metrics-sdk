from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from atlas.models import (
    AggregateBy,
    CompressorMetric,
    CondenserMetric,
    Condition,
    Connection,
    ControlPoint,
    DeviceAssociations,
    DeviceKind,
    DeviceMetric,
    EvaporatorMetric,
    HistoricalHourlyRate,
    HistoricalHourlyRates,
    HistoricalReadingQuery,
    HistoricalSettingQuery,
    HistoricalSettingQuerySource,
    HourlyRate,
    Metric,
    MetricType,
    Output,
    Setting,
    SettingResultSequenceValueItem,
    VesselMetric,
    construct_from_metric_name,
    is_valid_metric,
)


@pytest.mark.parametrize(
    ("device_kind", "metric_name", "expected"),
    [
        pytest.param(
            DeviceKind.compressor,
            CompressorMetric.suction_pressure.value,
            MetricType.control_point,
            id="compressor_suction_pressure",
        ),
        pytest.param(
            DeviceKind.compressor,
            CompressorMetric.discharge_pressure.value,
            MetricType.control_point,
            id="compressor_discharge_pressure",
        ),
        pytest.param(
            DeviceKind.condenser,
            CondenserMetric.discharge_pressure.value,
            MetricType.control_point,
            id="condenser_discharge_pressure",
        ),
        pytest.param(
            DeviceKind.evaporator,
            EvaporatorMetric.supply_temperature.value,
            MetricType.control_point,
            id="evaporator_supply_temperature",
        ),
        pytest.param(
            DeviceKind.vessel,
            VesselMetric.pressure.value,
            MetricType.control_point,
            id="vessel_pressure",
        ),
        pytest.param(
            DeviceKind.compressor,
            "NotARealMetric",
            None,
            id="unknown_metric",
        ),
    ],
)
def test_construct_from_metric_name_with_name_returns_type(
    device_kind: DeviceKind,
    metric_name: str,
    expected: MetricType | None,
) -> None:
    result = construct_from_metric_name(metric_name, device_kind)

    assert result == expected


def test_construct_from_metric_name_with_unmapped_kind_raises_key_error() -> None:
    with pytest.raises(KeyError):
        construct_from_metric_name("DischargePressure", DeviceKind.energy_meter)


def test_control_point_with_payload_parses_id_and_unit() -> None:
    control_point = ControlPoint.model_validate(
        {
            "control_point_id": "cp-1",
            "alias": "SuctionPressure",
            "bias": "direct",
            "type": "analog",
            "unit": "psi",
        },
    )

    assert control_point.id == "cp-1"
    assert control_point.unit == "psi"


def test_device_associations_with_default_upstream_isolates_lists() -> None:
    associations_a = DeviceAssociations()
    associations_b = DeviceAssociations()

    associations_a.upstream.append(Connection(device_id="device-1", kind="upstream"))

    assert associations_b.upstream == []
    assert associations_a.downstream == []


def test_device_metric_with_alias_regex_and_type_succeeds() -> None:
    metric = DeviceMetric.model_validate(
        {
            "device_kind": DeviceKind.compressor,
            "alias_regex": ".*Current.*",
            "metric_type": MetricType.control_point,
        },
    )

    assert metric.alias_regex == ".*Current.*"
    assert metric.metric_type == MetricType.control_point


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"device_kind": DeviceKind.compressor, "alias_regex": ".*Current.*"},
            id="missing_metric_type",
        ),
        pytest.param(
            {"device_kind": DeviceKind.compressor, "name": "", "alias_regex": ".*Current.*"},
            id="empty_name",
        ),
    ],
)
def test_device_metric_with_alias_regex_without_type_raises_validation_error(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="metric_type must be provided when using alias_regex"):
        DeviceMetric.model_validate(payload)


def test_device_metric_with_explicit_type_uses_override() -> None:
    metric = DeviceMetric.model_validate(
        {
            "device_kind": DeviceKind.compressor,
            "name": CompressorMetric.suction_pressure.value,
            "metric_type": MetricType.metric,
        },
    )

    assert metric.metric_type == MetricType.metric


@pytest.mark.parametrize(
    ("device_kind", "metric_name"),
    [
        pytest.param(DeviceKind.compressor, CompressorMetric.suction_pressure.value, id="compressor"),
        pytest.param(DeviceKind.condenser, CondenserMetric.discharge_pressure.value, id="condenser"),
        pytest.param(DeviceKind.evaporator, EvaporatorMetric.supply_temperature.value, id="evaporator"),
        pytest.param(DeviceKind.vessel, VesselMetric.pressure.value, id="vessel"),
    ],
)
def test_device_metric_with_known_name_sets_metric_type(device_kind: DeviceKind, metric_name: str) -> None:
    metric = DeviceMetric.model_validate({"device_kind": device_kind, "name": metric_name})

    assert metric.metric_type == MetricType.control_point


def test_device_metric_with_unmapped_kind_raises_key_error() -> None:
    with pytest.raises(KeyError):
        DeviceMetric.model_validate(
            {
                "device_kind": DeviceKind.energy_meter,
                "name": CompressorMetric.suction_pressure.value,
            },
        )


def test_device_metric_with_unknown_name_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        DeviceMetric.model_validate({"device_kind": DeviceKind.compressor, "name": "UnknownMetric"})


def test_historical_hourly_rate_start_datetime_returns_utc() -> None:
    timestamp = 1_704_067_200
    historical_rate = HistoricalHourlyRate(start=timestamp, rate=0.12)

    assert historical_rate.start_datetime == datetime.fromtimestamp(timestamp, tz=UTC)


def test_historical_hourly_rate_to_hourly_rate_returns_rate() -> None:
    timestamp = 1_704_067_200
    historical_rate = HistoricalHourlyRate(start=timestamp, rate=0.12)

    hourly_rate = historical_rate.to_hourly_rate()

    assert hourly_rate == HourlyRate(start=historical_rate.start_datetime, rate=0.12)


@pytest.mark.parametrize(
    ("field_name", "timestamp", "rate"),
    [
        pytest.param("usage_rate", 1_704_067_200, 0.12, id="usage_rate"),
        pytest.param("maximum_demand_charge", 1_704_070_800, 5.0, id="maximum_demand_charge"),
        pytest.param("time_of_use_demand_charge", 1_704_074_400, 3.0, id="time_of_use_demand_charge"),
        pytest.param("day_ahead_market_rate", 1_704_078_000, 1.0, id="day_ahead_market_rate"),
        pytest.param("real_time_market_rate", 1_704_081_600, 2.0, id="real_time_market_rate"),
    ],
)
def test_historical_hourly_rates_to_hourly_rates_converts_each_field(
    field_name: str,
    timestamp: int,
    rate: float,
) -> None:
    historical_rate = HistoricalHourlyRate(start=timestamp, rate=rate)
    historical_rates = HistoricalHourlyRates(**{field_name: [historical_rate]})

    hourly_rates = historical_rates.to_hourly_rates()
    converted = getattr(hourly_rates, field_name)

    assert len(converted) == 1
    assert converted[0].rate == rate
    assert converted[0].start == datetime.fromtimestamp(timestamp, tz=UTC)


def test_historical_reading_query_with_default_aggregate_by_isolates_lists() -> None:
    query_a = HistoricalReadingQuery(source_id="metric-a", aggregate_by=[AggregateBy.avg])
    query_b = HistoricalReadingQuery(source_id="metric-b")

    query_a.aggregate_by.append(AggregateBy.max)

    assert query_b.aggregate_by == []


@pytest.mark.parametrize(
    "source_id",
    [
        pytest.param("", id="empty_string"),
        pytest.param("   ", id="whitespace_only"),
    ],
)
def test_historical_reading_query_with_invalid_source_id_raises_validation_error(source_id: str) -> None:
    with pytest.raises(ValidationError, match="source_id must be a non-empty string"):
        HistoricalReadingQuery(source_id=source_id)


@pytest.mark.parametrize(
    "source_id",
    [
        pytest.param("metric-123", id="nonempty"),
        pytest.param("  metric-123  ", id="surrounding_whitespace"),
    ],
)
def test_historical_reading_query_with_valid_source_id_succeeds(source_id: str) -> None:
    query = HistoricalReadingQuery(source_id=source_id)

    assert query.source_id == source_id


def test_historical_reading_query_without_aggregate_by_defaults_empty() -> None:
    query = HistoricalReadingQuery(source_id="metric-123")

    assert query.aggregate_by == []


def test_historical_setting_query_with_default_aggregate_by_isolates_lists() -> None:
    source = HistoricalSettingQuerySource(setting_id="setting-1")
    query_a = HistoricalSettingQuery(source=source, aggregate_by=[AggregateBy.avg])
    query_b = HistoricalSettingQuery(source=source)

    query_a.aggregate_by.append(AggregateBy.max)

    assert query_b.aggregate_by == []


def test_historical_setting_query_without_aggregate_by_defaults_empty() -> None:
    source = HistoricalSettingQuerySource(setting_id="setting-1")
    query = HistoricalSettingQuery(source=source)

    assert query.aggregate_by == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("device_id", "", id="device_id_empty"),
        pytest.param("device_id", "   ", id="device_id_whitespace"),
        pytest.param("setting_alias", "", id="setting_alias_empty"),
        pytest.param("setting_id", "", id="setting_id_empty"),
        pytest.param("setting_id", "   ", id="setting_id_whitespace"),
    ],
)
def test_historical_setting_query_source_with_empty_field_raises_validation_error(
    field: str,
    value: str,
) -> None:
    with pytest.raises(ValidationError, match="must be a non-empty string"):
        HistoricalSettingQuerySource(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("device_id", None, id="device_id_none"),
        pytest.param("device_id", "device-1", id="device_id_nonempty"),
        pytest.param("setting_alias", None, id="setting_alias_none"),
        pytest.param("setting_alias", "max-capacity", id="setting_alias_nonempty"),
        pytest.param("setting_id", None, id="setting_id_none"),
        pytest.param("setting_id", "setting-1", id="setting_id_nonempty"),
    ],
)
def test_historical_setting_query_source_with_valid_field_succeeds(
    field: str,
    value: str | None,
) -> None:
    source = HistoricalSettingQuerySource(**{field: value})

    assert getattr(source, field) == value


@pytest.mark.parametrize(
    ("name", "device_kind", "alias_regex", "expected"),
    [
        pytest.param(
            CompressorMetric.suction_pressure.value,
            DeviceKind.compressor,
            "",
            True,
            id="known_name",
        ),
        pytest.param("UnknownMetric", DeviceKind.compressor, "", False, id="unknown_name"),
        pytest.param(
            CompressorMetric.suction_pressure.value,
            DeviceKind.condenser,
            "",
            False,
            id="wrong_device_kind",
        ),
        pytest.param("", DeviceKind.compressor, ".*Current.*", True, id="alias_regex_only"),
        pytest.param("", DeviceKind.compressor, "", False, id="no_name_or_alias"),
    ],
)
def test_is_valid_metric_with_metric_returns_validity(
    name: str,
    device_kind: DeviceKind,
    alias_regex: str,
    expected: bool,
) -> None:
    metric = DeviceMetric(
        device_kind=device_kind,
        name=name,
        alias_regex=alias_regex,
        metric_type=MetricType.control_point,
    )

    assert is_valid_metric(metric) is expected


def test_is_valid_metric_with_unmapped_kind_raises_key_error() -> None:
    metric = DeviceMetric(
        device_kind=DeviceKind.energy_meter,
        name=CompressorMetric.suction_pressure.value,
        metric_type=MetricType.control_point,
    )

    with pytest.raises(KeyError):
        is_valid_metric(metric)


@pytest.mark.parametrize(
    ("model_cls", "payload", "expected_metric_type"),
    [
        pytest.param(
            ControlPoint,
            {
                "control_point_id": "id-1",
                "alias": "alias-1",
                "bias": "bias",
                "type": "type",
            },
            MetricType.control_point,
            id="control_point",
        ),
        pytest.param(
            Metric,
            {
                "metric_id": "id-1",
                "alias": "alias-1",
                "kind": "kind",
            },
            MetricType.metric,
            id="metric",
        ),
        pytest.param(
            Output,
            {
                "output_id": "id-1",
                "alias": "alias-1",
                "kind": "kind",
            },
            MetricType.output,
            id="output",
        ),
        pytest.param(
            Condition,
            {
                "condition_id": "id-1",
                "alias": "alias-1",
            },
            MetricType.condition,
            id="condition",
        ),
        pytest.param(
            Setting,
            {
                "setting_id": "setting-1",
                "name": "MaxCapacity",
                "kind": "number",
                "unit": "kW",
            },
            MetricType.setting,
            id="setting",
        ),
    ],
)
def test_metric_type_property_with_instance_returns_type(
    model_cls: type[ControlPoint] | type[Metric] | type[Output] | type[Condition] | type[Setting],
    payload: dict[str, Any],
    expected_metric_type: MetricType,
) -> None:
    instance = model_cls.model_validate(payload)

    assert instance.metric_type == expected_metric_type


def test_setting_alias_property_returns_name() -> None:
    setting = Setting.model_validate(
        {
            "setting_id": "setting-1",
            "name": "MaxCapacity",
            "kind": "number",
            "unit": "kW",
        },
    )

    assert setting.alias == "MaxCapacity"


def test_setting_result_sequence_value_item_with_camel_case_parses_stage_values() -> None:
    item = SettingResultSequenceValueItem.model_validate(
        {
            "name": "stage-1",
            "stageValues": [1, 2, 3],
        },
    )

    assert item.name == "stage-1"
    assert item.stage_values == [1, 2, 3]
