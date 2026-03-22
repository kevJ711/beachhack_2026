import { useEffect, useRef } from 'react'
import useRealtimeTable from '../hooks/useRealtimeTable'

const styles = `
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`

const TRUCK_COLORS = {
  amazon_truck: '#ff9900',
  fedex_truck:  '#4d148c',
  ups_truck:    '#ffb500',
  dhl_truck:    '#ffcc00',
  rivian_truck: '#00c97a',
}

function truckColor(message) {
  for (const [name, color] of Object.entries(TRUCK_COLORS)) {
    if (message?.toLowerCase().includes(name.replace('_truck', ''))) return color
  }
  return null
}

function lineColor(type, message) {
  const tc = truckColor(message)
  if (type === 'win') return '#00ff88'
  if (type === 'bid' && tc) return tc
  if (type === 'bid') return '#00aaff'
  if (type === 'signal') return '#aa88ff'
  if (type === 'auction_start') return '#66ccff'
  if (type === 'auction_end') return '#8899aa'
  if (type === 'charge_complete') return '#ffcc66'
  return '#4a6a8a'
}

function formatMessage(type, message) {
  if (!message) return ''
  // Extract just the reasoning after the · separator for bid events
  if (type === 'bid') {
    const parts = message.split('·')
    if (parts.length >= 3) {
      const truck = parts[0].replace('BID', '').trim()
      const price = parts[1].trim()
      const reasoning = parts.slice(2).join('·').trim()
      return { truck, price, reasoning }
    }
  }
  if (type === 'win') {
    // "terminal → amazon_truck: DIRECT bay=Y1 at $0.23/kWh"
    return { truck: null, price: null, reasoning: message }
  }
  return { truck: null, price: null, reasoning: message }
}

export default function ActivityConsole() {
  const { rows } = useRealtimeTable('events', {
    orderBy: 'created_at',
    orderAscending: false,
    limit: 50,
  })

  const scrollRef = useRef(null)
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [rows])

  const reversed = [...rows].reverse()

  return (
    <section
      style={{
        flexShrink: 0,
        height: 260,
        background: '#050810',
        borderTop: '1px solid #1a3a5c',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <style>{styles}</style>
      <div
        style={{
          color: '#3a6a8a',
          fontSize: 10,
          letterSpacing: 2,
          padding: '5px 14px',
          borderBottom: '1px solid #0d1225',
          flexShrink: 0,
          fontFamily: 'Courier New, monospace',
        }}
      >
        AGENT ACTIVITY
      </div>
      <div
        ref={scrollRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '4px 14px 6px',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        {reversed.map((event) => {
          const t = new Date(event.created_at).toLocaleTimeString('en-US', { hour12: false })
          const type = event.type ?? ''
          const fmt = formatMessage(type, event.message)
          const color = lineColor(type, event.message)

          return (
            <div
              key={event.id}
              style={{
                fontSize: 13,
                lineHeight: 1.5,
                fontFamily: 'Courier New, monospace',
                color,
                animation: 'fadeIn 0.3s ease-out',
                borderLeft: `2px solid ${color}22`,
                paddingLeft: 6,
              }}
            >
              <span style={{ color: '#3a5a7a', fontSize: 11 }}>{t} </span>
              {type === 'bid' && fmt.truck ? (
                <>
                  <span style={{ fontWeight: 'bold' }}>{fmt.truck}</span>
                  <span style={{ color: '#4a6a8a' }}> {fmt.price} — </span>
                  <span style={{ color: '#8aaabb' }}>{fmt.reasoning}</span>
                </>
              ) : (
                <span>{fmt.reasoning}</span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
