-- Port-Power Nexus — tables required by the React dashboard + Python agents.
-- Run in Supabase SQL Editor, then: Database → Replication → enable Realtime for each table.

-- ---------------------------------------------------------------------------
-- trucks first (no FK to bays yet — avoids circular dependency with bays)
-- `name` must match agent truck_id: amazon_truck, fedex_truck, ups_truck
-- ---------------------------------------------------------------------------
create table if not exists public.trucks (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  state_of_charge integer not null default 0 check (state_of_charge between 0 and 100),
  distance_to_port integer default 0,
  status text not null default 'idle',
  bay_id uuid,
  balance numeric not null default 0,
  last_updated timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- bays
-- ---------------------------------------------------------------------------
create table if not exists public.bays (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  status text not null default 'available',
  assigned_truck_id uuid references public.trucks (id) on delete set null,
  locked_at timestamptz
);

-- Link trucks.bay_id → bays after both tables exist
do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'trucks_bay_id_fkey'
  ) then
    alter table public.trucks
      add constraint trucks_bay_id_fkey
      foreign key (bay_id) references public.bays (id) on delete set null;
  end if;
end $$;

-- ---------------------------------------------------------------------------
-- auction_state (Grid Agent upserts; TopBar reads latest by started_at)
-- ---------------------------------------------------------------------------
create table if not exists public.auction_state (
  id text primary key,
  status text not null default 'active',
  current_price numeric not null,
  start_price numeric,
  min_price numeric,
  renewable_pct numeric default 0,
  grid_stress numeric default 0,
  started_at timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- power_bids
-- ---------------------------------------------------------------------------
create table if not exists public.power_bids (
  id uuid primary key default gen_random_uuid(),
  truck_id uuid references public.trucks (id) on delete cascade,
  battery_level integer not null,
  requested_kwh numeric not null,
  bid_price numeric not null,
  reasoning text,
  created_at timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- bid_responses
-- ---------------------------------------------------------------------------
create table if not exists public.bid_responses (
  id uuid primary key default gen_random_uuid(),
  bid_id uuid not null references public.power_bids (id) on delete cascade,
  accepted boolean not null,
  bay_id uuid references public.bays (id) on delete set null,
  price_confirmed numeric,
  queue_position integer,
  created_at timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- events (Grid Agent log_event; Activity feed)
-- UI colors: auction_start, win, payment, bid
-- ---------------------------------------------------------------------------
create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  type text not null,
  message text not null,
  created_at timestamptz default now()
);

-- ---------------------------------------------------------------------------
-- RLS — dashboard uses anon key for SELECT
-- ---------------------------------------------------------------------------
alter table public.auction_state enable row level security;
alter table public.trucks enable row level security;
alter table public.bays enable row level security;
alter table public.power_bids enable row level security;
alter table public.bid_responses enable row level security;
alter table public.events enable row level security;

drop policy if exists "anon_select_auction_state" on public.auction_state;
drop policy if exists "anon_select_trucks" on public.trucks;
drop policy if exists "anon_select_bays" on public.bays;
drop policy if exists "anon_select_power_bids" on public.power_bids;
drop policy if exists "anon_select_bid_responses" on public.bid_responses;
drop policy if exists "anon_select_events" on public.events;

create policy "anon_select_auction_state" on public.auction_state for select to anon using (true);
create policy "anon_select_trucks" on public.trucks for select to anon using (true);
create policy "anon_select_bays" on public.bays for select to anon using (true);
create policy "anon_select_power_bids" on public.power_bids for select to anon using (true);
create policy "anon_select_bid_responses" on public.bid_responses for select to anon using (true);
create policy "anon_select_events" on public.events for select to anon using (true);

-- Agents may auto-create truck rows if seed was not applied (see agents/terminal/bay_manager.py)
drop policy if exists "anon_insert_trucks" on public.trucks;
create policy "anon_insert_trucks" on public.trucks for insert to anon with check (true);

-- Terminal agent seeds bays and runs lock_bay (update) — required when using anon key
drop policy if exists "anon_insert_bays" on public.bays;
drop policy if exists "anon_update_bays" on public.bays;
create policy "anon_insert_bays" on public.bays for insert to anon with check (true);
create policy "anon_update_bays" on public.bays for update to anon using (true) with check (true);

-- ---------------------------------------------------------------------------
-- Seed bays (map expects A1, A2, B1, B2)
-- ---------------------------------------------------------------------------
insert into public.bays (name, status) values
  ('A1', 'available'),
  ('A2', 'available'),
  ('B1', 'available'),
  ('B2', 'available')
on conflict (name) do nothing;

-- Seed trucks (names must match agents/trucks/agent.py)
insert into public.trucks (name, state_of_charge, distance_to_port, status) values
  ('amazon_truck', 20, 10, 'idle'),
  ('fedex_truck', 55, 10, 'idle'),
  ('ups_truck', 80, 10, 'idle')
on conflict (name) do nothing;
