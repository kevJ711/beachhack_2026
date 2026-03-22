import os
from datetime import datetime, timezone

from uagents import Agent, Context

from shared.models import DemoHeartbeat, PowerBid, BidResponse, TruckStatusRequest, TruckStatusResponse
from shared.truck_mapping import truck_label_to_agent_name
from shared.supabase_client import supabase
from agents.terminal.bay_manager import (
    DEMO_CHARGE_TICK_S,
    finalize_trucks_after_port,
    get_available_bay,
    lock_bay,
    log_event,
    save_bid,
    save_bid_response,
    tick_charging_sessions,
    update_truck_status,
)

terminal = Agent(name="terminal", seed="terminal_seed")

GRID_AGENT_ADDRESS = os.environ.get("GRID_AGENT_ADDRESS", "").strip()
# Set e.g. DEMO_GRID_HEARTBEAT_S=60 and GRID_AGENT_ADDRESS to enable grid↔terminal pings.
DEMO_GRID_HEARTBEAT_S = float(os.environ.get("DEMO_GRID_HEARTBEAT_S", "0"))

# Tracks bid queue position across rounds
bid_queue = []
# In-memory bay lock: bay_id -> truck_id (source of truth for this round)
_locked_bays: dict[str, str] = {}

_KNOWN_FLEET_NAMES = frozenset(
    {"amazon_truck", "fedex_truck", "ups_truck", "dhl_truck", "rivian_truck"}
)


def _fleet_name_for_status_query(truck_id: str) -> str | None:
    """Orchestrator sends Truck_01 … or fleet names — map to DB `trucks.name`."""
    mapped = truck_label_to_agent_name(truck_id)
    if mapped:
        return mapped
    tid = (truck_id or "").strip()
    if tid in _KNOWN_FLEET_NAMES:
        return tid
    return None


@terminal.on_message(model=TruckStatusRequest, allow_unverified=True)
async def handle_truck_status_request(ctx: Context, sender: str, msg: TruckStatusRequest) -> None:
    """Answer orchestrator status queries from Supabase (no separate truck-status agent required)."""
    fleet = _fleet_name_for_status_query(msg.truck_id)
    if not fleet:
        await ctx.send(
            msg.reply_to,
            TruckStatusResponse(
                request_id=msg.request_id,
                truck_id=msg.truck_id,
                truck_status="unknown",
                state_of_charge=None,
                distance_to_port=None,
                bay=None,
                timestamp=datetime.now(timezone.utc),
            ),
        )
        ctx.logger.warning(f"Terminal: status request for unrecognized truck id {msg.truck_id!r}")
        return

    row = (
        supabase.table("trucks")
        .select("state_of_charge,distance_to_port,status,bay_id,name")
        .eq("name", fleet)
        .limit(1)
        .execute()
    )
    if not row.data:
        await ctx.send(
            msg.reply_to,
            TruckStatusResponse(
                request_id=msg.request_id,
                truck_id=msg.truck_id,
                truck_status="not_in_hub",
                state_of_charge=None,
                distance_to_port=None,
                bay=None,
                timestamp=datetime.now(timezone.utc),
            ),
        )
        ctx.logger.warning(f"Terminal: no truck row for fleet name {fleet!r}")
        return

    t = row.data[0]
    bay_label: str | None = None
    bid = t.get("bay_id")
    if bid:
        br = supabase.table("bays").select("name").eq("id", bid).limit(1).execute()
        if br.data:
            bay_label = br.data[0].get("name")

    await ctx.send(
        msg.reply_to,
        TruckStatusResponse(
            request_id=msg.request_id,
            truck_id=msg.truck_id,
            truck_status=str(t.get("status") or "idle"),
            state_of_charge=float(t["state_of_charge"]) if t.get("state_of_charge") is not None else None,
            distance_to_port=float(t["distance_to_port"]) if t.get("distance_to_port") is not None else None,
            bay=bay_label,
            timestamp=datetime.now(timezone.utc),
        ),
    )
    ctx.logger.info(f"Terminal: truck status for {msg.truck_id} ({fleet}) → {t.get('status')}")


@terminal.on_event("startup")
async def terminal_startup(ctx: Context):
    # Reset all bays and trucks on startup so stale state doesn't block assignments
    supabase.table("bays").update({
        "status": "available",
        "assigned_truck_id": None,
        "locked_at": None,
    }).neq("id", "00000000-0000-0000-0000-000000000000").execute()
    supabase.table("trucks").update({
        "status": "idle",
        "bay_id": None,
    }).neq("id", "00000000-0000-0000-0000-000000000000").execute()
    _locked_bays.clear()
    ctx.logger.info("Terminal: bays and trucks reset on startup")


