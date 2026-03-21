from uagents import Agent, Context
from shared.models import PowerBid, BidResponse
from agents.terminal.bay_manager import (
    get_available_bay, lock_bay, save_bid, save_bid_response, update_truck_status
)

terminal = Agent(name="terminal", seed="terminal_seed", port=8010)

# Tracks bid queue position across rounds
bid_queue = []


@terminal.on_message(model=PowerBid)
async def handle_bid(ctx: Context, bid: PowerBid):
    ctx.logger.info(f"Terminal received bid from {bid.truck_id}: ${bid.bid_price}/kWh")

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
            update_truck_status(bid.truck_id, "charging", bay["id"])
            save_bid_response(bid_id, True, bay["id"], bid.bid_price, queue_position)

            response = BidResponse(
                accepted=True,
                bay=bay["name"],
                price_confirmed=bid.bid_price,
                queue_position=queue_position
            )
            ctx.logger.info(f"Terminal: {bid.truck_id} won bay {bay['name']}")

            # Ledger transaction — pay for the charging slot
            try:
                await ctx.ledger.send_tokens(
                    destination=terminal.address,
                    amount=int(bid.bid_price * 100),  # convert to uFET
                    denom="atestfet"
                )
                ctx.logger.info(f"Terminal: ledger tx sent for {bid.truck_id}")
            except Exception as e:
                ctx.logger.warning(f"Terminal: ledger tx failed — {e}")
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

    await ctx.send(ctx.sender, response)


if __name__ == "__main__":
    print(f"Terminal agent address: {terminal.address}")
    terminal.run()
