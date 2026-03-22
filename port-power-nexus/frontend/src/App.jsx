/**
 * Data flow: Supabase Realtime → hooks → UI. Debug UI: set VITE_DEMO_STATIC_TRUCK=true
 * to overlay a local TRUCK_01 loop (same row shape as `trucks` / `bays` tables).
 *
 * Schema: auction_state, trucks, bays, power_bids, bid_responses, events (Grid Agent).
 * For live agents + Supabase: set VITE_DEMO_STATIC_TRUCK=false in repo-root `.env`.
 */
import { useMemo } from 'react'
import TopBar from './components/TopBar'
import TerminalMap from './components/TerminalMap'
import TruckLeaderboard from './components/TruckLeaderboard'
import ActivityConsole from './components/ActivityConsole'
import useRealtimeTable from './hooks/useRealtimeTable'
import useDemoStaticTruck, {
  DEMO_TRUCK_ID,
  DEMO_BAY_IDS,
} from './hooks/useDemoStaticTruck'

const DEMO_BID_ID = '00000000-0000-4000-8000-00000000b001'
const DEMO_RESPONSE_ID = '00000000-0000-4000-8000-00000000r001'

export default function App() {
  const { rows: powerBids } = useRealtimeTable('power_bids', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 100,
  })

  const { rows: bidResponses } = useRealtimeTable('bid_responses', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 100,
  })

  const demo = useDemoStaticTruck()

  const powerBidsForUi = useMemo(() => {
    if (!demo.enabled) return powerBids
    return [
      {
        id: DEMO_BID_ID,
        truck_id: DEMO_TRUCK_ID,
        battery_level: 38,
        requested_kwh: 150,
        bid_price: 0.38,
        reasoning: demo.reasoning,
        created_at: new Date().toISOString(),
      },
      ...powerBids,
    ]
  }, [powerBids, demo.enabled, demo.reasoning])

  const bidResponsesForUi = useMemo(() => {
    if (!demo.enabled || demo.phase !== 2) return bidResponses
    return [
      {
        id: DEMO_RESPONSE_ID,
        bid_id: DEMO_BID_ID,
        accepted: true,
        bay_id: DEMO_BAY_IDS.A1,
        price_confirmed: 0.38,
        queue_position: 1,
        created_at: new Date().toISOString(),
      },
      ...bidResponses,
    ]
  }, [bidResponses, demo.enabled, demo.phase])

  const demoMap =
    demo.enabled && demo.truck && demo.bays
      ? { truck: demo.truck, bays: demo.bays }
      : null

  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        background: '#0a0e1a',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <TopBar />
      <main
        style={{
          flex: 1,
          display: 'flex',
          overflow: 'hidden',
          position: 'relative',
          zIndex: 1,
        }}
      >
        <TerminalMap
          powerBids={powerBidsForUi}
          demo={demoMap}
          style={{ flex: 1, overflow: 'hidden' }}
        />
        <TruckLeaderboard
          powerBids={powerBidsForUi}
          bidResponses={bidResponsesForUi}
          demoTruck={demo.truck}
        />
      </main>
      <ActivityConsole />
    </div>
  )
}
