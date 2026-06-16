import os
import sys

import orjson
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from atlas import HourlyRate, RateFilter, RatesReader


def print_rates(title: str, rates: list[HourlyRate]) -> None:
    if rates:
        print(title)
        for rate in rates:
            print(f"  {rate.start.isoformat()}: {rate.rate}")


"""
This example retrieves the past 24 hours of rates for the given facility and
prints the rates.
"""
json_output = "--json" in sys.argv
debug = "--debug" in sys.argv
facilities = sys.argv[1:]
if not facilities:
    print("Usage: python read_rates.py <facility1> <facility2> ...")
    sys.exit(1)

filter = RateFilter(facilities=facilities)
rates_result = RatesReader(debug=debug).read(filter)

if json_output:
    print(
        orjson.dumps(rates_result, default=lambda x: x.model_dump() if isinstance(x, BaseModel) else x).decode("utf-8"),
    )
    sys.exit(0)

for facility, rates in rates_result.items():
    print(f"{facility.capitalize()}")
    print_rates("Usage Rate", rates.usage_rate)
    print_rates("Maximum Demand Charge", rates.maximum_demand_charge)
    print_rates("Time of Use Demand Charge", rates.time_of_use_demand_charge)
    print_rates("Day Ahead Market Rate", rates.day_ahead_market_rate)
    print_rates("Real Time Market Rate", rates.real_time_market_rate)
