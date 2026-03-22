import shared.env_loader  # noqa: F401 — repo root .env

import os
from dataclasses import dataclass

# Default uAgent addresses (seeds unchanged) — used only if TRUCK_AGENT_ADDRESSES is unset.
_DEFAULT_GRID_AGENT = "agent1qdrkj8c6caq7tdmk04r3277ekaukfg7ztxncx0alpddflgz995k4xun8nut"
_DEFAULT_TRUCKS = (
    "agent1qt64xcals30mgjk0vgjykjen7j6wq0m3mp4ny0k5ymnpkaeadmxtqz3hp36",
    "agent1q0n4pnt8c25efcfzj3v9fwxp6fqw6lmn0yy279czrsem9hzvftgz7n4nmsq",
    "agent1qtelk9cdqsacsyz6re8edxugphks6z6cgaynn0q5w87m9h3x0zrqxxyslsx",
    "agent1qgrx8lknhs008wqrhjh89xm492mqcfstv7j0nm8p3jnnwgngytme6nq3dkt",
    "agent1qth5rcrwwetfhnmqx0y8gxatdh2xvrcju69ytewm0nsg2zntqluhx4xycww",
)


def truck_agent_addresses_tuple() -> tuple[str, ...]:
    """Five fleet agent addresses (amazon → rivian). Prefer TRUCK_AGENT_ADDRESSES in .env."""
    raw = os.getenv("TRUCK_AGENT_ADDRESSES", "").strip()
    if raw:
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if len(parts) == 5:
            return tuple(parts)
        if parts:
            raise ValueError(
                "TRUCK_AGENT_ADDRESSES must list exactly 5 comma-separated uAgent addresses "
                f"(got {len(parts)}). Do not include grid or terminal."
            )
    return (
        os.getenv("AMAZON_TRUCK_AGENT_ADDRESS", _DEFAULT_TRUCKS[0]),
        os.getenv("FEDEX_TRUCK_AGENT_ADDRESS", _DEFAULT_TRUCKS[1]),
        os.getenv("UPS_TRUCK_AGENT_ADDRESS", _DEFAULT_TRUCKS[2]),
        os.getenv("DHL_TRUCK_AGENT_ADDRESS", _DEFAULT_TRUCKS[3]),
        os.getenv("RIVIAN_TRUCK_AGENT_ADDRESS", _DEFAULT_TRUCKS[4]),
    )


@dataclass(frozen=True)
class AgentAddresses:
    grid_agent: str
    terminal_agent: str
    truck_status_agent: str
    truck_agents: tuple[str, ...]


@dataclass(frozen=True)
class OrchestratorSettings:
    hello_text: str
    outbound_timeout_seconds: int
    addresses: AgentAddresses


# Same default as OrchestratorSettings / `terminal` agent with seed `terminal_seed` in run_all.
_DEFAULT_TERMINAL_AGENT = (
    "agent1q2dsyxc0g3482s3cewzss6vf4gakd2r8znask0gpmqrnvm0p5n0fy9gsulk"
)


def terminal_agent_address() -> str:
    """Where trucks send PowerBid; grid sends AuctionComplete. Prefer TERMINAL_AGENT_ADDRESS in .env."""
    return os.getenv("TERMINAL_AGENT_ADDRESS", "").strip() or _DEFAULT_TERMINAL_AGENT


def load_orchestrator_settings() -> OrchestratorSettings:
    _t_default = _DEFAULT_TERMINAL_AGENT
    return OrchestratorSettings(
        hello_text=os.getenv("ORCHESTRATOR_HELLO_TEXT", "Hello from Port-Power Nexus"),
        outbound_timeout_seconds=int(
            os.getenv("ORCHESTRATOR_OUTBOUND_TIMEOUT_SECONDS", "15")
        ),
        addresses=AgentAddresses(
            grid_agent=os.getenv("GRID_AGENT_ADDRESS", _DEFAULT_GRID_AGENT),
            terminal_agent=os.getenv("TERMINAL_AGENT_ADDRESS", _t_default),
            truck_status_agent=os.getenv(
                "TRUCK_STATUS_AGENT_ADDRESS",
                os.getenv("TERMINAL_AGENT_ADDRESS", _t_default),
            ),
            truck_agents=truck_agent_addresses_tuple(),
        ),
    )
