/**
 * Map / bay visuals: charging only when truck row + bay assignment agree.
 */

export function effectiveMapStatus(truck, baysRows) {
  const raw = (truck.status ?? 'idle').toLowerCase()
  if (raw === 'charging') {
    if (!truck.bay_id) return 'idle'
    const bay = (baysRows ?? []).find((b) => b.id === truck.bay_id)
    if (!bay) return 'idle'
    if ((bay.status ?? '').toLowerCase() === 'available') return 'idle'
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
