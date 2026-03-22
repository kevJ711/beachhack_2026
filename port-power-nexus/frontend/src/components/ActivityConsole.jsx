import { useEffect, useRef } from 'react'
import useRealtimeTable from '../hooks/useRealtimeTable'

/**
 * Mirrors `events` rows written by the Grid Agent (auction_start, win, etc.).
 */
const styles = `
  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
`

function lineColor(type) {
  switch (type) {
    case 'bid':     return '#00aaff'
    case 'win':     return '#00ff88'
    case 'signal':  return '#aa88ff'
    case 'payment': return '#ffaa00'
    default:        return '#c8d4e8'
  }
}

export default function ActivityConsole() {
  const { rows } = useRealtimeTable('events', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 40,
  })

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
        height: 180,
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
          height: 150,
          overflowY: 'auto',
          padding: '0 12px 4px',
        }}
      >
        {reversed.map((event) => {
          const t = new Date(event.created_at).toLocaleTimeString('en-US', {
            hour12: false,
          })
          const type = (event.type ?? '').toUpperCase()
          return (
            <div
              key={event.id}
              style={{
                fontSize: 10,
                lineHeight: 1.8,
                fontFamily: 'Courier New, monospace',
                color: lineColor(event.type),
                animation: 'fadeIn 0.4s ease-in',
              }}
            >
              [{t}] {type}: {event.message}
            </div>
          )
        })}
      </div>
    </section>
  )
}
