"""Load repo-root `.env` (beachhack_2026/.env) before any `os.environ` reads."""
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_REPO_ROOT / ".env")
