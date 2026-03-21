from uagents import Agent, Context, Bureau
from shared.models import GridSignal, PowerBid
from agents.trucks.bidding import decide_bid
from datetime import datetime

TERMINAL_ADDRESS = "placeholder"  # replace with Person 4's terminal agent address

TRUCK_1_BATTERY = 20.0
TRUCK_2_BATTERY = 55.0
TRUCK_3_BATTERY = 80.0

truck1 = Agent(name="truck1", seed="truck1_seed", port=8001)
truck2 = Agent(name="truck2", seed="truck2_seed", port=8002)
truck3 = Agent(name="truck3", seed="truck3_seed", port=8003)


@truck1.on_message(model=GridSignal)
async def truck1_handler(ctx: Context, signal: GridSignal):
    result = decide_bid(TRUCK_1_BATTERY, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="truck1",
        battery_level=TRUCK_1_BATTERY,
        requested_kwh=50.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    await ctx.send(TERMINAL_ADDRESS, bid)


@truck2.on_message(model=GridSignal)
async def truck2_handler(ctx: Context, signal: GridSignal):
    result = decide_bid(TRUCK_2_BATTERY, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="truck2",
        battery_level=TRUCK_2_BATTERY,
        requested_kwh=40.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    await ctx.send(TERMINAL_ADDRESS, bid)


@truck3.on_message(model=GridSignal)
async def truck3_handler(ctx: Context, signal: GridSignal):
    result = decide_bid(TRUCK_3_BATTERY, signal.price, signal.grid_stress)
    bid = PowerBid(
        truck_id="truck3",
        battery_level=TRUCK_3_BATTERY,
        requested_kwh=30.0,
        bid_price=result["bid_price"],
        reasoning=result["reasoning"],
        timestamp=datetime.now()
    )
    await ctx.send(TERMINAL_ADDRESS, bid)


if __name__ == "__main__":
    bureau = Bureau()
    bureau.add(truck1)
    bureau.add(truck2)
    bureau.add(truck3)
    bureau.run()
