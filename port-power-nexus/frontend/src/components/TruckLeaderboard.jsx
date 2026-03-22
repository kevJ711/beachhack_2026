import useRealtimeTable from '../hooks/useRealtimeTable'
import { formatSocPercent, normalizeSoc } from '../lib/truckDisplay'

function TruckCard({ truck }) {
  const status = (truck.status ?? 'idle').toLowerCase()

  let borderColor = '#1a3a5c'
  if (status === 'bidding') borderColor = '#00aaff44'
  else if (status === 'charging') borderColor = '#ffaa0044'

  let badgeBg = '#00ff8822'
  let badgeColor = '#00ff88'
  let label = 'IDLE'
  if (status === 'bidding') { badgeBg = '#00aaff22'; badgeColor = '#00aaff'; label = 'BIDDING' }
  else if (status === 'charging') { badgeBg = '#ffaa0022'; badgeColor = '#ffaa00'; label = 'CHARGING' }
  else if (status === 'done') { badgeBg = '#3a5a6a22'; badgeColor = '#3a5a6a'; label = 'DONE' }

  const soc = normalizeSoc(truck.state_of_charge)
  let barColor = '#00ff88'
  if (soc < 30) barColor = '#cc3333'
  else if (soc <= 60) barColor = '#cc8800'

  return (
    <div style={{ background: '#0a0e1a', border: `1px solid ${borderColor}`, borderRadius: 4, padding: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ color: '#c8d4e8', fontSize: 10, letterSpacing: 1, fontFamily: 'Courier New, monospace' }}>
          {truck.name}
        </span>
        <span style={{ fontSize: 8, padding: '1px 5px', borderRadius: 2, letterSpacing: 1, fontFamily: 'Courier New, monospace', background: badgeBg, color: badgeColor }}>
          {label}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ flex: 1, height: 4, background: '#1a2a3a', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{ width: `${soc}%`, height: 4, background: barColor, borderRadius: 2 }} />
        </div>
        <span style={{ fontSize: 9, color: '#6a8aaa', fontFamily: 'Courier New, monospace' }}>
          {formatSocPercent(truck.state_of_charge)}
        </span>
      </div>
    </div>
  )
}

export default function TruckLeaderboard({ demoTruck }) {
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
          />
        ))}
      </div>
    </aside>
  )
}
