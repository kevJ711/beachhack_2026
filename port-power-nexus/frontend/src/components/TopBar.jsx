import { useMemo } from 'react'
import useRealtimeTable, { REFETCH_ON_EVENTS_INSERT } from '../hooks/useRealtimeTable'

const styles = `
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  @keyframes pricepulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
`

/** Stable options — avoids resubscribing every render. */
const AUCTION_STATE_OPTIONS = {
  orderBy: 'started_at',
  orderAscending: false,
  limit: 1,
  // Any `events` INSERT (incl. auction_end) — filtered INSERT Realtime is unreliable.
  refetchOnChanges: REFETCH_ON_EVENTS_INSERT,
}

/** How much the HUD bar follows live charging-bay utilization vs grid agent (CAISO blend). Match grid ~0.75. */
const BAY_STRESS_HUD_WEIGHT = 0.75

const BAYS_OPTIONS = {
  refetchOnChanges: REFETCH_ON_EVENTS_INSERT,
}

/** Locked (non-available) bays / total bays — same definition as grid agent. */
function bayUtilizationStress(baysRows) {
  const bays = baysRows ?? []
  const totalB = Math.max(bays.length, 1)
  const locked = bays.filter(
    (b) => String(b.status ?? '').toLowerCase() !== 'available'
  ).length
  return locked / totalB
}

export default function TopBar() {
  // Latest row from Grid Agent upserts (status active | complete). Do not filter
  // status=active only — completed auctions would disappear from the HUD.
  const { rows, lastUpdated } = useRealtimeTable('auction_state', AUCTION_STATE_OPTIONS)
  const { rows: baysRows } = useRealtimeTable('bays', BAYS_OPTIONS)

  const row = rows[0] ?? {}
  const price =
    row.current_price != null && row.current_price !== ''
      ? `$${Number(row.current_price).toFixed(2)}`
      : null

  const auctionActive = String(row.status ?? '').toLowerCase() === 'active'

  const bayStress = useMemo(() => bayUtilizationStress(baysRows), [baysRows])
  const agentStress = Number(row.grid_stress ?? 0)
  const gridStress = useMemo(() => {
    const w = BAY_STRESS_HUD_WEIGHT
    return Math.min(1, (1 - w) * agentStress + w * bayStress)
  }, [agentStress, bayStress])
  const renewablePct = Math.round(row.renewable_pct ?? 0)

  let stressColor = '#00ff88'
  if (gridStress >= 0.8) stressColor = '#cc3333'
  else if (gridStress >= 0.5) stressColor = '#ffaa00'

  const stale =
    lastUpdated != null && Date.now() - lastUpdated > 15000 && auctionActive

  return (
    <>
      <style>{styles}</style>
      {gridStress > 0.7 && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            background: 'rgba(255,170,0,0.03)',
            pointerEvents: 'none',
            zIndex: 0,
          }}
        />
      )}
      <header
        style={{
          position: 'relative',
          zIndex: 1,
          display: 'flex',
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#0d1225',
          borderBottom: '1px solid #1a3a5c',
          padding: '8px 16px',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'row', gap: 10, alignItems: 'center' }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#00ff88',
              animation: 'blink 1.5s infinite',
              flexShrink: 0,
            }}
          />
          <div>
            <div
              style={{
                color: '#00aaff',
                fontSize: 13,
                fontWeight: 700,
                letterSpacing: 2,
                fontFamily: 'Courier New, monospace',
              }}
            >
              PORT-POWER NEXUS
            </div>
            <div
              style={{
                color: '#3a6a8a',
                fontSize: 10,
                letterSpacing: 1,
                fontFamily: 'Courier New, monospace',
              }}
            >
              SWARM ACTIVE · LONG BEACH CA · PIER T + PIER E
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'row', gap: 20, alignItems: 'center' }}>
          <div>
            <div
              style={{
                fontSize: 9,
                color: '#3a6a8a',
                letterSpacing: 1,
                fontFamily: 'Courier New, monospace',
              }}
            >
              AUCTION PRICE
            </div>
            <div
              style={{
                fontSize: 10,
                color: auctionActive ? '#00aa66' : '#6a8aaa',
                letterSpacing: 1,
                fontFamily: 'Courier New, monospace',
                marginBottom: 2,
              }}
            >
              {auctionActive ? '● LIVE' : '○ ENDED'}
            </div>
            <div
              style={{
                fontSize: 22,
                color: price ? (auctionActive ? '#00ff88' : '#6a8aaa') : '#3a6a8a',
                letterSpacing: 2,
                fontFamily: 'Courier New, monospace',
                animation: price && auctionActive ? 'pricepulse 2s infinite' : 'none',
              }}
            >
              {price ?? '--'}
            </div>
          </div>

          <div>
            <div
              style={{
                fontSize: 9,
                color: '#3a6a8a',
                fontFamily: 'Courier New, monospace',
              }}
            >
              GRID STRESS
            </div>
            <div
              style={{
                width: 80,
                height: 6,
                background: '#1a2a3a',
                borderRadius: 3,
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  height: 6,
                  borderRadius: 3,
                  width: `${gridStress * 100}%`,
                  background: stressColor,
                }}
              />
            </div>
            {gridStress > 0.7 && (
              <div
                style={{
                  fontSize: 9,
                  color: '#ffaa00',
                  animation: 'blink 1s infinite',
                  fontFamily: 'Courier New, monospace',
                }}
              >
                GRID STRESS: HIGH
              </div>
            )}
          </div>

          <div>
            <div
              style={{
                fontSize: 9,
                color: '#3a6a8a',
                fontFamily: 'Courier New, monospace',
              }}
            >
              RENEWABLES
            </div>
            <div
              style={{
                fontSize: 13,
                color: '#00ff88',
                letterSpacing: 1,
                fontFamily: 'Courier New, monospace',
              }}
            >
              {renewablePct}%
            </div>
          </div>

          {stale && (
            <div
              style={{
                fontSize: 9,
                color: '#cc3333',
                animation: 'blink 1s infinite',
                fontFamily: 'Courier New, monospace',
              }}
            >
              SIGNAL LOST
            </div>
          )}
        </div>
      </header>
    </>
  )
}
