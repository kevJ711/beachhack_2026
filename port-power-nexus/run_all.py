"""Run all agents in one Bureau for local development.

Agents in the same Bureau communicate directly without needing
the Fetch.ai Almanac or funded wallets.

Env: BUREAU_PORT (default 8000), UAGENTS_HOST (default localhost).
"""
import os
from dotenv import load_dotenv
load_dotenv()

from uagents import Bureau
from agents.grid.agent import grid_agent
from agents.trucks.agent import truck1, truck2, truck3, truck4, truck5
from agents.terminal.agent import terminal
from shared.agent_net import bureau_port_run_all, uagents_host
from shared.agent_wiring import swarm_wiring_log_line

_port = bureau_port_run_all()
_host = uagents_host()
bureau = Bureau(port=_port, endpoint=f"http://{_host}:{_port}/submit")
bureau.add(grid_agent)
bureau.add(truck1)
bureau.add(truck2)
bureau.add(truck3)
bureau.add(truck4)
bureau.add(truck5)
bureau.add(terminal)
print(f"[run_all] Bureau endpoint: http://{_host}:{_port}/submit")
print(f"[run_all] {swarm_wiring_log_line()}")
bureau.run()
