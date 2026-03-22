from shared.supabase_client import supabase
from datetime import datetime, timezone


def log_event(event_type: str, message: str):
    supabase.table("events").insert({
        "type": event_type,
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat()
    }).execute()


def get_available_bay():
    """Find the first available bay."""
    result = supabase.table("bays").select("*").eq("status", "available").limit(1).execute()
    if result.data:
        return result.data[0]
    return None


def lock_bay(bay_id: str, truck_name: str):
    """Lock a bay for a truck. Returns False if already locked."""
    # Get truck UUID from name
    truck = supabase.table("trucks").select("id").eq("name", truck_name).single().execute()
    if not truck.data:
        return False
    truck_id = truck.data["id"]

    # Attempt to lock — only update if still available (prevents race conditions)
    result = supabase.table("bays").update({
        "status": "locked",
        "assigned_truck_id": truck_id,
        "locked_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", bay_id).eq("status", "available").execute()

    return len(result.data) > 0


def save_bid(truck_name: str, battery_level: float, requested_kwh: float, bid_price: float, reasoning: str):
    """Insert a bid into power_bids. Returns the inserted row id."""
    truck = supabase.table("trucks").select("id").eq("name", truck_name).single().execute()
    truck_id = truck.data["id"] if truck.data else None

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


def update_truck_status(truck_name: str, status: str, bay_id: str = None):
    """Update the truck's status and bay assignment."""
    supabase.table("trucks").update({
        "status": status,
        "bay_id": bay_id,
        "last_updated": datetime.now(timezone.utc).isoformat()
    }).eq("name", truck_name).execute()
