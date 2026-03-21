from uagents import Agent, Context, Bureau
from shared.models import GridSignal, PowerBid, BidResponse
from agents.trucks.bidding import decide_bid
from datetime import datetime

TERMINAL_ADDRESS = "placeholder"  # replace with Person 2's terminal agent address

# --- 3 trucks from different companies, each with private battery state ---
truck1 = Agent(name="amazon_truck", seed="amazon_truck_seed", port=8001)
truck2 = Agent(name="fedex_truck", seed="fedex_truck_seed", port=8002)
truck3 = Agent(name="ups_truck", seed="ups_truck_seed", port=8003)

# Private battery levels — not shared with competitors
amazon_battery = 20.0
fedex_battery = 55.0
ups_battery = 80.0


# ─────────────────────────── AMAZON ───────────────────────────

@truck1.on_message(model=GridSignal)
async def amazon_on_grid(ctx: Context, signal: GridSignal):
    result = decide_bid(amazon_battery, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="amazon_truck",
        battery_level=amazon_battery,
        requested_kwh=50.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    ctx.logger.info(f"Amazon: bidding ${result['bid_price']:.2f}/kWh — {result['reasoning']}")
    await ctx.send(TERMINAL_ADDRESS, bid)

@truck1.on_message(model=BidResponse)
async def amazon_on_response(ctx: Context, response: BidResponse):
    global amazon_battery
    if response.accepted:
        amazon_battery = min(100.0, amazon_battery + 30.0)
        ctx.logger.info(f"Amazon: accepted! Bay {response.bay}, battery now {amazon_battery}%")
    else:
        ctx.logger.info(f"Amazon: rejected, queue position {response.queue_position}")


# ─────────────────────────── FEDEX ───────────────────────────

@truck2.on_message(model=GridSignal)
async def fedex_on_grid(ctx: Context, signal: GridSignal):
    result = decide_bid(fedex_battery, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="fedex_truck",
        battery_level=fedex_battery,
        requested_kwh=40.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    ctx.logger.info(f"FedEx: bidding ${result['bid_price']:.2f}/kWh — {result['reasoning']}")
    await ctx.send(TERMINAL_ADDRESS, bid)

@truck2.on_message(model=BidResponse)
async def fedex_on_response(ctx: Context, response: BidResponse):
    global fedex_battery
    if response.accepted:
        fedex_battery = min(100.0, fedex_battery + 30.0)
        ctx.logger.info(f"FedEx: accepted! Bay {response.bay}, battery now {fedex_battery}%")
    else:
        ctx.logger.info(f"FedEx: rejected, queue position {response.queue_position}")


# ─────────────────────────── UPS ───────────────────────────

@truck3.on_message(model=GridSignal)
async def ups_on_grid(ctx: Context, signal: GridSignal):
    result = decide_bid(ups_battery, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="ups_truck",
        battery_level=ups_battery,
        requested_kwh=30.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    ctx.logger.info(f"UPS: bidding ${result['bid_price']:.2f}/kWh — {result['reasoning']}")
    await ctx.send(TERMINAL_ADDRESS, bid)

@truck3.on_message(model=BidResponse)
async def ups_on_response(ctx: Context, response: BidResponse):
    global ups_battery
    if response.accepted:
        ups_battery = min(100.0, ups_battery + 30.0)
        ctx.logger.info(f"UPS: accepted! Bay {response.bay}, battery now {ups_battery}%")
    else:
        ctx.logger.info(f"UPS: rejected, queue position {response.queue_position}")


# ─────────────────────────── RUN ───────────────────────────

if __name__ == "__main__":
    bureau = Bureau()
    bureau.add(truck1)
    bureau.add(truck2)
    bureau.add(truck3)
    bureau.run()
