from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Union

from pydantic import BaseModel, Field, model_validator


class Agent(BaseModel):
    agent_id: str


class Facility(BaseModel):
    organization_id: str
    facility_id: str
    display_name: str
    short_name: str
    address: str
    timezone: str
    agents: List[Agent]


class Connection(BaseModel):
    device_id: str
    kind: str


class DeviceAssociations(BaseModel):
    upstream: List[Connection] = []
    downstream: List[Connection] = []


class MetricType(str, Enum):
    control_point = "control_point"
    metric = "metric"
    output = "output"
    condition = "condition"
    setting = "setting"


class ControlPoint(BaseModel):
    id: str = Field(alias="control_point_id")
    alias: str
    bias: str
    type: str
    unit: str | None = None

    @property
    def metric_type(self) -> MetricType:
        return MetricType.control_point


class Metric(BaseModel):
    id: str = Field(alias="metric_id")
    alias: str
    kind: str
    unit: str | None = None

    @property
    def metric_type(self) -> MetricType:
        return MetricType.metric


class Output(BaseModel):
    id: str = Field(alias="output_id")
    alias: str
    kind: str
    unit: str | None = None

    @property
    def metric_type(self) -> MetricType:
        return MetricType.output


class Condition(BaseModel):
    id: str = Field(alias="condition_id")
    alias: str

    @property
    def metric_type(self) -> MetricType:
        return MetricType.condition


class Setting(BaseModel):
    id: str = Field(alias="setting_id")
    name: str
    kind: str
    unit: str | None = None
    # value: float | bool | str | None = None
    # default_value: float | bool | str | None = None
    # desired_value: float | bool | str | None = None

    @property
    def alias(self) -> str:
        return self.name

    @property
    def metric_type(self) -> MetricType:
        return MetricType.setting


ControlledDeviceConstruct = Union[
    ControlPoint,
    Metric,
    Output,
    Condition,
    Setting,
]


class Device(BaseModel):
    id: str
    alias: str
    kind: str
    control_points: List[ControlPoint] = []
    metrics: List[Metric] = []
    outputs: List[Output] = []
    conditions: List[Condition] = []
    settings: List[Setting] = []
    upstream: List[Connection] = []
    downstream: List[Connection] = []

    @property
    def name(self) -> str:
        return self.alias


class AnalogValues(BaseModel):
    timestamps: List[int]
    values: List[float]


class DiscreteValues(BaseModel):
    timestamps: List[int]
    values: List[bool]


class PointValues(BaseModel):
    analog: AnalogValues = None
    discrete: DiscreteValues = None


class AggregateBy(str, Enum):
    avg = "avg"
    min = "min"
    max = "max"
    first = "first"
    last = "last"


class HistoricalValues(BaseModel):
    point_id: str
    values: Dict[AggregateBy, PointValues]


class HourlyRate(BaseModel):
    start: datetime
    rate: float


class HourlyRates(BaseModel):
    usage_rate: List[HourlyRate] = []
    maximum_demand_charge: List[HourlyRate] = []
    time_of_use_demand_charge: List[HourlyRate] = []
    day_ahead_market_rate: List[HourlyRate] = []
    real_time_market_rate: List[HourlyRate] = []


class HistoricalHourlyRate(BaseModel):
    start: int
    rate: float

    @property
    def start_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.start, tz=timezone.utc)

    def to_hourly_rate(self) -> HourlyRate:
        return HourlyRate(start=self.start_datetime, rate=self.rate)


class HistoricalHourlyRates(BaseModel):
    usage_rate: List[HistoricalHourlyRate] = []
    maximum_demand_charge: List[HistoricalHourlyRate] = []
    time_of_use_demand_charge: List[HistoricalHourlyRate] = []
    day_ahead_market_rate: List[HistoricalHourlyRate] = []
    real_time_market_rate: List[HistoricalHourlyRate] = []

    def to_hourly_rates(self) -> HourlyRates:
        return HourlyRates(
            usage_rate=[rate.to_hourly_rate() for rate in self.usage_rate],
            maximum_demand_charge=[rate.to_hourly_rate() for rate in self.maximum_demand_charge],
            time_of_use_demand_charge=[rate.to_hourly_rate() for rate in self.time_of_use_demand_charge],
            day_ahead_market_rate=[rate.to_hourly_rate() for rate in self.day_ahead_market_rate],
            real_time_market_rate=[rate.to_hourly_rate() for rate in self.real_time_market_rate],
        )


class DeviceKind(str, Enum):
    compressor = "compressor"
    evaporator = "evaporator"
    condenser = "condenser"
    vessel = "vessel"
    energy_meter = "energy meter"


class CompressorMetric(str, Enum):
    discharge_pressure = "DischargePressure"
    discharge_temperature = "DischargeTemperature"
    suction_pressure = "SuctionPressure"
    suction_temperature = "SuctionTemperature"


class CondenserMetric(str, Enum):
    discharge_pressure = "DischargePressure"
    discharge_temperature = "DischargeTemperature"


class EvaporatorMetric(str, Enum):
    supply_temperature = "SupplyTemperature"
    return_temperature = "ReturnTemperature"


class VesselMetric(str, Enum):
    pressure = "Pressure"


def construct_from_metric_name(metric_name: str, device_kind: DeviceKind) -> MetricType:
    # Currently all the metrics are control points
    if metric_name in [e.value for e in device_metric_mapping[device_kind]]:
        return MetricType.control_point
    return None


DeviceMetricName = Union[CompressorMetric, CondenserMetric, EvaporatorMetric, VesselMetric]


device_metric_mapping = {
    DeviceKind.compressor: CompressorMetric,
    DeviceKind.condenser: CondenserMetric,
    DeviceKind.evaporator: EvaporatorMetric,
    DeviceKind.vessel: VesselMetric,
}


class DeviceMetric(BaseModel):
    name: str = ""
    alias_regex: str = ""  # Use name (preferred) or alias regular expression to match the metric
    device_kind: DeviceKind
    metric_type: MetricType

    @model_validator(mode="before")
    @classmethod
    def auto_fill_metric_type(cls, values):
        """
        Auto-fill metric_type based on device_kind and name if not provided.
        Only does lookup when name is provided (not when using alias_regex).
        """
        if not isinstance(values, dict):
            return values

        # If metric_type is not provided, auto-fill it
        if "metric_type" not in values or values["metric_type"] is None:
            name = values.get("name", "")
            device_kind = values.get("device_kind")

            if name != "" and device_kind:
                values["metric_type"] = construct_from_metric_name(name, device_kind)
            else:
                # If no name provided, we can't auto-fill, so raise an error
                raise ValueError("metric_type must be provided when using alias_regex")
        return values


class Deployment(BaseModel):
    id: str
    agent_id: str
    organization_id: str
    blueprint_version: int


def is_valid_metric(metric: DeviceMetric) -> bool:
    """
    Check if the metric is valid for the given device kind.
    """
    if metric.name != "":
        valid_metrics = [e.value for e in device_metric_mapping[metric.device_kind]]
        return metric.name in valid_metrics
    return metric.alias_regex != ""
