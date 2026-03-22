import asyncio
import os
import requests
from dotenv import load_dotenv
import uuid
from datetime import datetime, timezone

load_dotenv()
import shared.env_loader  # noqa: F401 — repo root .env

from supabase import create_client, Client
from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low
from shared.models import (
    AuctionComplete,
    DemoHeartbeat,
    GridSignal,
    AgentErrorResponse,
    AuctionStarted,
    FinalAssignmentResponse,
    StartAuctionRequest,
)
from shared.truck_mapping import is_all_trucks_auction, truck_label_to_agent_name
from shared.config import terminal_agent_address, truck_agent_addresses_tuple
from shared.agent_net import submit_endpoint
from shared.agent_wiring import swarm_wiring_log_line

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_ANON_KEY"]

# Five fleet uAgent addresses (must match running truck agents — same .env everywhere)
TRUCK_AGENT_ADDRESSES: list[str] = list(truck_agent_addresses_tuple())
# Must match trucks' bid target; empty env alone skipped AuctionComplete to terminal (no bay settlement).
TERMINAL_AGENT_ADDRESS: str = terminal_agent_address()

# GridStatus API — https://api.gridstatus.io/v1
GRIDSTATUS_API_KEY: str = os.environ.get("GRIDSTATUS_API_KEY", "")
GRIDSTATUS_BASE_URL = "https://api.gridstatus.io/v1"

# Dutch Auction parameters
AUCTION_START_PRICE: float = float(os.environ.get("AUCTION_START_PRICE", "0.35"))   # $/kWh
AUCTION_MIN_PRICE: float   = float(os.environ.get("AUCTION_MIN_PRICE",   "0.08"))   # $/kWh
AUCTION_PRICE_STEP: float  = float(os.environ.get("AUCTION_PRICE_STEP",  "0.01"))   # drop per tick
# How often the grid drops price and broadcasts (shorter = snappier demo)
AUCTION_TICK_SECONDS: int  = int(os.environ.get("AUCTION_TICK_SECONDS",  "1"))
# Hard cap — auction always ends by this wall time (then terminal settles bids)
AUCTION_DURATION_SECONDS: float = float(os.environ.get("AUCTION_DURATION_SECONDS", "10"))

# grid_stress blends CAISO load (0–1) with charging-bay utilization (locked bays / total bays only).
# 1.0 = 100% weight on bays; 0.0 = CAISO load only. Default 0.75 so bay usage moves the needle.
GRID_STRESS_BAY_WEIGHT: float = float(os.environ.get("GRID_STRESS_BAY_WEIGHT", "0.75"))
# Push latest stress/renewables to auction_state this often (HUD + Realtime) even between auction ticks.
GRID_STRESS_HUD_REFRESH_S: float = float(os.environ.get("GRID_STRESS_HUD_REFRESH_S", "2"))

# GridSignal imported from shared.models — both sides must use the same class.


def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_auction(sb: Client, auction_id: str, payload: dict) -> None:
    """Insert or update the single active auction row."""
    sb.table("auction_state").upsert({"id": auction_id, **payload}).execute()


def update_auction_state(sb: Client, auction_id: str, payload: dict) -> None:
    """Partial update by id — use when only changing a few columns (avoids NOT NULL upsert nulls)."""
    sb.table("auction_state").update(payload).eq("id", auction_id).execute()


