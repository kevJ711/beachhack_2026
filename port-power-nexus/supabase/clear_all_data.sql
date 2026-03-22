-- Clear all application data from Port-Power Nexus tables.
-- Run in Supabase → SQL Editor (uses postgres role; bypasses RLS).
--
-- FK order is handled by truncating all listed tables in one statement.

truncate table
  public.bid_responses,
  public.power_bids,
  public.events,
  public.auction_state,
  public.trucks,
  public.bays
restart identity cascade;

-- Optional: re-seed minimal bays + trucks (matches schema_for_frontend_and_agents.sql).
-- Uncomment if you want empty names reset instead of fully empty tables.

/*
insert into public.bays (name, status) values
  ('A1', 'available'),
  ('A2', 'available'),
  ('B1', 'available'),
  ('B2', 'available')
on conflict (name) do update set
  status = 'available',
  assigned_truck_id = null,
  locked_at = null;

insert into public.trucks (name, state_of_charge, distance_to_port, status) values
  ('amazon_truck', 20, 10, 'idle'),
  ('fedex_truck', 55, 10, 'idle'),
  ('ups_truck', 80, 10, 'idle'),
  ('dhl_truck', 50, 10, 'idle'),
  ('rivian_truck', 60, 10, 'idle')
on conflict (name) do update set
  state_of_charge = excluded.state_of_charge,
  distance_to_port = excluded.distance_to_port,
  status = excluded.status,
  bay_id = null;
*/
