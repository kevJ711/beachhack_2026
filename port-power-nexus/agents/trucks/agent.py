import random
from uagents import Agent, Context, Bureau
from shared.models import AuctionComplete, GridSignal, PowerBid, BidResponse
from shared.supabase_client import supabase
from agents.trucks.bidding import decide_bid
from datetime import datetime

TERMINAL_ADDRESS = "agent1q2dsyxc0g3482s3cewzss6vf4gakd2r8znask0gpmqrnvm0p5n0fy9gsulk"

# Starting virtual credits per truck (USD)
STARTING_BALANCE = {
    "amazon_truck": 200.0,
    "fedex_truck":  200.0,
    "ups_truck":    200.0,
    "dhl_truck":    200.0,
    "rivian_truck": 200.0,
}


def _truck_state_from_hub(truck_name: str, fallback_soc: float) -> tuple[float, int]:
    r = (
        supabase.table("trucks")
        .select("state_of_charge,distance_to_port")
        .eq("name", truck_name)
        .limit(1)
        .execute()
    )
    if r.data:
        return float(r.data[0]["state_of_charge"]), int(r.data[0].get("distance_to_port") or 10)
    return fallback_soc, 10


def _get_balance(truck_name: str) -> float:
    r = supabase.table("trucks").select("balance").eq("name", truck_name).limit(1).execute()
    if r.data and r.data[0]["balance"] is not None:
        return float(r.data[0]["balance"])
    return STARTING_BALANCE.get(truck_name, 500.0)


def _set_balance(truck_name: str, balance: float) -> None:
    supabase.table("trucks").update({"balance": round(balance, 2)}).eq("name", truck_name).execute()


def stress_label(stress: float) -> str:
    if stress < 0.33:
        return "low"
    if stress < 0.66:
        return "medium"
    return "high"


DESTINATIONS = [
    "Oakland", "San Diego", "Fresno", "Sacramento", "Las Vegas", "Phoenix", "Seattle",
    "Denver", "Salt Lake City", "Portland", "Reno", "Tucson", "Albuquerque",
    "Chicago", "Dallas", "Houston",
]

def _randomize_truck(truck_name: str, battery_ref: list) -> dict:
    soc = random.randint(10, 95)
    distance = random.randint(5, 40)
    hours_until_deadline = random.randint(20, 120)  # 20-120 minutes until departure
    destination = random.choice(DESTINATIONS)
    battery_ref[0] = float(soc)
    # Core columns only — destination / hours_until_deadline require DB migration (see supabase/).
    supabase.table("trucks").update({
        "state_of_charge": soc,
        "distance_to_port": distance,
        "status": "idle",
    }).eq("name", truck_name).execute()
    return {"hours_until_deadline": hours_until_deadline, "destination": destination}


def _make_startup(truck_name: str, battery_ref: list, meta_ref: dict):
    async def _startup(ctx: Context):
        starting = STARTING_BALANCE.get(truck_name, 50.0)
        _set_balance(truck_name, starting)
        info = _randomize_truck(truck_name, battery_ref)
        meta_ref.update(info)
        ctx.logger.info(
            f"{truck_name}: balance=${starting:.2f} | SOC={battery_ref[0]:.0f}% | "
            f"dest={info['destination']} | deadline={info['hours_until_deadline']}h"
        )
    return _startup


BATTERY_CAPACITY_KWH = 500.0  # Tesla Semi-class heavy EV freight truck

DEST_DISTANCES = {
    "Oakland": 50, "San Diego": 120, "Fresno": 185, "Sacramento": 90,
    "Las Vegas": 270, "Phoenix": 370, "Seattle": 1140,
    "Denver": 1020, "Salt Lake City": 690, "Portland": 1080,
    "Reno": 480, "Tucson": 490, "Albuquerque": 790,
    "Chicago": 2020, "Dallas": 1430, "Houston": 1550,
}

def _calc_requested_kwh(battery_level: float, destination: str) -> float:
    trip_miles = DEST_DISTANCES.get(destination, 150)
    battery_needed_pct = min(95, round(trip_miles * 0.35 + 15))
    shortfall_pct = max(0, battery_needed_pct - battery_level)
    # If no shortfall, request a small top-up (10%) so the truck still considers charging
    if shortfall_pct == 0:
        return round(0.10 * BATTERY_CAPACITY_KWH, 1)
    return round((shortfall_pct / 100) * BATTERY_CAPACITY_KWH, 1)


