#!/usr/bin/env python3
"""
Delete all rows from Port-Power Nexus Supabase tables.

The anon key cannot bulk-delete under the default RLS policies. Use either:
  - Supabase Dashboard → SQL Editor → run ../supabase/clear_all_data.sql, or
  - This script with a service-role key (SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY).

Usage (from repo root, with PYTHONPATH including port-power-nexus):
  python scripts/clear_all_data.py
  python scripts/clear_all_data.py --dry-run
"""
from __future__ import annotations

import argparse
import os
import sys

# Repo-root .env
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import shared.env_loader  # noqa: F401

from supabase import Client, create_client


def _service_key() -> str | None:
    k = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.getenv("SUPABASE_KEY", "").strip()
    )
    if k and (k.startswith("sb_secret_") or k.startswith("eyJ")):
        return k
    return None


def clear_via_rest(supabase: Client) -> None:
    """Delete all rows table-by-table (FK-safe order)."""
    # Child tables first
    supabase.table("bid_responses").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    supabase.table("power_bids").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    supabase.table("events").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    supabase.table("auction_state").delete().neq("id", "").execute()

    # Break trucks ↔ bays circular FKs
    supabase.table("bays").update({"assigned_truck_id": None}).neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    supabase.table("trucks").update({"bay_id": None}).neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()

    supabase.table("trucks").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    supabase.table("bays").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()


def main() -> int:
    p = argparse.ArgumentParser(description="Clear all Port-Power Nexus table data.")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would run and exit (no deletes).",
    )
    args = p.parse_args()

    url = os.getenv("SUPABASE_URL", "").strip()
    key = _service_key()
    if not url:
        print("SUPABASE_URL is not set.", file=sys.stderr)
        return 1
    if not key:
        print(
            "Set SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY with service role / sb_secret) "
            "for bulk deletes, or run supabase/clear_all_data.sql in the SQL Editor.",
            file=sys.stderr,
        )
        return 1

    if args.dry_run:
        print(f"Would clear tables via {url} (service key present).")
        return 0

    supabase = create_client(url, key)
    clear_via_rest(supabase)
    print("Cleared: bid_responses, power_bids, events, auction_state, trucks, bays.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
