import os
import sys
from collections import defaultdict
from typing import Dict, List

import orjson
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from atlas import AtlasClient, Device


class PropertyValue(BaseModel):
    name: str
    kind: str
    bias: str
    alias: str


class DeviceList(BaseModel):
    by_id: Dict[str, Device]
    by_kind: Dict[str, Dict[str, List[Device]]]


def list_devices(facilities: List[str], debug: bool = False) -> DeviceList:
    """
    Return the device across all facilities indexed by facility name, then by
    device kind as well as a dictionary of all devices indexed by device ID.
    """
    client = AtlasClient(debug=debug)
    try:
        facilities = client.filter_facilities(facilities)
    except Exception as e:
        print(f"Error listing facilities: {e}")
        return {}

    by_kind = {}
    by_id = {}
    for facility in sorted(facilities, key=lambda facility: facility.display_name):
        if not facility.agents:
            continue
        device_map = defaultdict(list)
        try:
            devices = client.list_devices(facility.organization_id, facility.agents[0].agent_id)
        except Exception as e:
            print(f"Error listing devices for facility {facility.display_name}: {e}")
            continue
        for device in sorted(devices, key=lambda device: device.name):
            device_map[device.kind].append(device)
            by_id[device.id] = device

        by_kind[facility.display_name] = device_map

    return DeviceList(by_id=by_id, by_kind=by_kind)


if __name__ == "__main__":
    json_output = "--json" in sys.argv
    debug = "--debug" in sys.argv
    facilities = [arg for arg in sys.argv[1:] if not arg.startswith("--")]

    device_list = list_devices(facilities, debug)
    by_kind = device_list.by_kind
    by_id = device_list.by_id

    if json_output:
        print(
            orjson.dumps(by_kind, default=lambda x: x.model_dump() if isinstance(x, BaseModel) else x).decode("utf-8")
        )
        sys.exit(0)

    for facility_name, facility in by_kind.items():
        print(f"Facility: {facility_name}")
        for kind, by_kind in facility.items():
            print(f"  {kind}:")
            for device in by_kind:
                print(f"    {device.name}")
                print("     Control points -----")
                for cp in device.control_points:
                    print(f"      {cp.alias} (type: {cp.type} bias: {cp.bias} unit: {cp.unit}): {cp.id}")
                print("     Metrics -----")
                for metric in device.metrics:
                    print(f"      {metric.alias} (kind: {metric.kind} unit: {metric.unit}): {metric.id}")
                print("     Outputs -----")
                for output in device.outputs:
                    print(f"      {output.alias} (kind: {output.kind} unit: {output.unit}): {output.id}")
                print("     Conditions -----")
                for condition in device.conditions:
                    print(f"      {condition.alias}: {condition.id}")
                print("     Settings -----")
                for setting in device.settings:
                    print(f"      {setting.alias} (kind: {setting.kind} unit: {setting.unit}): {setting.id}")
                for up in device.upstream:
                    print(f"      Upstream: {up.kind} to {by_id[up.device_id].name}")
                for down in device.downstream:
                    print(f"      Downstream: {down.kind} to {by_id[down.device_id].name}")