@terminal.on_message(model=PowerBid)
async def handle_bid(ctx: Context, sender: str, bid: PowerBid):
    ctx.logger.info(f"Terminal received bid from {bid.truck_id}: ${bid.bid_price}/kWh")
    reason = (bid.reasoning or "").strip().replace("\n", " ")
    if len(reason) > 60:
        reason = reason[:57] + "…"
    log_event(
        "bid",
        f"BID {bid.truck_id} ${bid.bid_price:.2f}/kWh · batt {bid.battery_level:.0f}% · {reason}",
    )

    # Save bid to Supabase
    bid_id = save_bid(
        truck_name=bid.truck_id,
        battery_level=bid.battery_level,
        requested_kwh=bid.requested_kwh,
        bid_price=bid.bid_price,
        reasoning=bid.reasoning
    )

    # Track queue position
    if bid.truck_id not in bid_queue:
        bid_queue.append(bid.truck_id)
    queue_position = bid_queue.index(bid.truck_id) + 1

    # Count available bays and trucks currently waiting (not charging)
    available_bays = get_available_bay(exclude_ids=list(_locked_bays.keys()))
    all_available = supabase.table("bays").select("id").eq("status", "available").execute()
    available_count = len([b for b in (all_available.data or []) if b["id"] not in _locked_bays])
    waiting_trucks = supabase.table("trucks").select("id").in_("status", ["idle", "bidding"]).execute()
    waiting_count = len(waiting_trucks.data or [])

    # If more spots than trucks — direct assign, no auction needed
    direct_assign = available_count >= waiting_count

    bay = available_bays

    if bay:
        _locked_bays[bay["id"]] = bid.truck_id
        lock_bay(bay["id"], bid.truck_id)
        update_truck_status(
            bid.truck_id,
            "charging",
            bay["id"],
            state_of_charge=int(bid.battery_level),
        )
        # If direct assign, use market price instead of bid price
        confirmed_price = bid.bid_price if not direct_assign else bid.bid_price * 0.9
        save_bid_response(bid_id, True, bay["id"], confirmed_price, queue_position)
        response = BidResponse(
            accepted=True,
            bay=bay["name"],
            price_confirmed=confirmed_price,
            queue_position=queue_position
        )
        mode = "DIRECT" if direct_assign else "AUCTION"
        ctx.logger.info(f"Terminal: {bid.truck_id} assigned bay {bay['name']} [{mode}]")
        log_event("win", f"terminal → {bid.truck_id}: {mode} bay={bay['name']} at ${confirmed_price:.2f}/kWh")
    else:
        # All bays full — auction required, reject
        save_bid_response(bid_id, False, None, bid.bid_price, queue_position)
        response = BidResponse(
            accepted=False,
            bay=None,
            price_confirmed=bid.bid_price,
            queue_position=queue_position
        )
        ctx.logger.info(f"Terminal: {bid.truck_id} rejected — no bays available")
        log_event("bid", f"terminal → {bid.truck_id}: REJECTED — no bays available")

    await ctx.send(sender, response)


@terminal.on_interval(period=DEMO_CHARGE_TICK_S)
async def demo_charging_tick(ctx: Context) -> None:
    try:
        tick_charging_sessions()
        finalize_trucks_after_port()
        # Re-sync in-memory locks from Supabase each tick
        locked_in_db = supabase.table("bays").select("id").eq("status", "locked").execute()
        locked_ids = {r["id"] for r in (locked_in_db.data or [])}
        for bay_id in list(_locked_bays.keys()):
            if bay_id not in locked_ids:
                del _locked_bays[bay_id]
    except Exception as e:
        ctx.logger.warning(f"Terminal: charging tick failed — {e}")


if DEMO_GRID_HEARTBEAT_S > 0 and GRID_AGENT_ADDRESS:

    @terminal.on_interval(period=DEMO_GRID_HEARTBEAT_S)
    async def demo_grid_heartbeat(ctx: Context) -> None:
        try:
            await ctx.send(GRID_AGENT_ADDRESS, DemoHeartbeat(msg="terminal_ping"))
        except Exception as e:
            ctx.logger.debug(f"Terminal: grid heartbeat skipped — {e}")


if __name__ == "__main__":
    print(f"Terminal agent address: {terminal.address}")
    terminal.run()
