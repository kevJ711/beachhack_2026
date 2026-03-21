/**
 * UI helpers for battery / SOC. Matches Supabase `trucks.state_of_charge` (int 0–100).
 * Bids / outcomes: `power_bids`, `bid_responses` (see team ERD).
 */

/** @param {unknown} raw */
export function normalizeSoc(raw) {
  const n = Number(raw)
  if (Number.isNaN(n)) return 0
  return Math.min(100, Math.max(0, Math.round(n)))
}

/** @param {unknown} raw */
export function formatSocPercent(raw) {
  return `${normalizeSoc(raw)}%`
}
