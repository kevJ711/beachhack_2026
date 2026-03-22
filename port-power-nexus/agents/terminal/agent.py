import asyncio
import os
from datetime import datetime, timezone

from uagents import Agent, Context

from shared.models import (
    AuctionComplete,
    BidResponse,
    DemoHeartbeat,
    PowerBid,
    TruckStatusRequest,
    TruckStatusResponse,
)
from shared.truck_mapping import fleet_index, truck_label_to_agent_name
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
from shared.agent_net import submit_endpoint
from shared.config import truck_agent_addresses_tuple
from shared.agent_wiring import swarm_wiring_log_line

_terminal_port_raw = os.environ.get("TERMINAL_PORT", "").strip()
if _terminal_port_raw:
    _tp = int(_terminal_port_raw, 10)
    terminal = Agent(
        name="terminal",
        seed="terminal_seed",
        port=_tp,
        endpoint=submit_endpoint(_tp),
        mailbox=False,
    )
else:
    terminal = Agent(name="terminal", seed="terminal_seed", mailbox=False)

GRID_AGENT_ADDRESS = os.environ.get("GRID_AGENT_ADDRESS", "").strip()
# Set e.g. DEMO_GRID_HEARTBEAT_S=60 and GRID_AGENT_ADDRESS to enable grid↔terminal pings.
DEMO_GRID_HEARTBEAT_S = float(os.environ.get("DEMO_GRID_HEARTBEAT_S", "0"))

# Tracks bid queue position across rounds
bid_queue = []
# In-memory bay lock: bay_id -> truck_id (source of truth for this round)
_locked_bays: dict[str, str] = {}
# Prevent double settlement if Grid retries
_completed_auctions: set[str] = set()

_TRUCK_ADDRESSES: list[str] = list(truck_agent_addresses_tuple())
_WINNER_STAGGER_S = float(os.environ.get("TERMINAL_WINNER_STAGGER_S", "1.75"))
# How often terminal polls auction_state for completed auctions it hasn't settled yet
_SETTLE_POLL_S = float(os.environ.get("TERMINAL_SETTLE_POLL_S", "2.0"))

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
        "charging_started_at": None,
        "charge_start_soc": None,
    }).neq("id", "00000000-0000-0000-0000-000000000000").execute()
    _locked_bays.clear()
    ctx.logger.info("Terminal: bays and trucks reset on startup")
    ctx.logger.info(f"Terminal: {swarm_wiring_log_line()}")


def _active_auction_id() -> str | None:
    r = (
        supabase.table("auction_state")
        .select("id")
        .eq("status", "active")
        .limit(1)
        .execute()
    )
    if not r.data:
        return None
    return r.data[0]["id"]


def _truck_agent_address(truck_name: str) -> str | None:
    idx = fleet_index(truck_name)
    if idx is None or idx >= len(_TRUCK_ADDRESSES):
        return None
    return _TRUCK_ADDRESSES[idx]


