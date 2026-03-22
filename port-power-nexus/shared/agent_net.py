"""uAgents HTTP host/ports — override via env instead of hardcoding localhost:8000 / 8011–8015.

**Split processes (one terminal each), typical layout:**

- ``python agents/trucks/agent.py`` → ``TRUCKS_BUREAU_PORT=8000`` (all five trucks in one Bureau)
- ``python agents/grid/agent.py`` → ``GRID_AGENT_PORT=8001``
- ``python agents/orchestrator/agent.py`` → ``ORCHESTRATOR_PORT=8002`` (default)
- ``python agents/terminal/agent.py`` → ``TERMINAL_PORT=8003``

When using ``run_all.py``, **unset** ``GRID_AGENT_PORT`` and ``TERMINAL_PORT`` in `.env` so grid/terminal
agents do not bind extra HTTP ports while also joining the shared Bureau.

Environment variables
-----------------------
UAGENTS_HOST       Default ``localhost``.
BUREAU_PORT        Default ``8000`` — ``run_all.py`` shared Bureau only.
TRUCKS_BUREAU_PORT Default ``8000`` — ``agents/trucks/agent.py`` standalone Bureau only.
TRUCK_PORT_BASE    Default ``8011`` — per-truck Agent ports (8011..8015) inside the truck Bureau.
TRUCK_PORTS        Optional — exactly five comma-separated ports (overrides TRUCK_PORT_BASE).
GRID_AGENT_PORT    Optional — grid standalone HTTP port + submit URL.
TERMINAL_PORT      Optional — terminal standalone HTTP port + submit URL.
ORCHESTRATOR_PORT  Default ``8002`` — see ``agents/orchestrator/agent.py``.
ORCHESTRATOR_MAILBOX         Default on — ``false`` uses local ``/submit`` only (no Agentverse
    mailbox). When on, do not set a custom ``endpoint=`` in code; mailbox needs Agentverse URLs.
ORCHESTRATOR_PUBLISH_MANIFEST  Default ``true`` for Agentverse; set ``false`` to skip manifest
    fetch (fewer ``dispenser`` errors if peers are down).
"""

from __future__ import annotations

import os


def uagents_host() -> str:
    return os.environ.get("UAGENTS_HOST", "localhost").strip() or "localhost"


def bureau_port_run_all() -> int:
    """Port for `run_all.py` shared Bureau (grid + trucks + terminal)."""
    return int(os.environ.get("BUREAU_PORT", "8000"))


def trucks_bureau_port() -> int:
    """Port for `python agents/trucks/agent.py` standalone (five trucks in one Bureau)."""
    return int(os.environ.get("TRUCKS_BUREAU_PORT", "8000"))


def truck_ports() -> list[int]:
    """Five truck agent ports. Set `TRUCK_PORTS=p1,p2,...` or `TRUCK_PORT_BASE` (default 8011 → 8011..8015)."""
    raw = os.environ.get("TRUCK_PORTS", "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) != 5:
            raise ValueError(
                "TRUCK_PORTS must list exactly 5 comma-separated ports "
                f"(got {len(parts)}): {raw!r}"
            )
        return [int(p, 10) for p in parts]
    base = int(os.environ.get("TRUCK_PORT_BASE", "8011"))
    return [base + i for i in range(5)]


def submit_endpoint(port: int) -> list[str]:
    """HTTP `submit` URL list for `Agent(..., endpoint=...)`."""
    h = uagents_host()
    return [f"http://{h}:{port}/submit"]
