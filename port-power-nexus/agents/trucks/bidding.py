import openai
import os
import json
from dotenv import load_dotenv
import shared.env_loader  # noqa: F401 — repo root .env

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

_FALLBACK_BID = {"bid_price": 0.20, "reasoning": "Fallback bid — AI unavailable."}

def decide_bid(battery_level, price, grid_stress, distance_to_port=10, requested_kwh=40.0, balance=50.0, hours_until_deadline=4, destination="Unknown"):
    total_cost = round(price * requested_kwh, 2)
    budget_pct = round((total_cost / balance) * 100, 1) if balance > 0 else 100
    # Estimate battery % needed for the trip (rough: 1% per mile for heavy EV truck, +15% buffer)
    DEST_DISTANCES = {
        "Oakland": 50, "San Diego": 120, "Fresno": 185, "Sacramento": 90,
        "Las Vegas": 270, "Phoenix": 370, "Seattle": 1140,
        "Denver": 1020, "Salt Lake City": 690, "Portland": 1080,
        "Reno": 480, "Tucson": 490, "Albuquerque": 790,
        "Chicago": 2020, "Dallas": 1430, "Houston": 1550,
    }
    trip_miles = DEST_DISTANCES.get(destination, 150)
    battery_needed_pct = min(95, round(trip_miles * 0.35 + 15))  # ~0.35% per mile + 15% buffer
    can_make_trip = battery_level >= battery_needed_pct
    shortfall = max(0, battery_needed_pct - battery_level)

    prompt = f"""You are an autonomous AI bidding agent for a zero-emission electric freight truck competing in a real-time Dutch auction for a charging bay at a smart port.

MISSION: Win a charging slot at the lowest price that still guarantees your truck completes its delivery on time. Every dollar saved is profit. Every missed delivery is a failure.

YOUR TRUCK'S SITUATION:
- Battery: {battery_level:.0f}% charged
- Needs {battery_needed_pct}% to reach {destination} ({trip_miles} miles away) — {"YOU CAN MAKE THE TRIP" if can_make_trip else f"YOU ARE {shortfall:.0f}% SHORT — YOU CANNOT MAKE THE TRIP WITHOUT CHARGING"}
- Departure deadline: {hours_until_deadline} minute(s) from now
- Distance to charging port: {distance_to_port} miles away
- Budget remaining: ${balance:.2f}
- This charge ({requested_kwh} kWh) costs ${total_cost} at current price (${price}/kWh) = {budget_pct}% of your budget

GRID CONDITIONS:
- Electricity price: ${price}/kWh (Dutch auction — price drops every 5 seconds, first to bid wins)
- Grid stress: {grid_stress} (low = cheap clean renewable energy available, high = expensive dirty grid)

DECISION FRAMEWORK — think like a logistics optimizer:
1. CAN YOU MAKE THE TRIP WITHOUT CHARGING? If yes and deadline > 60min, consider skipping or bidding very low.
2. HOW URGENT IS YOUR DEADLINE? Under 30min with insufficient battery = bid whatever it takes.
3. WHAT IS THE GRID DOING? Low stress = renewable energy window, great time to charge cheap and clean.
4. WHAT CAN YOU AFFORD? If this charge burns >50% of budget, be conservative unless it's critical.
5. DUTCH AUCTION LOGIC: The price is dropping — wait for a better price if you can afford to, but don't wait so long another truck wins.

BIDDING RULES:
- CRITICAL (can't make trip + deadline < 30min): Bid 15–25% above market price. Do not lose this slot.
- URGENT (can't make trip + deadline 30–60min): Bid 5–10% above market price.
- NEEDED (can't make trip + deadline > 60min OR battery < 40%): Bid at market price.
- OPTIONAL (can make trip, battery > 60%): Bid 10–20% below market price or skip.
- SKIP (can make trip, battery > 80%, deadline > 90min): Bid very low (${price * 0.5:.2f}) — only take it if it's basically free.

Return ONLY valid JSON:
- "bid_price": float — your bid in $/kWh, rounded to 2 decimal places
- "reasoning": string — ONE short sentence (max 12 words) stating the key reason: e.g. "Low battery, must reach Chicago, deadline in 2h." """
    try:
        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            timeout=10,
        )
        result = json.loads(response.choices[0].message.content)
        # Clamp bid_price to a sane range ($0.01 – $2.00/kWh)
        result["bid_price"] = round(max(0.01, min(2.0, float(result["bid_price"]))), 2)
        return result
    except Exception:
        return _FALLBACK_BID