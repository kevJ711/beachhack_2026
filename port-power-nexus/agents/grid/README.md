# Port-Power Nexus Grid Agent

The Grid Agent is the market operator of the Port-Power Nexus swarm.

It runs the Dutch auction system that connects electricity supply with truck demand. Rather than first-come-first-served or manual slot allocation, the Grid Agent uses a descending-price auction to discover the true market clearing price for charging slots and ensure sustainable grid operation.

When the orchestrator decides that a truck needs charging, the Grid Agent takes that request and kicks off an auction. It starts at a high price and drops the price by fixed increments every few seconds until either a truck bids or the floor price is reached. This mechanism ensures that trucks bid honestly based on their urgency and the grid's ability to supply clean power.

The Grid Agent is also aware of real-time grid conditions—it monitors grid stress signals (from CAISO or similar grid operators) to understand when renewable energy is abundant and when the grid is strained. This information flows into the auction parameters and gives truck agents the signal they need to make intelligent bidding decisions.

In practice, the Grid Agent is responsible for:

- running Dutch descending-price auctions for charging slots
- monitoring real-time grid stress and clean energy signals
- setting auction parameters (start price, floor price, tick rate)
- communicating auction status to all truck agents
- announcing winners and finalizing assignments
- integrating grid sustainability into the market mechanism

The Grid Agent makes charging fair, efficient, and green—it is the invisible hand that balances supply and demand while keeping a eye on what's good for the electrical grid.

## In One Sentence

The Port-Power Nexus Grid Agent runs a market-driven Dutch auction to allocate charging slots while optimizing for real-time grid sustainability.