def log_event(sb: Client, event_type: str, message: str) -> None:
    sb.table("events").insert({
        "type":       event_type,
        "message":    message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()



def _gridstatus_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if GRIDSTATUS_API_KEY:
        headers["x-api-key"] = GRIDSTATUS_API_KEY
    return headers


def fetch_caiso_fuel_mix() -> dict:
    """
    Returns the latest CAISO fuel mix snapshot from GridStatus.
    Endpoint: GET /datasets/caiso_fuel_mix/latest
    Falls back to neutral defaults if the request fails.
    """
    try:
        url = f"{GRIDSTATUS_BASE_URL}/datasets/caiso_fuel_mix/query"
        resp = requests.get(
            url,
            headers=_gridstatus_headers(),
            params={"limit": 1, "order_by": "interval_start_utc desc"},
            timeout=8,
        )
        if resp.status_code == 429:
            print("[GridAgent] GridStatus rate-limited (429) — using defaults")
            return {"renewable_pct": 0.1, "ca_iso_zone": "CAISO", "raw_row": {}}
        resp.raise_for_status()
        data = resp.json()

        # GridStatus wraps results in {"data": [...]}
        rows = data.get("data", [])
        if not rows:
            raise ValueError("Empty fuel mix response")

        row = rows[0]
        # Sum renewable sources: solar, wind, geothermal, small_hydro, biomass, biogas
        renewable_keys = ["solar", "wind", "geothermal", "small_hydro", "biomass", "biogas"]
        all_keys = ["solar", "wind", "geothermal", "biomass", "biogas", "small_hydro", "coal", "nuclear", "natural_gas", "large_hydro", "batteries", "imports", "other"]
        total_mw  = sum(row.get(k, 0) or 0 for k in all_keys) or 1  # avoid div/0
        renew_mw  = sum(row.get(k, 0) or 0 for k in renewable_keys)
        renewable_pct = round((renew_mw / total_mw) * 100, 1)

        return {
            "renewable_pct": min(renewable_pct, 100.0),
            "ca_iso_zone":   "CAISO",
            "raw_row":       row,
        }

    except Exception as exc:  # noqa: BLE001
        print(f"[GridAgent] GridStatus fuel-mix fetch failed: {exc} — using defaults")
        return {"renewable_pct": 25.0, "ca_iso_zone": "CAISO", "raw_row": {}}


def fetch_caiso_load() -> dict:
    """
    Returns the latest CAISO system load to derive grid_stress (0.0–1.0).
    Endpoint: GET /datasets/caiso_load/latest
    Falls back to 0.5 if the request fails.
    """
    # Rough capacity benchmark for CAISO peak (MW)
    CAISO_PEAK_CAPACITY_MW = 52_000

    try:
        url = f"{GRIDSTATUS_BASE_URL}/datasets/caiso_load/query"
        resp = requests.get(
            url,
            headers=_gridstatus_headers(),
            params={"limit": 1, "order_by": "interval_start_utc desc"},
            timeout=8,
        )
        if resp.status_code == 429:
            print("[GridAgent] GridStatus rate-limited (429) — using defaults")
            return {"grid_stress": 0.5, "load_mw": 0}
        resp.raise_for_status()
        data = resp.json()

        rows = data.get("data", [])
        if not rows:
            raise ValueError("Empty load response")

        load_mw = rows[0].get("load", 0) or 0
        stress  = round(min(load_mw / CAISO_PEAK_CAPACITY_MW, 1.0), 3)
        return {"grid_stress": stress, "load_mw": load_mw}

    except Exception as exc:  # noqa: BLE001
        print(f"[GridAgent] GridStatus load fetch failed: {exc} — using defaults")
        return {"grid_stress": 0.5, "load_mw": 0}


_fuel_load_cache: dict = {}
_fuel_load_cache_time: float = 0.0
GRID_CACHE_SECONDS = 30


def compute_bay_utilization_stress(sb: Client) -> float:
    """0–1: charging bays in use / total bays (non-`available` status = occupied)."""
    try:
        r = sb.table("bays").select("status").execute()
        brows = r.data or []
        if not brows:
            return 0.0
        total_b = len(brows)
        used_b = sum(
            1
            for b in brows
            if (b.get("status") or "").lower() not in ("available",)
        )
        return round(min(1.0, used_b / max(total_b, 1)), 4)
    except Exception as exc:  # noqa: BLE001
        print(f"[GridAgent] bays read for stress failed: {exc}")
        return 0.0


def fetch_grid_data() -> dict:
    """Fuel-mix + CAISO load cached ~30s; bay utilization (locked/total) is read fresh each call."""
    import time

    global _fuel_load_cache, _fuel_load_cache_time
    now = time.time()
    if not _fuel_load_cache or (now - _fuel_load_cache_time) >= GRID_CACHE_SECONDS:
        _fuel_load_cache = {
            "fuel": fetch_caiso_fuel_mix(),
            "load": fetch_caiso_load(),
        }
        _fuel_load_cache_time = now

    fuel = _fuel_load_cache["fuel"]
    load = _fuel_load_cache["load"]
    load_stress = float(load["grid_stress"])

    sb = get_supabase()
    bay_stress = compute_bay_utilization_stress(sb)
    w = max(0.0, min(1.0, GRID_STRESS_BAY_WEIGHT))
    combined = min(1.0, (1.0 - w) * load_stress + w * bay_stress)

    return {
        "renewable_pct": fuel["renewable_pct"],
        "grid_stress": round(combined, 3),
        "grid_stress_load": load_stress,
        "grid_stress_bays": bay_stress,
        "ca_iso_zone": fuel["ca_iso_zone"],
        "load_mw": load["load_mw"],
    }


_grid_port_raw = os.environ.get("GRID_AGENT_PORT", "").strip()
if _grid_port_raw:
    _gp = int(_grid_port_raw, 10)
    grid_agent = Agent(
        name="grid_agent",
        seed=os.environ.get("GRID_AGENT_SEED", "grid_agent_secret_seed"),
        port=_gp,
        endpoint=submit_endpoint(_gp),
        mailbox=False,
    )
else:
    grid_agent = Agent(
        name="grid_agent",
        seed=os.environ.get("GRID_AGENT_SEED", "grid_agent_secret_seed"),
        mailbox=False,
    )

try:
    fund_agent_if_low(grid_agent.wallet.address())
except Exception as _e:
    print(f"[GridAgent] Skipping wallet funding (local Bureau mode): {_e}")



class AuctionState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.auction_id:    str   = ""
        self.current_price: float = AUCTION_START_PRICE
        self.active:        bool  = False
        self.tick_count:    int   = 0
        self.request_id:    str   = ""
        self.reply_to:      str   = ""
        self.target_truck:  str   = ""
        self.requested_goal: str | None = None
        self.trucks_may_bid: bool = False
        self.started_at: datetime | None = None

    def drop_price(self) -> None:
        self.current_price = round(
            max(self.current_price - AUCTION_PRICE_STEP, AUCTION_MIN_PRICE), 4
        )
        self.tick_count += 1

    @property
    def at_floor(self) -> bool:
        return self.current_price <= AUCTION_MIN_PRICE


_state = AuctionState()

# Wall-clock auction end (on_interval does not align with auction start — see AUCTION_TICK_SECONDS).
_auction_duration_task: asyncio.Task | None = None


def _cancel_auction_duration_task() -> None:
    global _auction_duration_task
    if _auction_duration_task is not None and not _auction_duration_task.done():
        _auction_duration_task.cancel()
    _auction_duration_task = None


def _schedule_auction_duration_end(ctx: Context) -> None:
    """End the auction exactly after AUCTION_DURATION_SECONDS, independent of tick interval."""
    _cancel_auction_duration_task()
    global _auction_duration_task

    async def _fire_after_duration() -> None:
        try:
            await asyncio.sleep(max(0.05, float(AUCTION_DURATION_SECONDS)))
            if _state.active:
                ctx.logger.info(
                    f"[GridAgent] Auction {_state.auction_id} wall-clock limit "
                    f"({AUCTION_DURATION_SECONDS:.0f}s) — ending"
                )
                await _end_auction(ctx, reason="time_expired")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            ctx.logger.error(f"[GridAgent] time_expired handler failed: {e}")

    _auction_duration_task = asyncio.create_task(_fire_after_duration())


def _truck_index_from_agent_name(agent_name: str) -> int | None:
    order = ["amazon_truck", "fedex_truck", "ups_truck", "dhl_truck", "rivian_truck"]
    try:
        return order.index(agent_name)
    except ValueError:
        return None


def _is_self_address(ctx: Context, addr: str) -> bool:
    return addr.strip() == ctx.agent.address


def _broadcast_targets(truck_id: str) -> tuple[list[str], str | None]:
    """Addresses that receive GridSignal, and invited_truck_name for the payload (None = any truck)."""
    all_addrs = [a.strip() for a in TRUCK_AGENT_ADDRESSES if a.strip()]
    if is_all_trucks_auction(truck_id):
        return all_addrs, None
    invited = truck_label_to_agent_name(truck_id)
    if not invited:
        return all_addrs, None
    idx = _truck_index_from_agent_name(invited)
    if idx is None or idx < 0 or idx >= len(all_addrs):
        return all_addrs, invited
    return [all_addrs[idx]], invited


@grid_agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    _state.reset()
    n_trucks = len([a for a in TRUCK_AGENT_ADDRESSES if str(a).strip()])
    ctx.logger.info(
        f"[GridAgent] Ready — no auction until orchestrator sends StartAuctionRequest. "
        f"address={ctx.agent.address} | terminal={TERMINAL_AGENT_ADDRESS!r} | "
        f"TRUCK_AGENT_ADDRESSES count={n_trucks}"
    )
    ctx.logger.info(f"[GridAgent] {swarm_wiring_log_line()}")


@grid_agent.on_message(model=DemoHeartbeat)
async def on_demo_heartbeat(ctx: Context, sender: str, msg: DemoHeartbeat) -> None:
    ctx.logger.info(f"[GridAgent] heartbeat from terminal sender={sender} msg={msg.msg!r}")


@grid_agent.on_interval(period=max(1.0, GRID_STRESS_HUD_REFRESH_S))
async def refresh_auction_hud_metrics(ctx: Context) -> None:
    """Keep latest auction_state row in sync with live port stress + renewables (TopBar Realtime)."""
    try:
        sb = get_supabase()
        r = (
            sb.table("auction_state")
            .select("id")
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = r.data or []
        if not rows:
            return
        aid = rows[0]["id"]
        grid = fetch_grid_data()
        update_auction_state(
            sb,
            aid,
            {
                "grid_stress": grid["grid_stress"],
                "renewable_pct": grid["renewable_pct"],
            },
        )
    except Exception as exc:  # noqa: BLE001
        ctx.logger.warning(f"[GridAgent] HUD metrics refresh failed: {exc}")


@grid_agent.on_message(model=StartAuctionRequest)
async def on_start_auction_request(ctx: Context, sender: str, msg: StartAuctionRequest) -> None:
    sb = get_supabase()

    _cancel_auction_duration_task()
    _state.reset()
    _state.auction_id = str(uuid.uuid4())
    _state.active = True
    _state.request_id = msg.request_id
    _state.reply_to = msg.reply_to
    _state.target_truck = msg.truck_id
    _state.requested_goal = msg.requested_goal

    upsert_auction(sb, _state.auction_id, {
        "current_price": AUCTION_START_PRICE,
        "start_price": AUCTION_START_PRICE,
        "min_price": AUCTION_MIN_PRICE,
        "renewable_pct": 0.0,
        "grid_stress": 0.0,
        "status": "active",
        "started_at": datetime.now(timezone.utc).isoformat(),
    })
    log_event(
        sb,
        "auction_start",
        f"Orchestrator requested auction {_state.auction_id} for {msg.truck_id}",
    )

    ctx.logger.info(
        f"[GridAgent] Received StartAuctionRequest request_id={msg.request_id} "
        f"truck={msg.truck_id} sender={sender}"
    )

    addrs, _inv = _broadcast_targets(msg.truck_id)
    if is_all_trucks_auction(msg.truck_id):
        scope_note = f"all {len(addrs)} truck agents may bid."
    else:
        agent = truck_label_to_agent_name(msg.truck_id)
        scope_note = (
            f"only {msg.truck_id} ({agent}) may bid — signals to 1 agent."
            if agent
            else f"auction for {msg.truck_id!r} — signals to {len(addrs)} agent(s)."
        )

    await ctx.send(
        msg.reply_to,
        AuctionStarted(
            request_id=msg.request_id,
            truck_id=msg.truck_id,
            status="accepted",
            note=(
                f"The Dutch auction is live at ${AUCTION_START_PRICE:.2f}/kWh; "
                f"{scope_note} "
                f"Max duration {AUCTION_DURATION_SECONDS:.0f}s."
            ),
            timestamp=datetime.now(timezone.utc),
        ),
    )
    _state.started_at = datetime.now(timezone.utc)
    _state.trucks_may_bid = True
    _schedule_auction_duration_end(ctx)


@grid_agent.on_interval(period=AUCTION_TICK_SECONDS)
async def auction_tick(ctx: Context) -> None:
    if not _state.active:
        return
    if not _state.trucks_may_bid:
        return

    # 1. Pull live grid data from GridStatus
    grid = fetch_grid_data()

    # 2. Drop price
    _state.drop_price()

    now_iso = datetime.now(timezone.utc).isoformat()

    addrs, invited_name = _broadcast_targets(_state.target_truck)

    # 3. Build the signal
    signal = GridSignal(
        auction_id    = _state.auction_id,
        current_price = _state.current_price,
        start_price   = AUCTION_START_PRICE,
        min_price     = AUCTION_MIN_PRICE,
        renewable_pct = grid["renewable_pct"],
        grid_stress   = grid["grid_stress"],
        ca_iso_zone   = grid["ca_iso_zone"],
        timestamp     = now_iso,
        invited_truck_name=invited_name,
    )

    ctx.logger.info(
        f"[GridAgent] Tick #{_state.tick_count} | "
        f"price=${_state.current_price:.4f} | "
        f"renewable={grid['renewable_pct']}% | "
        f"stress={grid['grid_stress']:.2f} "
        f"(load={grid.get('grid_stress_load', 0):.2f} bays={grid.get('grid_stress_bays', 0):.2f})"
    )

    # 4. Update Supabase (frontend reads this)
    sb = get_supabase()
    upsert_auction(sb, _state.auction_id, {
        "current_price": _state.current_price,
        "renewable_pct": grid["renewable_pct"],
        "grid_stress":   grid["grid_stress"],
        "status":        "active",
    })

    # 5. Broadcast to scoped truck agent(s) (throttle feed: every 3rd tick)
    if _state.tick_count % 3 == 0:
        log_event(
            sb,
            "signal",
            f"grid_agent → trucks ({len(addrs)}): price=${_state.current_price:.2f}/kWh | "
            f"renewable={grid['renewable_pct']}% | stress={grid['grid_stress']:.2f}",
        )
    for addr in addrs:
        if _is_self_address(ctx, addr):
            ctx.logger.warning(
                "[GridAgent] TRUCK_AGENT_ADDRESSES includes this grid agent's address — "
                "remove it from .env to avoid receiving your own GridSignal."
            )
            continue
        await ctx.send(addr, signal)

    # 6. End auction if price has hit the floor
    if _state.at_floor:
        await _end_auction(ctx, reason="price_floor_reached")



class BidAccepted(Model):
    """Terminal Agent → Grid Agent: a truck won the auction."""
    auction_id: str
    truck_id:   str
    bay_id:     str
    price_paid: float


@grid_agent.on_message(model=BidAccepted)
async def on_bid_accepted(ctx: Context, sender: str, msg: BidAccepted) -> None:
    if msg.auction_id != _state.auction_id:
        ctx.logger.warning(f"[GridAgent] Stale BidAccepted for auction {msg.auction_id} — ignoring")
        return

    ctx.logger.info(
        f"[GridAgent] Bid accepted! truck={msg.truck_id} bay={msg.bay_id} "
        f"price=${msg.price_paid:.4f}"
    )

    sb = get_supabase()
    log_event(
        sb,
        "win",
        f"Truck {msg.truck_id} won bay {msg.bay_id} at ${msg.price_paid:.4f}/kWh",
    )

    if _state.reply_to and _state.request_id:
        await ctx.send(
            _state.reply_to,
            FinalAssignmentResponse(
                request_id=_state.request_id,
                truck_id=msg.truck_id,
                status="completed",
                decision_summary=(
                    f"{msg.truck_id} won the charging auction after the price dropped "
                    "into its bidding threshold."
                ),
                bay=msg.bay_id,
                price=msg.price_paid,
                tx_hash=None,
                timestamp=datetime.now(timezone.utc),
            ),
        )

    await _end_auction(ctx, reason="bid_accepted")


async def _end_auction(ctx: Context, reason: str) -> None:
    """Mark auction complete, update Supabase, notify all trucks."""
    if not _state.active:
        return

    _cancel_auction_duration_task()

    _state.active = False
    _state.trucks_may_bid = False

    sb = get_supabase()
    update_auction_state(sb, _state.auction_id, {"status": "complete"})
    log_event(sb, "auction_end", f"Auction {_state.auction_id} ended: {reason}")

    complete_msg = AuctionComplete(auction_id=_state.auction_id, reason=reason)
    if TERMINAL_AGENT_ADDRESS and not _is_self_address(ctx, TERMINAL_AGENT_ADDRESS):
        try:
            await ctx.send(TERMINAL_AGENT_ADDRESS, complete_msg)
        except Exception as e:
            ctx.logger.warning(f"[GridAgent] notify terminal of auction end failed: {e}")
    for addr in TRUCK_AGENT_ADDRESSES:
        addr = addr.strip()
        if not addr:
            continue
        if _is_self_address(ctx, addr):
            continue
        await ctx.send(addr, complete_msg)

    if reason == "price_floor_reached" and _state.reply_to and _state.request_id:
        await ctx.send(
            _state.reply_to,
            AgentErrorResponse(
                request_id=_state.request_id,
                source_agent="grid_agent",
                error_message=(
                    f"The auction for {_state.target_truck or 'the requested truck'} "
                    "reached the price floor before any winning bid was accepted."
                ),
                timestamp=datetime.now(timezone.utc),
            ),
        )

    ctx.logger.info(f"[GridAgent] Auction {_state.auction_id} ended — {reason}")


if __name__ == "__main__":
    grid_agent.run()
