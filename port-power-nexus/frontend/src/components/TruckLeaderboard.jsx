import { useEffect, useRef } from 'react'
import useRealtimeTable from '../hooks/useRealtimeTable'
import { formatSocPercent, normalizeSoc } from '../lib/truckDisplay'

function truckHasAcceptedBid(truckId, powerBids, bidResponses) {
  const acceptedIds = new Set(
    (bidResponses ?? [])
      .filter((r) => r.accepted === true)
      .map((r) => r.bid_id)
  )
  return (powerBids ?? []).some(
    (b) => b.truck_id === truckId && acceptedIds.has(b.id)
  )
}

function TruckCard({ truck, powerBids, bidResponses }) {
  const containerRef = useRef(null)
  const prevRef = useRef(null)

  const sortedBids = [...(powerBids ?? [])].sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )

  useEffect(() => {
    const serialized = JSON.stringify({
      id: truck.id,
      state_of_charge: truck.state_of_charge,
      status: truck.status,
      bay_id: truck.bay_id,
    })
    if (prevRef.current !== null && prevRef.current !== serialized) {
      const el = containerRef.current
      if (el) {
        el.style.backgroundColor = '#00aaff11'
        const t = window.setTimeout(() => {
          el.style.backgroundColor = '#0a0e1a'
        }, 300)
        return () => window.clearTimeout(t)
      }
    }
    prevRef.current = serialized
  }, [truck])

  const latestBid = sortedBids.find((b) => b.truck_id === truck.id)
  const reasoning = latestBid?.reasoning
    ? String(latestBid.reasoning).trim()
    : null

  const hasWon = truckHasAcceptedBid(truck.id, powerBids, bidResponses)

  const status = (truck.status ?? 'idle').toLowerCase()
  let borderColor = '#1a3a5c'
  let boxShadow = 'none'
  if (status === 'bidding') {
    borderColor = '#00aaff44'
    boxShadow = '0 0 6px #00aaff22'
  } else if (status === 'charging') {
    borderColor = '#ffaa0044'
    boxShadow = '0 0 6px #ffaa0022'
  }

  let badgeBg = '#00ff8822'
  let badgeColor = '#00ff88'
  let label = 'IDLE'
  if (status === 'bidding') {
    badgeBg = '#00aaff22'
    badgeColor = '#00aaff'
    label = 'BIDDING'
  } else if (status === 'charging') {
    badgeBg = '#ffaa0022'
    badgeColor = '#ffaa00'
    label = 'CHARGING'
  } else if (status === 'done') {
    badgeBg = '#3a5a6a22'
    badgeColor = '#3a5a6a'
    label = 'DONE'
  }

  const soc = normalizeSoc(truck.state_of_charge)
  let barColor = '#00ff88'
  if (soc < 30) barColor = '#cc3333'
  else if (soc <= 60) barColor = '#cc8800'

  return (
    <div
      ref={containerRef}
      style={{
        background: '#0a0e1a',
        border: `1px solid ${borderColor}`,
        borderRadius: 4,
        padding: 8,
        boxShadow,
        transition: 'background-color 0.3s ease',
        minWidth: 0,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 6,
          minWidth: 0,
        }}
      >
        <span
          title={truck.name}
          style={{
            color: '#c8d4e8',
            fontSize: 10,
            letterSpacing: 1,
            fontFamily: 'Courier New, monospace',
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {truck.name}
        </span>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: 8,
              padding: '1px 5px',
              borderRadius: 2,
              letterSpacing: 1,
              fontFamily: 'Courier New, monospace',
              background: badgeBg,
              color: badgeColor,
            }}
          >
            {label}
          </span>
          {hasWon && (
            <span
              style={{
                marginLeft: 4,
                background: '#00ff8822',
                color: '#00ff88',
                fontSize: 8,
                padding: '1px 5px',
                borderRadius: 2,
                fontFamily: 'Courier New, monospace',
              }}
            >
              WON
            </span>
          )}
        </div>
      </div>
      <div
        style={{
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          gap: 8,
          margin: '4px 0',
        }}
      >
        <div
          style={{
            flex: 1,
            minWidth: 0,
            height: 4,
            background: '#1a2a3a',
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${soc}%`,
              height: 4,
              background: barColor,
              borderRadius: 2,
            }}
          />
        </div>
        <span
          style={{
            fontSize: 9,
            color: '#6a8aaa',
            fontFamily: 'Courier New, monospace',
            flexShrink: 0,
            letterSpacing: 0.5,
          }}
        >
          {formatSocPercent(truck.state_of_charge)}
        </span>
      </div>
      <div
        style={{
          fontSize: 9,
          color: '#3a6a8a',
          lineHeight: 1.4,
          fontFamily: 'Courier New, monospace',
          wordBreak: 'break-word',
          overflowWrap: 'anywhere',
          maxWidth: '100%',
        }}
      >
        {reasoning ?? 'Awaiting auction...'}
      </div>
    </div>
  )
}

export default function TruckLeaderboard({
  powerBids,
  bidResponses,
  demoTruck,
}) {
  const { rows: trucks } = useRealtimeTable('trucks', {
    orderBy: 'state_of_charge',
    orderAscending: true,
  })

  const displayTrucks = demoTruck ? [demoTruck] : trucks

  return (
    <aside
      style={{
        width: 220,
        flexShrink: 0,
        background: '#0d1225',
        borderLeft: '1px solid #1a3a5c',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          color: '#00aaff',
          fontSize: 9,
          letterSpacing: 2,
          padding: '10px 12px',
          borderBottom: '1px solid #1a3a5c',
          flexShrink: 0,
          fontFamily: 'Courier New, monospace',
        }}
      >
        SWARM STATUS
      </div>
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 8,
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
        }}
      >
        {displayTrucks.map((t) => (
          <TruckCard
            key={t.id}
            truck={t}
            powerBids={powerBids}
            bidResponses={bidResponses}
          />
        ))}
      </div>
    </aside>
  )
}
