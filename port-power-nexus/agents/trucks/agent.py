from uagents import Agent, Context, Bureau
from uagents.setup import fund_agent_if_low
from shared.models import GridSignal, PowerBid, BidResponse
from shared.supabase_client import supabase
from agents.trucks.bidding import decide_bid
from datetime import datetime

TERMINAL_ADDRESS = "agent1q2dsyxc0g3482s3cewzss6vf4gakd2r8znask0gpmqrnvm0p5n0fy9gsulk"
TERMINAL_WALLET = "fetch1xz6mhfxl79l47r3x5n4lclrfs46rr8k26g9yt7"  # terminal agent wallet


def _soc_from_hub(truck_name: str, fallback: float) -> float:
    r = (
        supabase.table("trucks")
        .select("state_of_charge")
        .eq("name", truck_name)
        .limit(1)
        .execute()
    )
    if r.data:
        return float(r.data[0]["state_of_charge"])
    return fallback


def stress_label(stress: float) -> str:
    if stress < 0.33:
        return "low"
    if stress < 0.66:
        return "medium"
    return "high"

# --- 3 trucks from different companies, each with private battery state ---
truck1 = Agent(name="amazon_truck", seed="amazon_truck_seed")
truck2 = Agent(name="fedex_truck", seed="fedex_truck_seed")
truck3 = Agent(name="ups_truck", seed="ups_truck_seed")

def _update_balance(truck_name: str, balance_atestfet: int) -> None:
    supabase.table("trucks").update({"balance": balance_atestfet}).eq("name", truck_name).execute()


def _make_startup(agent: Agent, truck_name: str):
    async def _startup(ctx: Context):
        fund_agent_if_low(agent.wallet.address())
        balance = ctx.ledger.query_bank_balance(agent.wallet.address())
        _update_balance(truck_name, int(balance))
        ctx.logger.info(f"{truck_name} wallet: {agent.wallet.address()} | balance: {balance} atestfet")
    return _startup


def _make_on_grid(agent: Agent, truck_name: str, requested_kwh: float, battery_ref: list):
    async def _on_grid(ctx: Context, sender: str, signal: GridSignal):
        battery_ref[0] = _soc_from_hub(truck_name, battery_ref[0])
        result = decide_bid(battery_ref[0], signal.current_price, stress_label(signal.grid_stress))
        bid = PowerBid(
            truck_id=truck_name,
            battery_level=battery_ref[0],
            requested_kwh=requested_kwh,
            bid_price=result["bid_price"],
            reasoning=result["reasoning"],
            timestamp=datetime.now()
        )
        ctx.logger.info(f"{truck_name}: bidding ${result['bid_price']:.2f}/kWh — {result['reasoning']}")
        await ctx.send(TERMINAL_ADDRESS, bid)
    return _on_grid


def _make_on_response(agent: Agent, truck_name: str, requested_kwh: float, battery_ref: list):
    async def _on_response(ctx: Context, sender: str, response: BidResponse):
        if response.accepted:
            battery_ref[0] = _soc_from_hub(truck_name, battery_ref[0])
            ctx.logger.info(f"{truck_name}: charging at bay {response.bay} — SOC {battery_ref[0]:.0f}% (hub)")
            cost_atestfet = int(response.price_confirmed * requested_kwh * 1_000_000)
            try:
                ctx.ledger.send_tokens(
                    destination=TERMINAL_WALLET,
                    amount=cost_atestfet,
                    denom="atestfet",
                    sender=agent.wallet,
                    memo=f"charge-{truck_name}-{response.bay}",
                )
                new_balance = ctx.ledger.query_bank_balance(agent.wallet.address())
                _update_balance(truck_name, int(new_balance))
                ctx.logger.info(f"{truck_name}: paid {cost_atestfet} atestfet | remaining: {new_balance}")
            except Exception as e:
                ctx.logger.warning(f"{truck_name}: payment failed — {e}")
        else:
            ctx.logger.info(f"{truck_name}: rejected, queue position {response.queue_position}")
    return _on_response


# ─────────────────────────── TRUCK DEFINITIONS ───────────────────────────

_TRUCKS = [
    ("amazon_truck", "amazon_truck_seed", 8011, 50.0, 20.0),
    ("fedex_truck",  "fedex_truck_seed",  8012, 40.0, 55.0),
    ("ups_truck",    "ups_truck_seed",    8013, 30.0, 80.0),
    ("dhl_truck",    "dhl_truck_seed",    8014, 45.0, 35.0),
    ("rivian_truck", "rivian_truck_seed", 8015, 60.0, 10.0),
]

_agents = {}
for _name, _seed, _port, _kwh, _soc in _TRUCKS:
    _agent = Agent(name=_name, seed=_seed, port=_port, endpoint=[f"http://localhost:{_port}/submit"])
    _batt = [_soc]

    def _make_balance_poll(a: Agent, n: str):
        async def _poll(ctx: Context):
            try:
                bal = ctx.ledger.query_bank_balance(a.wallet.address())
                _update_balance(n, int(bal))
            except Exception:
                pass
        return _poll

    _agent.on_event("startup")(_make_startup(_agent, _name))
    _agent.on_message(model=GridSignal)(_make_on_grid(_agent, _name, _kwh, _batt))
    _agent.on_message(model=BidResponse)(_make_on_response(_agent, _name, _kwh, _batt))
    _agent.on_interval(period=30.0)(_make_balance_poll(_agent, _name))

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
