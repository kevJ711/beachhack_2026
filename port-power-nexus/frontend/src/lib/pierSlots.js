/** Pier T + Pier E berth boxes (matches TerminalMap SVG layout). */
export const PIER_BOXES = [
  { id: 'Y1', x: 30, y: 42, w: 40, h: 30 },
  { id: 'Y2', x: 80, y: 42, w: 40, h: 30 },
  { id: 'Y3', x: 130, y: 42, w: 40, h: 30 },
  { id: 'Y4', x: 30, y: 84, w: 40, h: 30 },
  { id: 'Y5', x: 80, y: 84, w: 40, h: 30 },
  { id: 'Y6', x: 130, y: 84, w: 40, h: 30 },
  { id: 'Y7', x: 270, y: 42, w: 40, h: 30 },
  { id: 'Y8', x: 320, y: 42, w: 40, h: 30 },
  { id: 'Y9', x: 370, y: 42, w: 40, h: 30 },
  { id: 'Y10', x: 270, y: 84, w: 40, h: 30 },
  { id: 'Y11', x: 320, y: 84, w: 40, h: 30 },
]

/** Home berth per live swarm truck (agents/trucks/agent.py names). */
export const TRUCK_HOME_PIER = {
  amazon_truck: 'Y1',
  fedex_truck: 'Y2',
  ups_truck: 'Y3',
  TRUCK_01: 'Y1',
  TRUCK_07: 'Y2',
  TRUCK_12: 'Y3',
  TRUCK_15: 'Y8',
  TRUCK_03: 'Y4',
}

export function getPierBox(pierId) {
  return PIER_BOXES.find((p) => p.id === pierId) ?? PIER_BOXES[0]
}

export function getPierCenterById(pierId) {
  const b = getPierBox(pierId)
  return { x: b.x + b.w / 2, y: b.y + b.h / 2 }
}

export function getIdleCenterForTruck(truckName) {
  const pid = TRUCK_HOME_PIER[truckName] ?? 'Y1'
  return { ...getPierCenterById(pid), pierId: pid }
}

/** Off-screen X: exit right (full charge), spawn left (respawn) — Y matches pier row in resolve */
export const EXIT_RIGHT_X = 540
export const SPAWN_LEFT_X = -38
