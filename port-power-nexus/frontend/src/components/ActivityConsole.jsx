import { useEffect, useMemo, useRef } from 'react'
import useRealtimeTable from '../hooks/useRealtimeTable'

const styles = `
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
`

function lineColor(kind, accepted) {
  if (kind === 'bid') return '#00aaff'
  if (kind === 'response') {
    return accepted ? '#00ff88' : '#ffaa00'
  }
  return '#c8d4e8'
}

export default function ActivityConsole() {
  const { rows: powerBids } = useRealtimeTable('power_bids', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 60,
  })

  const { rows: bidResponses } = useRealtimeTable('bid_responses', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 60,
  })

  const rows = useMemo(() => {
    const bidRows = (powerBids ?? []).map((b) => ({
      key: `bid-${b.id}`,
      created_at: b.created_at,
      kind: 'bid',
      payload: b,
    }))
    const resRows = (bidResponses ?? []).map((r) => ({
      key: `res-${r.id}`,
      created_at: r.created_at,
      kind: 'response',
      payload: r,
    }))
    return [...bidRows, ...resRows].sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    ).slice(0, 40)
  }, [powerBids, bidResponses])

  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      el.scrollTop = el.scrollHeight
    }
  }, [rows])

  const reversed = [...rows].reverse()

  return (
    <section
      style={{
        flexShrink: 0,
        height: 90,
        background: '#050810',
        borderTop: '1px solid #1a3a5c',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <style>{styles}</style>
      <div
        style={{
          color: '#3a6a8a',
          fontSize: 9,
          letterSpacing: 1,
          padding: '4px 12px',
          borderBottom: '1px solid #0d1225',
          flexShrink: 0,
          fontFamily: 'Courier New, monospace',
        }}
      >
        ACTIVITY FEED
      </div>
      <div
        ref={scrollRef}
        style={{
          height: 66,
          overflowY: 'auto',
          padding: '0 12px 4px',
        }}
      >
        {reversed.map((row) => {
          const t = new Date(row.created_at).toLocaleTimeString('en-US', {
            hour12: false,
          })
          if (row.kind === 'bid') {
            const b = row.payload
            const price =
              b.bid_price != null ? Number(b.bid_price).toFixed(2) : '—'
            const reason = b.reasoning
              ? String(b.reasoning).slice(0, 80)
              : ''
            return (
              <div
                key={row.key}
                style={{
                  fontSize: 10,
                  lineHeight: 1.8,
                  fontFamily: 'Courier New, monospace',
                  color: lineColor('bid'),
                  animation: 'fadeIn 0.4s ease-in',
                }}
              >
                [{t}] BID: ${price} · {reason}
              </div>
            )
          }
          const r = row.payload
          const accepted = r.accepted === true
          const label = accepted ? 'ACCEPT' : 'REJECT'
          const price =
            r.price_confirmed != null
              ? Number(r.price_confirmed).toFixed(2)
              : '—'
          return (
            <div
              key={row.key}
              style={{
                fontSize: 10,
                lineHeight: 1.8,
                fontFamily: 'Courier New, monospace',
                color: lineColor('response', accepted),
                animation: 'fadeIn 0.4s ease-in',
              }}
            >
              [{t}] {label}: ${price} · queue {r.queue_position ?? '—'}
            </div>
          )
        })}
      </div>
    </section>
  )
}
