import os
import random

from shared.supabase_client import supabase
from datetime import datetime, timezone

from postgrest.exceptions import APIError

# Demo: fast charging ramp + release bay when truck reaches port (see tick_charging_sessions)
DEMO_CHARGE_TICK_S: float = float(os.environ.get("DEMO_CHARGE_TICK_S", "0.65"))
DEMO_CHARGE_STEP_PCT: int = int(os.environ.get("DEMO_CHARGE_STEP_PCT", "34"))
# After at_port, dwell then reset to idle so the map can cycle (exit animation + pier)
DEMO_AT_PORT_DWELL_S: float = float(os.environ.get("DEMO_AT_PORT_DWELL_S", "2.8"))

# Matches agents/trucks/agent.py — used when DB was created without seed rows
_TRUCK_DEFAULT_SOC = {"amazon_truck": 20, "fedex_truck": 55, "ups_truck": 80}

# Random inbound SOC bands after a truck “departs” (demo: each return = new load / different batt.)
_INBOUND_SOC_BANDS: dict[str, tuple[int, int]] = {
    "amazon_truck": (14, 30),
    "fedex_truck": (40, 65),
    "ups_truck": (68, 94),
}


def _random_inbound_soc(truck_name: str) -> int:
    lo, hi = _INBOUND_SOC_BANDS.get(truck_name, (25, 55))
    return random.randint(lo, hi)

# Matches supabase/schema_for_frontend_and_agents.sql seed — map UI expects A1, A2, B1, B2
_DEFAULT_BAY_NAMES = ("A1", "A2", "B1", "B2")


def get_truck_id(truck_name: str) -> str:
    """Resolve trucks.id by name, inserting a row if missing (same as schema seed)."""
    r = supabase.table("trucks").select("id").eq("name", truck_name).limit(1).execute()
    if r.data:
        return r.data[0]["id"]
    soc = _TRUCK_DEFAULT_SOC.get(truck_name, 50)
    try:
        ins = supabase.table("trucks").insert(
            {
                "name": truck_name,
                "state_of_charge": soc,
                "distance_to_port": 10,
                "status": "idle",
            }
        ).execute()
        if ins.data:
            return ins.data[0]["id"]
    except APIError:
        pass
    r = supabase.table("trucks").select("id").eq("name", truck_name).limit(1).execute()
    if r.data:
        return r.data[0]["id"]
    raise RuntimeError(f"No truck row for name={truck_name!r} and insert failed")


def log_event(event_type: str, message: str):
    supabase.table("events").insert({
        "type": event_type,
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()


def _seed_bays_if_table_empty() -> None:
    """Insert default bays when the table has no rows (schema seed was never run)."""
    any_row = supabase.table("bays").select("id").limit(1).execute()
    if any_row.data:
        return
    for name in _DEFAULT_BAY_NAMES:
        try:
            supabase.table("bays").insert({"name": name, "status": "available"}).execute()
        except APIError:
            pass


def get_available_bay():
    """Find the first available bay."""
    result = supabase.table("bays").select("*").eq("status", "available").limit(1).execute()
    if result.data:
        return result.data[0]
    _seed_bays_if_table_empty()
    result = supabase.table("bays").select("*").eq("status", "available").limit(1).execute()
    return result.data[0] if result.data else None


def lock_bay(bay_id: str, truck_name: str):
    """Lock a bay for a truck. Returns False if already locked."""
    truck_id = get_truck_id(truck_name)

    # Attempt to lock — only update if still available (prevents race conditions)
    result = supabase.table("bays").update({
        "status": "locked",
        "assigned_truck_id": truck_id,
        "locked_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", bay_id).eq("status", "available").execute()

    return len(result.data) > 0


def save_bid(truck_name: str, battery_level: float, requested_kwh: float, bid_price: float, reasoning: str):
    """Insert a bid into power_bids. Returns the inserted row id."""
    truck_id = get_truck_id(truck_name)

    result = supabase.table("power_bids").insert({
        "truck_id": truck_id,
        "battery_level": int(battery_level),
        "requested_kwh": requested_kwh,
        "bid_price": bid_price,
        "reasoning": reasoning,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()

    return result.data[0]["id"] if result.data else None


def save_bid_response(bid_id: str, accepted: bool, bay_id: str, price_confirmed: float, queue_position: int):
    """Insert a bid response into bid_responses."""
    supabase.table("bid_responses").insert({
        "bid_id": bid_id,
        "accepted": accepted,
        "bay_id": bay_id,
        "price_confirmed": price_confirmed,
        "queue_position": queue_position,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()


def update_truck_status(
    truck_name: str,
    status: str,
    bay_id: str | None = None,
    state_of_charge: int | None = None,
):
    """Update the truck's status and bay assignment."""
    payload = {
        "status": status,
        "bay_id": bay_id,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    if state_of_charge is not None:
        payload["state_of_charge"] = state_of_charge
    supabase.table("trucks").update(payload).eq("name", truck_name).execute()


def release_bay_for_truck(bay_id: str, truck_id: str) -> None:
    supabase.table("bays").update(
        {
            "status": "available",
            "assigned_truck_id": None,
            "locked_at": None,
        }
    ).eq("id", bay_id).eq("assigned_truck_id", truck_id).execute()


def tick_charging_sessions() -> None:
    """Ramp SOC while status=charging; at 100% mark at_port, free the bay (demo loop)."""
    r = (
        supabase.table("trucks")
        .select("id,name,state_of_charge,bay_id")
        .eq("status", "charging")
        .execute()
    )
    rows = r.data or []
    now = datetime.now(timezone.utc).isoformat()
    for row in rows:
        tid = row["id"]
        name = row["name"]
        bay_id = row.get("bay_id")
        soc = int(row["state_of_charge"])
        new_soc = min(100, soc + DEMO_CHARGE_STEP_PCT)
        if new_soc >= 100:
            if bay_id:
                release_bay_for_truck(bay_id, tid)
            supabase.table("trucks").update(
                {
                    "state_of_charge": 100,
                    "status": "at_port",
                    "distance_to_port": 0,
                    "bay_id": None,
                    "last_updated": now,
                }
            ).eq("id", tid).execute()
            log_event(
                "charge_complete",
                f"{name} @ 100% — departed yard (bay cleared)",
            )
        else:
            supabase.table("trucks").update(
                {"state_of_charge": new_soc, "last_updated": now}
            ).eq("id", tid).execute()


def _parse_last_updated(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def finalize_trucks_after_port() -> None:
    """After DEMO_AT_PORT_DWELL_S at `at_port`, reset to idle pier (demo loop)."""
    r = (
        supabase.table("trucks")
        .select("id,name,last_updated")
        .eq("status", "at_port")
        .execute()
    )
    now = datetime.now(timezone.utc)
    for row in r.data or []:
        lu = _parse_last_updated(row.get("last_updated"))
        if lu is None:
            continue
        if (now - lu).total_seconds() < DEMO_AT_PORT_DWELL_S:
            continue
        soc = _random_inbound_soc(row["name"])
        supabase.table("trucks").update(
            {
                "status": "idle",
                "state_of_charge": soc,
                "distance_to_port": 10,
                "bay_id": None,
                "last_updated": now.isoformat(),
            }
        ).eq("id", row["id"]).execute()
        log_event(
            "truck_reset",
            f"New inbound {row['name']} · SOC {soc}% (replaced departed unit)",
        )
