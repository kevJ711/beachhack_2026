"""Map UI labels (Truck_01 …) to fleet agent names — must match agents/trucks/agent.py order."""

import re
from typing import Optional

# Index matches TRUCK_AGENT_ADDRESSES order (Truck_01 … Truck_05).
TRUCK_INDEX_TO_AGENT: dict[int, str] = {
    1: "amazon_truck",
    2: "fedex_truck",
    3: "ups_truck",
    4: "dhl_truck",
    5: "rivian_truck",
}


def truck_label_to_agent_name(truck_label: str) -> Optional[str]:
    m = re.match(r"Truck_(\d+)", truck_label.strip(), re.IGNORECASE)
    if not m:
        return None
    return TRUCK_INDEX_TO_AGENT.get(int(m.group(1)))


def is_all_trucks_auction(truck_id: str) -> bool:
    return truck_id.strip().lower() in ("", "all", "*")
