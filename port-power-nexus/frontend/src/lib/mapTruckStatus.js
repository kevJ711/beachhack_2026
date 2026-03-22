/**
 * Map / bay visuals: charging only when truck row + bay assignment agree.
 *
 * Realtime: `bays` and `trucks` refetch independently. After charge, `release_bay_for_truck`
 * can appear before the truck row flips to `at_port` — if we mapped that to `idle`, the dot
 * snaps to the home pier (left) for one frame. Treat released bay + truck still `charging` as
 * exit staging (`at_port`) instead.
 */

export function effectiveMapStatus(truck, baysRows) {
  const raw = (truck.status ?? 'idle').toLowerCase()
  if (raw === 'charging') {
    if (!truck.bay_id) return 'idle'
    const bay = (baysRows ?? []).find((b) => b.id === truck.bay_id)
    if (!bay) return 'idle'
    if ((bay.status ?? '').toLowerCase() === 'available') {
      return 'at_port'
    }
    if (bay.assigned_truck_id && bay.assigned_truck_id !== truck.id) return 'idle'
    return 'charging'
  }
  return raw
}

export function bayIsActivelyCharging(bay, trucks) {
  if ((bay.status ?? '').toLowerCase() === 'available') return false
  const tid = bay.assigned_truck_id
  if (!tid) return false
  const t = (trucks ?? []).find((x) => x.id === tid)
  if (!t) return false
  const st = (t.status ?? '').toLowerCase()
  if (st !== 'charging') return false
  return t.bay_id === bay.id
}
