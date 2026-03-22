-- Optional: run in Supabase SQL Editor if tables already exist.
-- Smooth 20s charge uses time-based SOC; bids link to auction.

alter table public.power_bids add column if not exists auction_id text;

alter table public.trucks add column if not exists charging_started_at timestamptz;
alter table public.trucks add column if not exists charge_start_soc integer;
