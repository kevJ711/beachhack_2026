import os
import asyncio
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv
from supabase import create_client, Client
from uagents import Agent, Context, Model
from uagents.setup import fund_agent_if_low

load_dotenv()

# ---------------------------------------------------------------------------
# Config — set these in your .env
# ---------------------------------------------------------------------------
SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_KEY: str = os.environ["SUPABASE_KEY"]

# Truck agent addresses — fill in after each truck agent is registered
TRUCK_AGENT_ADDRESSES: list[str] = os.environ.get(
    "TRUCK_AGENT_ADDRESSES", ""
).split(",")

# GridStatus API — https://api.gridstatus.io/v1
GRIDSTATUS_API_KEY: str = os.environ.get("GRIDSTATUS_API_KEY", "")
GRIDSTATUS_BASE_URL = "https://api.gridstatus.io/v1"

# Dutch Auction parameters
AUCTION_START_PRICE: float = float(os.environ.get("AUCTION_START_PRICE", "0.35"))   # $/kWh
AUCTION_MIN_PRICE: float   = float(os.environ.get("AUCTION_MIN_PRICE",   "0.08"))   # $/kWh
AUCTION_PRICE_STEP: float  = float(os.environ.get("AUCTION_PRICE_STEP",  "0.01"))   # drop per tick
AUCTION_TICK_SECONDS: int  = int(os.environ.get("AUCTION_TICK_SECONDS",  "5"))

# ---------------------------------------------------------------------------
# Shared message models (must match shared/models.py used by truck agents)
# ---------------------------------------------------------------------------

class GridSignal(Model):
    """Broadcast from Grid Agent → Truck Agents every tick."""
    auction_id:       str
    current_price:    float       # $/kWh, dropping each tick
    start_price:      float
    min_price:        float
    renewable_pct:    float       # 0–100 %
    grid_stress:      float       # 0.0–1.0
    ca_iso_zone:      str         # e.g. "CAISO" or the BA name from GridStatus
    timestamp:        str         # ISO-8601 UTC


class AuctionComplete(Model):
    """Sent from Grid Agent → Truck Agents when the auction ends."""
    auction_id: str
    reason:     str   # "price_floor_reached" | "bid_accepted"


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def get_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def upsert_auction(sb: Client, auction_id: str, payload: dict) -> None:
    """Insert or update the single active auction row."""
    sb.table("auction").upsert({"id": auction_id, **payload}).execute()


