# Port-Power Nexus Truck Agents

The Truck Agents are the fleet participants in the Port-Power Nexus swarm.

Each truck is an autonomous agent with its own identity, battery state, financial budget, and decision-making logic. When a truck arrives at the port and needs to charge, it doesn't wait for someone else to tell it where to go—it actively participates in the auction by placing bids.

Every truck agent has a sophisticated bidding brain powered by AI. When an auction starts, each truck evaluates its own situation: How low is my battery? How much does charging cost right now? Is the grid stressed or is clean energy abundant? Based on these real-time signals, the truck decides whether to bid aggressively, bid conservatively, or wait. This is not just reactive bidding—it is intelligent, context-aware participation in the market.

The truck agents are also adversarial competitors in the best sense. They bid against each other fairly; high battery levels bid low; critical low-battery trucks bid high. This honest competition is what makes the Dutch auction work and leads to efficient charging allocation across the fleet.

In practice, each Truck Agent is responsible for:

- monitoring its own battery state of charge
- listening to grid signals and electricity prices
- deciding when and how much to bid for a charging slot
- using AI reasoning to justify bids
- communicating bids to the auction
- confirming assignment and moving to a charging bay
- tracking charging progress once assigned
- handling rejection if another truck wins the slot

The Truck Agents embody the intelligence, autonomy, and sustainability of the system. They are not passive; they are active market participants that compete fairly and bid honestly.

## In One Sentence

Port-Power Nexus Truck Agents are autonomous, AI-backed fleet participants that bid intelligently for charging slots based on battery urgency, electricity price, and grid health.
