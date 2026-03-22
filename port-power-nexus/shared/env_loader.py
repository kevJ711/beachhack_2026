"""Load `.env` before any `os.environ` reads.

Tries workspace root first (`beachhack_2026/.env`), then `port-power-nexus/.env`,
so Python agents and scripts match Vite (which resolves the parent folder).
"""
from pathlib import Path

from dotenv import load_dotenv

_here = Path(__file__).resolve()
# shared/ → port-power-nexus/ → beachhack_2026/
for _env in (_here.parents[2] / ".env", _here.parents[1] / ".env"):
    if _env.is_file():
        load_dotenv(_env)