async def settle_auction(ctx: Context, auction_id: str) -> None:
    """After Grid ends the auction: rank bids, assign bays one-by-one, start 20s charge."""
    global bid_queue
    if auction_id in _completed_auctions:
        ctx.logger.info(f"Terminal: settlement already ran for auction {auction_id}")
        return

    rows = (
        supabase.table("power_bids")
        .select("id, truck_id, bid_price, battery_level, created_at")
        .eq("auction_id", auction_id)
        .execute()
    )
    bids = rows.data or []

    # Fallback: auction_id column may not exist yet (run 20250322_charging_auction_columns.sql).
    # If no bids matched by auction_id but bid_queue has trucks, fetch their latest bids directly.
    if not bids and bid_queue:
        ctx.logger.warning(
            f"Terminal: no bids with auction_id={auction_id} — "
            f"falling back to bid_queue {bid_queue} (run migration to fix permanently)"
        )
        tids_r = supabase.table("trucks").select("id").in_("name", bid_queue).execute()
        truck_ids = [r["id"] for r in (tids_r.data or [])]
        if truck_ids:
            fb = (
                supabase.table("power_bids")
                .select("id, truck_id, bid_price, battery_level, created_at")
                .in_("truck_id", truck_ids)
                .order("created_at", desc=False)
                .execute()
            )
            bids = fb.data or []

    if not bids:
        ctx.logger.warning(
            f"Terminal: no bids for auction {auction_id} — bids must store auction_id "
            f"(see supabase/migrations/20250322_charging_auction_columns.sql). "
            f"If bids exist in power_bids without auction_id, settlement cannot match."
        )
        _completed_auctions.add(auction_id)
        bid_queue.clear()
        return

    # Latest bid per truck
    latest_by_truck: dict[str, dict] = {}
    for row in sorted(bids, key=lambda x: x.get("created_at") or ""):
        tid = row.get("truck_id")
        if tid:
            latest_by_truck[str(tid)] = row

    trows = (
        supabase.table("trucks")
        .select("id,name")
        .in_("id", list(latest_by_truck.keys()))
        .execute()
    )
    id_to_name = {str(t["id"]): t["name"] for t in (trows.data or [])}

    candidates: list[tuple[str, str, float, int]] = []
    for tid, row in latest_by_truck.items():
        name = id_to_name.get(tid)
        if not name:
            continue
        candidates.append(
            (
                name,
                str(row["id"]),
                float(row.get("bid_price") or 0),
                int(row.get("battery_level") or 0),
            )
        )
    # Lower $/kWh first, then neediest battery (lower %)
    candidates.sort(key=lambda x: (x[2], x[3]))
    if not candidates:
        ctx.logger.warning(f"Terminal: no candidate trucks after join for auction {auction_id}")
        _completed_auctions.add(auction_id)
        bid_queue.clear()
        return

    ap = (
        supabase.table("auction_state")
        .select("current_price,min_price")
        .eq("id", auction_id)
        .limit(1)
        .execute()
    )
    clearing = 0.35
    if ap.data:
        clearing = float(ap.data[0].get("current_price") or ap.data[0].get("min_price") or 0.35)

    bays_r = (
        supabase.table("bays")
        .select("id,name")
        .eq("status", "available")
        .execute()
    )
    bays = sorted(bays_r.data or [], key=lambda b: b.get("name") or "")
    winners = candidates[: len(bays)]

    for i, (truck_name, bid_row_id, _bp, _bl) in enumerate(winners):
        if i > 0:
            await asyncio.sleep(_WINNER_STAGGER_S)
        bay = bays[i]
        bay_id = bay["id"]
        _locked_bays[bay_id] = truck_name
        if not lock_bay(bay_id, truck_name):
            ctx.logger.warning(f"Terminal: could not lock {bay['name']} for {truck_name}")
            continue

        tr = (
            supabase.table("trucks")
            .select("state_of_charge")
            .eq("name", truck_name)
            .limit(1)
            .execute()
        )
        soc0 = 50
        if tr.data:
            soc0 = int(tr.data[0].get("state_of_charge") or 50)

        now_iso = datetime.now(timezone.utc).isoformat()
        update_truck_status(
            truck_name,
            "charging",
            bay_id,
            soc0,
            charging_started_at=now_iso,
            charge_start_soc=soc0,
        )
        save_bid_response(bid_row_id, True, bay_id, clearing, i + 1)

        addr = _truck_agent_address(truck_name)
        if addr:
            await ctx.send(
                addr,
                BidResponse(
                    accepted=True,
                    bay=bay["name"],
                    price_confirmed=clearing,
                    queue_position=i + 1,
                    pending_auction=False,
                ),
            )

        ctx.logger.info(
            f"Terminal: winner {i + 1}/{len(winners)} — {truck_name} → {bay['name']} @ ${clearing:.2f}/kWh"
        )
        log_event(
            "win",
            f"terminal → {truck_name}: AUCTION_SETTLE bay={bay['name']} at ${clearing:.2f}/kWh",
        )

    _completed_auctions.add(auction_id)
    bid_queue.clear()


@terminal.on_message(model=AuctionComplete, allow_unverified=True)
async def on_auction_complete(ctx: Context, sender: str, msg: AuctionComplete) -> None:
    ctx.logger.info(
        f"Terminal: AuctionComplete from {sender} auction={msg.auction_id} reason={msg.reason!r}"
    )
    await settle_auction(ctx, msg.auction_id)


