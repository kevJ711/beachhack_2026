# Port-Power Nexus Terminal Agent

The Terminal Agent is the physical gatekeeper of the port charging infrastructure.

While the Grid Agent runs the market auction, the Terminal Agent manages the actual charging bays—the tangible assets where trucks physically plug in and charge their batteries. It is responsible for the state and allocation of every bay at the port facility.

When a truck wins an auction, the Terminal Agent is the one that locks down a bay, tracks the active charging session, monitors charge progress, handles the queue of incoming trucks, and releases bays when charging is complete. It keeps real-time state of what slots are available, which are currently charging, and which are reserved.

The Terminal Agent also logs all activity—every bid, every bay assignment, every charging event—into the shared database so that the frontend dashboard, fleet managers, and data analysts can see exactly what is happening at the port in real time.

In practice, the Terminal Agent is responsible for:

- managing the pool of physical charging bays
- receiving and queuing bids from truck agents
- locking available bays when trucks win the auction
- tracking charging progress and power delivery
- simulating charge curves for demo purposes
- releasing bays when trucks are fully charged
- logging all operational events to the database
- maintaining the single source of truth for bay availability

The Terminal Agent is where the virtual market meets physical infrastructure. It ensures that every winning bid translates into actual electrons flowing into a truck battery.

## In One Sentence

The Port-Power Nexus Terminal Agent transforms auction winners into real charging operations by managing bays, tracking sessions, and logging all activity.
