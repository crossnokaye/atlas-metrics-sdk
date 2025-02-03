import os
import sys
import orjson
from collections import defaultdict
from typing import Dict, List
from pydantic import BaseModel
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from atlas import AtlasClient, Device

class PropertyValue(BaseModel):
    name: str
    kind: str
    bias: str
    alias: str

class DeviceList(BaseModel):
    by_id: Dict[str, Device]
    by_kind: Dict[str, Dict[str, List[Device]]]

def list_devices(debug: bool = False) -> DeviceList:
    """
    Return the device across all facilities indexed by facility name, then by
    device kind as well as a dictionary of all devices indexed by device ID.
    """
    client = AtlasClient(debug=debug)
    try:
        facilities = client.list_facilities()
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
    debug ="--debug" in sys.argv

    device_list = list_devices(debug)
    by_kind = device_list.by_kind
    by_id = device_list.by_id

    if json_output:
        print(orjson.dumps(by_kind, default=lambda x: x.model_dump() if isinstance(x, BaseModel) else x).decode("utf-8"))
        sys.exit(0)

    for facility_name, facility in by_kind.items():
        print(f"Facility: {facility_name}")
        for kind, by_kind in facility.items():
            print(f"  {kind}:")
            for device in by_kind:
                print(f"    {device.name}")
                for prop in device.properties:
                    print(f"      {prop.value.name} ({prop.value.kind} {prop.value.bias}): {prop.value.alias}")
                for up in device.upstream:
                    print(f"      Upstream: {up.kind} to {by_id[up.device_id].name}")
                for down in device.downstream:
                    print(f"      Downstream: {down.kind} to {by_id[down.device_id].name}")
