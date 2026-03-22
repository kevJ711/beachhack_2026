from uagents import Agent, Context

from shared.models import PowerBid, BidResponse
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

terminal = Agent(name="terminal", seed="terminal_seed")

# Tracks bid queue position across rounds
bid_queue = []


@terminal.on_message(model=PowerBid)
async def handle_bid(ctx: Context, sender: str, bid: PowerBid):
    ctx.logger.info(f"Terminal received bid from {bid.truck_id}: ${bid.bid_price}/kWh")
    reason = (bid.reasoning or "").strip().replace("\n", " ")
    if len(reason) > 220:
        reason = reason[:217] + "..."
    log_event(
        "bid",
        f"BID {bid.truck_id} ${bid.bid_price:.2f}/kWh · batt {bid.battery_level:.0f}% · {reason}",
    )

    # Save bid to Supabase
    bid_id = save_bid(
        truck_name=bid.truck_id,
        battery_level=bid.battery_level,
        requested_kwh=bid.requested_kwh,
        bid_price=bid.bid_price,
        reasoning=bid.reasoning
    )

    # Track queue position
    if bid.truck_id not in bid_queue:
        bid_queue.append(bid.truck_id)
    queue_position = bid_queue.index(bid.truck_id) + 1

    # Try to find and lock an available bay
    bay = get_available_bay()

    if bay:
        locked = lock_bay(bay["id"], bid.truck_id)

        if locked:
            # Winner — bay secured
            update_truck_status(
                bid.truck_id,
                "charging",
                bay["id"],
                state_of_charge=int(bid.battery_level),
            )
            save_bid_response(bid_id, True, bay["id"], bid.bid_price, queue_position)

            response = BidResponse(
                accepted=True,
                bay=bay["name"],
                price_confirmed=bid.bid_price,
                queue_position=queue_position
            )
            ctx.logger.info(f"Terminal: {bid.truck_id} won bay {bay['name']}")
            log_event("win", f"terminal → {bid.truck_id}: ACCEPTED bay={bay['name']} at ${bid.bid_price:.2f}/kWh")

            ctx.logger.info(f"Terminal: awaiting atestfet payment from {bid.truck_id}")
        else:
            # Bay was locked by another truck in a race
            save_bid_response(bid_id, False, None, bid.bid_price, queue_position)
            response = BidResponse(
                accepted=False,
                bay=None,
                price_confirmed=bid.bid_price,
                queue_position=queue_position
            )
            ctx.logger.info(f"Terminal: {bid.truck_id} lost — bay taken")
            log_event("bid", f"terminal → {bid.truck_id}: REJECTED — bay taken by another truck")
    else:
        # No bays available
        save_bid_response(bid_id, False, None, bid.bid_price, queue_position)
        response = BidResponse(
            accepted=False,
            bay=None,
            price_confirmed=bid.bid_price,
            queue_position=queue_position
        )
        ctx.logger.info(f"Terminal: {bid.truck_id} rejected — no bays available")
        log_event("bid", f"terminal → {bid.truck_id}: REJECTED — no bays available")

    await ctx.send(sender, response)


@terminal.on_interval(period=DEMO_CHARGE_TICK_S)
async def demo_charging_tick(ctx: Context) -> None:
    try:
        tick_charging_sessions()
        finalize_trucks_after_port()
    except Exception as e:
        ctx.logger.warning(f"Terminal: charging tick failed — {e}")


if __name__ == "__main__":
    print(f"Terminal agent address: {terminal.address}")
    terminal.run()
