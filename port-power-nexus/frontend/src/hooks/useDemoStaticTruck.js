/**
 * DEBUG ONLY — local animation loop for the Command Center.
 * Toggle: VITE_DEMO_STATIC_TRUCK=true
 *
 * The `truck` and `bays` objects mirror Supabase row shapes (`trucks`, `bays`)
 * so production data can drop in with no UI changes. Disable this flag when
 * using your real database.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'

export const DEMO_TRUCK_ID = '00000000-0000-4000-8000-000000000001'
export const DEMO_BAY_IDS = {
  A1: '00000000-0000-4000-8000-0000000000a1',
  A2: '00000000-0000-4000-8000-0000000000a2',
  B1: '00000000-0000-4000-8000-0000000000b1',
  B2: '00000000-0000-4000-8000-0000000000b2',
}

const PHASE_MS = 5000

/** SOC during idle + bidding (flat). Rises only during charging phase. */
const DEMO_SOC_IDLE = 38
const DEMO_SOC_CHARGE_MAX = 88

const REASONING = [
  'Demo: idle · holding at pier',
  'Demo: bidding · approaching charging zone',
  'Demo: charging · locked at Bay A1',
]

export function isDemoStaticTruckEnabled() {
  return import.meta.env.VITE_DEMO_STATIC_TRUCK === 'true'
}

/**
 * Local-only loop: idle → bidding → charging (TRUCK_01 + Bay A1).
 * Enable with VITE_DEMO_STATIC_TRUCK=true in .env.local
 */
export default function useDemoStaticTruck() {
  const enabled = isDemoStaticTruckEnabled()
  const [phase, setPhase] = useState(0)
  const chargeStartRef = useRef(null)
  const prevPhaseRef = useRef(phase)
  const [chargeTick, setChargeTick] = useState(0)

  useEffect(() => {
    if (!enabled) return
    const id = window.setInterval(() => {
      setPhase((p) => (p + 1) % 3)
    }, PHASE_MS)
    return () => clearInterval(id)
  }, [enabled])

  useLayoutEffect(() => {
    if (!enabled) return
    if (phase === 2) {
      if (prevPhaseRef.current !== 2) {
        chargeStartRef.current = performance.now()
        setChargeTick((n) => n + 1)
      }
    } else {
      chargeStartRef.current = null
    }
    prevPhaseRef.current = phase
  }, [enabled, phase])

  useEffect(() => {
    if (!enabled || phase !== 2) return
    const id = window.setInterval(() => {
      setChargeTick((n) => n + 1)
    }, 100)
    return () => clearInterval(id)
  }, [enabled, phase])

  const truck = useMemo(() => {
    if (!enabled) return null
    const statuses = ['idle', 'bidding', 'charging']
    const status = statuses[phase]
    let state_of_charge = DEMO_SOC_IDLE
    if (status === 'charging' && chargeStartRef.current != null) {
      const elapsed = performance.now() - chargeStartRef.current
      const t = Math.min(1, elapsed / PHASE_MS)
      state_of_charge = Math.round(
        DEMO_SOC_IDLE + (DEMO_SOC_CHARGE_MAX - DEMO_SOC_IDLE) * t
      )
    }
    return {
      id: DEMO_TRUCK_ID,
      name: 'TRUCK_01',
      state_of_charge,
      distance_to_port: 12,
      status,
      bay_id: status === 'charging' ? DEMO_BAY_IDS.A1 : null,
      last_updated: new Date().toISOString(),
    }
  }, [enabled, phase, chargeTick])

  const bays = useMemo(() => {
    if (!enabled) return null
    const available = (name, id) => ({
      id,
      name,
      status: 'available',
      assigned_truck_id: null,
      locked_at: null,
    })
    if (phase === 2) {
      return [
        {
          id: DEMO_BAY_IDS.A1,
          name: 'A1',
          status: 'locked',
          assigned_truck_id: DEMO_TRUCK_ID,
          locked_at: new Date().toISOString(),
        },
        available('A2', DEMO_BAY_IDS.A2),
        available('B1', DEMO_BAY_IDS.B1),
        available('B2', DEMO_BAY_IDS.B2),
      ]
    }
    return [
      available('A1', DEMO_BAY_IDS.A1),
      available('A2', DEMO_BAY_IDS.A2),
      available('B1', DEMO_BAY_IDS.B1),
      available('B2', DEMO_BAY_IDS.B2),
    ]
  }, [enabled, phase])

  const reasoning = enabled ? REASONING[phase] : ''

  return { enabled, phase, truck, bays, reasoning }
}
