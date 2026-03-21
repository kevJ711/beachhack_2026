from uagents import Agent, Context
from shared.models import GridSignal, PowerBid
from agents.trucks.bidding import decide_bid


result = decide_bid(TRUCK_1_BATTERY, signal.price, signal.grid_stress)