@terminal.on_message(model=PowerBid)
async def handle_bid(ctx: Context, sender: str, bid: PowerBid):
    ctx.logger.info(f"Terminal received bid from {bid.truck_id}: ${bid.bid_price}/kWh")
    reason = (bid.reasoning or "").strip().replace("\n", " ")
    if len(reason) > 60:
        reason = reason[:57] + "…"

    active_aid = _active_auction_id()
    msg_aid = (getattr(bid, "auction_id", None) or "").strip()

    if active_aid:
        # During live auction: record bid only — no bay until Grid sends AuctionComplete.
        if msg_aid and msg_aid != active_aid:
            await ctx.send(
                sender,
                BidResponse(
                    accepted=False,
                    bay=None,
                    price_confirmed=bid.bid_price,
                    queue_position=0,
                    pending_auction=False,
                ),
            )
            return

        save_aid = active_aid
        bid_id = save_bid(
            truck_name=bid.truck_id,
            battery_level=bid.battery_level,
            requested_kwh=bid.requested_kwh,
            bid_price=bid.bid_price,
            reasoning=bid.reasoning,
            auction_id=save_aid,
        )
        if bid.truck_id not in bid_queue:
            bid_queue.append(bid.truck_id)
        queue_position = bid_queue.index(bid.truck_id) + 1

        update_truck_status(bid.truck_id, "bidding", None, int(bid.battery_level))

        log_event(
            "bid",
            f"BID {bid.truck_id} ${bid.bid_price:.2f}/kWh · batt {bid.battery_level:.0f}% · {reason} (pending settlement)",
        )

        await ctx.send(
            sender,
            BidResponse(
                accepted=False,
                bay=None,
                price_confirmed=bid.bid_price,
                queue_position=queue_position,
                pending_auction=True,
            ),
        )
        return

    # No active auction — legacy path (should be rare)
    log_event(
        "bid",
        f"BID {bid.truck_id} ${bid.bid_price:.2f}/kWh · batt {bid.battery_level:.0f}% · {reason}",
    )

    bid_id = save_bid(
        truck_name=bid.truck_id,
        battery_level=bid.battery_level,
        requested_kwh=bid.requested_kwh,
        bid_price=bid.bid_price,
        reasoning=bid.reasoning,
        auction_id=msg_aid or None,
    )

    if bid.truck_id not in bid_queue:
        bid_queue.append(bid.truck_id)
    queue_position = bid_queue.index(bid.truck_id) + 1

    available_bays = get_available_bay(exclude_ids=list(_locked_bays.keys()))
    all_available = supabase.table("bays").select("id").eq("status", "available").execute()
    available_count = len([b for b in (all_available.data or []) if b["id"] not in _locked_bays])
    waiting_trucks = supabase.table("trucks").select("id").in_("status", ["idle", "bidding"]).execute()
    waiting_count = len(waiting_trucks.data or [])

    direct_assign = available_count >= waiting_count
    bay = available_bays

    if bay:
        _locked_bays[bay["id"]] = bid.truck_id
        lock_bay(bay["id"], bid.truck_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        soc0 = int(bid.battery_level)
        update_truck_status(
            bid.truck_id,
            "charging",
            bay["id"],
            state_of_charge=soc0,
            charging_started_at=now_iso,
            charge_start_soc=soc0,
        )
        confirmed_price = bid.bid_price if not direct_assign else bid.bid_price * 0.9
        save_bid_response(bid_id, True, bay["id"], confirmed_price, queue_position)
        response = BidResponse(
            accepted=True,
            bay=bay["name"],
            price_confirmed=confirmed_price,
            queue_position=queue_position,
            pending_auction=False,
        )
        mode = "DIRECT" if direct_assign else "LEGACY"
        ctx.logger.info(f"Terminal: {bid.truck_id} assigned bay {bay['name']} [{mode}]")
        log_event("win", f"terminal → {bid.truck_id}: {mode} bay={bay['name']} at ${confirmed_price:.2f}/kWh")
    else:
        save_bid_response(bid_id, False, None, bid.bid_price, queue_position)
        response = BidResponse(
            accepted=False,
            bay=None,
            price_confirmed=bid.bid_price,
            queue_position=queue_position,
            pending_auction=False,
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


@terminal.on_interval(period=_SETTLE_POLL_S)
async def poll_completed_auctions(ctx: Context) -> None:
    """Catch any auction_state rows marked complete that we haven't settled yet.
    Handles the case where the AuctionComplete message from Grid was dropped or the
    TERMINAL_AGENT_ADDRESS env var is misconfigured."""
    try:
        r = (
            supabase.table("auction_state")
            .select("id")
            .eq("status", "complete")
            .execute()
        )
        for row in r.data or []:
            aid = row["id"]
            if aid not in _completed_auctions:
                ctx.logger.info(f"Terminal: poll found unsettled completed auction {aid} — settling now")
                await settle_auction(ctx, aid)
    except Exception as e:
        ctx.logger.warning(f"Terminal: poll_completed_auctions failed — {e}")


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
