import os
import sys

import orjson
from pydantic import BaseModel

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from atlas import AtlasClient

json_output = "--json" in sys.argv
debug = "--debug" in sys.argv

client = AtlasClient(debug)
facilities = client.list_facilities()

if json_output:
    print(orjson.dumps(facilities, default=lambda x: x.model_dump() if isinstance(x, BaseModel) else x).decode("utf-8"))
    sys.exit(0)

for facility in facilities:
    print(facility.display_name)
    print(f"  Organization ID: {facility.organization_id}")
    print(f"  Agent ID: {facility.agents[0].agent_id}")
    print(f"  Short name: {facility.short_name}")
    print(f"  Address: {facility.address}")
