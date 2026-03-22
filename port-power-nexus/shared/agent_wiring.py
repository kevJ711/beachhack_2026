"""Single place to resolve swarm peer addresses (split processes / different ports).

HTTP ports (BUREAU_PORT, GRID_AGENT_PORT, …) are separate from uAgent identity addresses.
Every process must share the same GRID_AGENT_ADDRESS, TERMINAL_AGENT_ADDRESS, and
TRUCK_AGENT_ADDRESSES in `.env` so ctx.send targets match running agents.
"""

from __future__ import annotations

from shared.config import load_orchestrator_settings


def swarm_wiring_log_line() -> str:
    """One-line summary for startup logs (split-stack debugging)."""
    s = load_orchestrator_settings()
    t = s.addresses.truck_agents
    return (
        f"swarm wiring — grid={s.addresses.grid_agent!r} "
        f"terminal={s.addresses.terminal_agent!r} "
        f"status_agent={s.addresses.truck_status_agent!r} "
        f"fleet[{len(t)}]={list(t)}"
    )
