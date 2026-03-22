"""Run all agents in one Bureau for local development.

Agents in the same Bureau communicate directly without needing
the Fetch.ai Almanac or funded wallets.
"""
import os
from dotenv import load_dotenv
load_dotenv()

from uagents import Bureau
from agents.grid.agent import grid_agent
from agents.trucks.agent import truck1, truck2, truck3
from agents.terminal.agent import terminal

bureau = Bureau(port=8000, endpoint="http://localhost:8000/submit")
bureau.add(grid_agent)
bureau.add(truck1)
bureau.add(truck2)
bureau.add(truck3)
bureau.add(terminal)
bureau.run()
