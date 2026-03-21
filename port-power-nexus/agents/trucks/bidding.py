import openai
import os
import json
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def decide_bid(battery_level, price, grid_stress):
    prompt = f"""You are an intelligent energy bidding agent managing a zero-emission electric truck operating at a logistics hub (such as a port, warehouse, or freight terminal).

Your goal is to secure a charging slot at the lowest possible cost while ensuring the truck can continue operating without running out of battery. You must balance urgency, cost efficiency, and grid sustainability.

Current truck status:
- Battery level: {battery_level}% (0% = empty, 100% = full)
- Current electricity price: ${price}/kWh
- Grid stress level: {grid_stress} (low = grid is stable, medium = moderate demand, high = grid is strained)

Bidding rules and strategy:
- If battery is below 20%: this is CRITICAL. Bid aggressively above market price to guarantee a slot. The truck cannot miss this charge.
- If battery is between 20–40%: bid at or slightly above market price. Prioritize securing a slot soon.
- If battery is between 40–60%: bid at market price. A slot is needed but not urgent.
- If battery is between 60–80%: bid slightly below market price. Only charge if it's cost effective.
- If battery is above 80%: bid very low or consider waiting. Charging now is optional.

Grid stress adjustments:
- If grid stress is "high": lower your bid slightly to reduce strain on the grid and support zero-emission grid health. Waiting is encouraged if battery allows.
- If grid stress is "medium": bid normally based on battery level.
- If grid stress is "low": this is the ideal time to charge. Bid competitively to take advantage of clean, affordable energy.

You are operating in a zero-emission freight environment. Prioritize renewable energy windows (low grid stress = higher renewable mix). Charging during low-stress periods benefits the environment and reduces costs.

Based on all of the above, decide:
1. What price per kWh to bid (bid_price) — this must be a float
2. A clear, human-readable explanation of your reasoning (reasoning) — explain why you chose this bid given the battery level, price, and grid stress

Return ONLY a JSON object with exactly these two fields:
- "bid_price": float (your bid in $/kWh)
- "reasoning": string (your explanation, 2-3 sentences)"""
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(response.choices[0].message.content) #parses and returns