def log_event(sb: Client, event_type: str, message: str) -> None:
    sb.table("events").insert({
        "type":       event_type,
        "message":    message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# ---------------------------------------------------------------------------
# GridStatus API helpers
# ---------------------------------------------------------------------------

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
        url = f"{GRIDSTATUS_BASE_URL}/datasets/caiso_fuel_mix/latest"
        resp = requests.get(
            url,
            headers=_gridstatus_headers(),
            params={"iso": "caiso", "limit": 1},
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()

        # GridStatus wraps results in {"data": [...]}
        rows = data.get("data", [])
        if not rows:
            raise ValueError("Empty fuel mix response")

        row = rows[0]
        # Sum renewable sources: solar, wind, geothermal, small_hydro, biomass, biogas
        renewable_keys = ["solar", "wind", "geothermal", "small_hydro", "biomass", "biogas"]
        total_mw  = row.get("net_generation", 0) or 1  # avoid div/0
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
        url = f"{GRIDSTATUS_BASE_URL}/datasets/caiso_load/latest"
        resp = requests.get(
            url,
            headers=_gridstatus_headers(),
            params={"iso": "caiso", "limit": 1},
            timeout=8,
        )
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


def fetch_grid_data() -> dict:
    """Merge fuel-mix + load into a single snapshot dict."""
    fuel  = fetch_caiso_fuel_mix()
    load  = fetch_caiso_load()
    return {
        "renewable_pct": fuel["renewable_pct"],
        "grid_stress":   load["grid_stress"],
        "ca_iso_zone":   fuel["ca_iso_zone"],
        "load_mw":       load["load_mw"],
    }


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

grid_agent = Agent(
    name     = "grid_agent",
    seed     = os.environ.get("GRID_AGENT_SEED", "grid_agent_secret_seed"),
    endpoint = os.environ.get("GRID_AGENT_ENDPOINT", "http://127.0.0.1:8001/submit"),
    port     = int(os.environ.get("GRID_AGENT_PORT", "8001")),
)

fund_agent_if_low(grid_agent.wallet.address())


# ---------------------------------------------------------------------------
# Auction state (in-memory; Supabase is source of truth for frontend)
# ---------------------------------------------------------------------------

class AuctionState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.auction_id:    str   = ""
        self.current_price: float = AUCTION_START_PRICE
        self.active:        bool  = False
        self.tick_count:    int   = 0

    def drop_price(self) -> None:
        self.current_price = round(
            max(self.current_price - AUCTION_PRICE_STEP, AUCTION_MIN_PRICE), 4
        )
        self.tick_count += 1

    @property
    def at_floor(self) -> bool:
        return self.current_price <= AUCTION_MIN_PRICE


_state = AuctionState()


# ---------------------------------------------------------------------------
# Startup: create a fresh auction row in Supabase
# ---------------------------------------------------------------------------

@grid_agent.on_event("startup")
async def on_startup(ctx: Context) -> None:
    import uuid
    sb = get_supabase()

    _state.reset()
    _state.auction_id = str(uuid.uuid4())
    _state.active     = True

    # Seed initial row
    upsert_auction(sb, _state.auction_id, {
        "current_price": _state.current_price,
        "start_price":   AUCTION_START_PRICE,
        "min_price":     AUCTION_MIN_PRICE,
        "renewable_pct": 0.0,
        "grid_stress":   0.0,
        "status":        "active",
        "started_at":    datetime.now(timezone.utc).isoformat(),
    })
    log_event(sb, "auction_start", f"Dutch auction {_state.auction_id} started at ${AUCTION_START_PRICE}/kWh")

    ctx.logger.info(f"[GridAgent] Auction {_state.auction_id} started. address={ctx.address}")


# ---------------------------------------------------------------------------
# Main tick: every AUCTION_TICK_SECONDS seconds
# ---------------------------------------------------------------------------

@grid_agent.on_interval(period=AUCTION_TICK_SECONDS)
async def auction_tick(ctx: Context) -> None:
    if not _state.active:
        return

    # 1. Pull live grid data from GridStatus
    grid = fetch_grid_data()

    # 2. Drop price
    _state.drop_price()

    now_iso = datetime.now(timezone.utc).isoformat()

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
    )

    ctx.logger.info(
        f"[GridAgent] Tick #{_state.tick_count} | "
        f"price=${_state.current_price:.4f} | "
        f"renewable={grid['renewable_pct']}% | "
        f"stress={grid['grid_stress']}"
    )

    # 4. Update Supabase (frontend reads this)
    sb = get_supabase()
    upsert_auction(sb, _state.auction_id, {
        "current_price": _state.current_price,
        "renewable_pct": grid["renewable_pct"],
        "grid_stress":   grid["grid_stress"],
        "status":        "active",
    })

    # 5. Broadcast to all truck agents
    for addr in TRUCK_AGENT_ADDRESSES:
        addr = addr.strip()
        if addr:
            await ctx.send(addr, signal)

    # 6. End auction if price has hit the floor
    if _state.at_floor:
        await _end_auction(ctx, reason="price_floor_reached")


# ---------------------------------------------------------------------------
# Listen for a "bid accepted" notification from the Terminal Agent
# ---------------------------------------------------------------------------

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

    await _end_auction(ctx, reason="bid_accepted")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _end_auction(ctx: Context, reason: str) -> None:
    """Mark auction complete, update Supabase, notify all trucks."""
    if not _state.active:
        return

    _state.active = False

    sb = get_supabase()
    upsert_auction(sb, _state.auction_id, {"status": "complete"})
    log_event(sb, "auction_start", f"Auction {_state.auction_id} ended: {reason}")

    complete_msg = AuctionComplete(auction_id=_state.auction_id, reason=reason)
    for addr in TRUCK_AGENT_ADDRESSES:
        addr = addr.strip()
        if addr:
            await ctx.send(addr, complete_msg)

    ctx.logger.info(f"[GridAgent] Auction {_state.auction_id} ended — {reason}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    grid_agent.run()