def _make_on_grid(truck_name: str, requested_kwh: float, battery_ref: list, meta_ref: dict):
    async def _on_grid(ctx: Context, sender: str, signal: GridSignal):
        invited = getattr(signal, "invited_truck_name", None)
        if invited and invited != truck_name:
            ctx.logger.info(
                f"{truck_name}: skipping auction {signal.auction_id} — "
                f"invited fleet agent is {invited}"
            )
            return

        battery_ref[0], distance = _truck_state_from_hub(truck_name, battery_ref[0])
        balance = _get_balance(truck_name)
        destination = meta_ref.get("destination", "Unknown")
        dynamic_kwh = _calc_requested_kwh(battery_ref[0], destination)
        result = decide_bid(
            battery_ref[0],
            signal.current_price,
            stress_label(signal.grid_stress),
            distance_to_port=distance,
            requested_kwh=dynamic_kwh,
            balance=balance,
            hours_until_deadline=meta_ref.get("hours_until_deadline", 4),
            destination=destination,
        )
        bid = PowerBid(
            truck_id=truck_name,
            battery_level=battery_ref[0],
            requested_kwh=dynamic_kwh,
            bid_price=result["bid_price"],
            reasoning=result["reasoning"],
            timestamp=datetime.now()
        )
        ctx.logger.info(f"{truck_name}: bidding ${result['bid_price']:.2f}/kWh — {result['reasoning']}")
        await ctx.send(TERMINAL_ADDRESS, bid)
    return _on_grid


def _make_on_auction_complete(truck_name: str):
    async def _on_complete(ctx: Context, sender: str, msg: AuctionComplete) -> None:
        ctx.logger.info(f"{truck_name}: auction {msg.auction_id} finished ({msg.reason})")

    return _on_complete


def _make_on_response(truck_name: str, battery_ref: list, meta_ref: dict):
    async def _on_response(ctx: Context, sender: str, response: BidResponse):
        if response.accepted:
            battery_ref[0], _ = _truck_state_from_hub(truck_name, battery_ref[0])
            kwh = _calc_requested_kwh(battery_ref[0], meta_ref.get("destination", "Unknown"))
            cost = round(response.price_confirmed * kwh, 2)
            balance = _get_balance(truck_name)
            new_balance = max(0.0, balance - cost)
            _set_balance(truck_name, new_balance)
            ctx.logger.info(
                f"{truck_name}: charging at bay {response.bay} — "
                f"SOC {battery_ref[0]:.0f}% | paid ${cost:.2f} | balance ${new_balance:.2f}"
            )
        else:
            ctx.logger.info(f"{truck_name}: rejected, queue position {response.queue_position}")
    return _on_response


# ─────────────────────────── TRUCK DEFINITIONS ───────────────────────────

_TRUCKS = [
    ("amazon_truck", "amazon_truck_seed", 8011),
    ("fedex_truck",  "fedex_truck_seed",  8012),
    ("ups_truck",    "ups_truck_seed",    8013),
    ("dhl_truck",    "dhl_truck_seed",    8014),
    ("rivian_truck", "rivian_truck_seed", 8015),
]

_agents = {}
for _name, _seed, _port in _TRUCKS:
    _agent = Agent(name=_name, seed=_seed, port=_port, endpoint=[f"http://localhost:{_port}/submit"])
    _batt = [float(random.randint(10, 95))]
    _meta = {"hours_until_deadline": random.randint(20, 120), "destination": random.choice(DESTINATIONS)}

    _agent.on_event("startup")(_make_startup(_name, _batt, _meta))
    _agent.on_message(model=GridSignal)(_make_on_grid(_name, 0, _batt, _meta))
    _agent.on_message(model=AuctionComplete)(_make_on_auction_complete(_name))
    _agent.on_message(model=BidResponse)(_make_on_response(_name, _batt, _meta))

    _agents[_name] = _agent

truck1 = _agents["amazon_truck"]
truck2 = _agents["fedex_truck"]
truck3 = _agents["ups_truck"]
truck4 = _agents["dhl_truck"]
truck5 = _agents["rivian_truck"]


# ─────────────────────────── RUN ───────────────────────────

if __name__ == "__main__":
    bureau = Bureau()
    for _agent in _agents.values():
        bureau.add(_agent)
    bureau.run()
