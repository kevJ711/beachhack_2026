# Port-Power Nexus Orchestrator

The orchestrator is the public face of the Port-Power Nexus swarm.

It is the agent that judges, operators, and fleet managers interact with first. Instead of exposing the full swarm and all of its moving parts, the orchestrator gives the system one clear voice.

Its role is to understand a user's request, decide what kind of action is being asked for, and hand that work to the right agents downstream.

If someone says:

> find the cleanest charging slot for Truck_07

the orchestrator interprets that as more than just a sentence. It recognizes the truck, judges the user's intent, understands that the goal is sustainability-focused charging, and then triggers the coordination flow that leads to an actual charging decision.

That is what makes this agent important.

In practice, the orchestrator is responsible for:

- receiving natural-language requests
- identifying what the user wants
- extracting the truck involved
- deciding whether the request is about charging or status
- passing the task to the swarm
- returning the result in a clear, human-readable way

This makes the whole project easier to understand in a demo.

The orchestrator behaves like the head of the system: it listens, interprets, coordinates, and reports back. The other agents do the specialized work, but the orchestrator is what makes the swarm feel usable.

## In One Sentence

The Port-Power Nexus Orchestrator turns a plain-English fleet request into a coordinated charging decision across the swarm.
