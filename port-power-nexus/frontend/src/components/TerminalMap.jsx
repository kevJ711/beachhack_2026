import useRealtimeTable from '../hooks/useRealtimeTable'
import useSmoothPosition from '../hooks/useSmoothPosition'
import { formatSocPercent, normalizeSoc } from '../lib/truckDisplay'

const TRUCK_PATHS = {
  TRUCK_01: {
    idlePosition: { x: 60, y: 150 },
    approachPosition: { x: 175, y: 275 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 4.2,
  },
  TRUCK_07: {
    idlePosition: { x: 120, y: 230 },
    approachPosition: { x: 210, y: 268 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 5.1,
  },
  TRUCK_12: {
    idlePosition: { x: 330, y: 145 },
    approachPosition: { x: 265, y: 280 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 3.6,
  },
  TRUCK_15: {
    idlePosition: { x: 390, y: 230 },
    approachPosition: { x: 300, y: 272 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 4.8,
  },
  TRUCK_03: {
    idlePosition: { x: 75, y: 80 },
    approachPosition: { x: 190, y: 260 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 5.5,
  },
}

const BAY_POSITIONS = {
  A1: { cx: 188, cy: 342 },
  A2: { cx: 272, cy: 342 },
  B1: { cx: 188, cy: 390 },
  B2: { cx: 272, cy: 390 },
}

const FALLBACK_PATH = {
  idlePosition: { x: 50, y: 50 },
  approachPosition: { x: 50, y: 50 },
  tooltipOffset: { x: 20, y: -50 },
  driftDuration: 4,
}

function getTruckPath(name) {
  return TRUCK_PATHS[name] ?? FALLBACK_PATH
}

const BAY_RECTS = {
  A1: { x: 152, y: 322, w: 72, h: 40 },
  A2: { x: 236, y: 322, w: 72, h: 40 },
  B1: { x: 152, y: 372, w: 72, h: 36 },
  B2: { x: 236, y: 372, w: 72, h: 36 },
}

function socBarText(soc) {
  const s = normalizeSoc(soc)
  const n = Math.max(0, Math.min(5, Math.round(s / 20)))
  return '▓'.repeat(n) + '░'.repeat(5 - n)
}

function socBarFill(soc) {
  const s = normalizeSoc(soc)
  if (s < 30) return '#cc3333'
  if (s <= 60) return '#cc8800'
  return '#00cc66'
}

/** Tooltip box is ~100px wide — keep copy short so it stays inside the rect. */
const MAP_TOOLTIP_REASON_MAX = 22
const MAP_TOOLTIP_NAME_MAX = 14

function truncateTooltipText(s, maxLen) {
  const t = String(s).trim()
  if (t.length <= maxLen) return t
  return t.slice(0, Math.max(0, maxLen - 1)) + '…'
}

function latestReasoningForTruck(powerBids, truckId, maxLen = 38) {
  const list = (powerBids ?? []).filter((b) => b.truck_id === truckId)
  list.sort(
    (a, b) =>
      new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
  const empty = 'Waiting for auction...'
  if (list.length === 0) return truncateTooltipText(empty, maxLen)
  const r = list[0]?.reasoning
  if (r == null || String(r).trim() === '') return truncateTooltipText(empty, maxLen)
  return truncateTooltipText(String(r), maxLen)
}

function resolveTruckPosition(truck, baysRows) {
  const path = getTruckPath(truck.name)
  const status = (truck.status ?? 'idle').toLowerCase()

  if (status === 'charging') {
    const bay = (baysRows ?? []).find((b) => b.id === truck.bay_id)
    const bayName = bay?.name
    if (bayName && BAY_POSITIONS[bayName]) {
      const p = BAY_POSITIONS[bayName]
      return { x: p.cx, y: p.cy }
    }
    return path.idlePosition
  }
  if (status === 'bidding') {
    return path.approachPosition
  }
  return path.idlePosition
}

function nodeColors(status) {
  const s = (status ?? 'idle').toLowerCase()
  if (s === 'idle') return { fill: '#00ff88', stroke: '#00ff88' }
  if (s === 'bidding') return { fill: '#00aaff', stroke: '#00aaff' }
  if (s === 'charging') return { fill: '#ffaa00', stroke: '#ffaa00' }
  if (s === 'done') return { fill: '#3a5a6a', stroke: '#3a5a6a' }
  return { fill: '#00ff88', stroke: '#00ff88' }
}

const svgStyles = `
  @keyframes drift {
    0%, 100% { transform: translate(0, 0); }
    50% { transform: translate(6px, -4px); }
  }
  @keyframes ripple {
    0% { transform: scale(1); opacity: 0.8; }
    100% { transform: scale(2.2); opacity: 0; }
  }
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
  }
  @keyframes baylock {
    0%, 100% { opacity: 0.5; }
    50% { opacity: 1; }
  }
`

function TruckNode({ truck, baysRows, powerBids }) {
  const target = resolveTruckPosition(truck, baysRows)
  const pos = useSmoothPosition(target.x, target.y, 1400)
  const path = getTruckPath(truck.name)
  const off = path.tooltipOffset
  const status = (truck.status ?? 'idle').toLowerCase()
  const colors = nodeColors(truck.status)
  const drift = `${path.driftDuration ?? 4}s`
  const reasoning = latestReasoningForTruck(
    powerBids,
    truck.id,
    MAP_TOOLTIP_REASON_MAX
  )
  const nameLabel = truncateTooltipText(String(truck.name ?? ''), MAP_TOOLTIP_NAME_MAX)
  const tx = pos.x + off.x
  const ty = pos.y + off.y
  const tw = 100
  const th = 46

  return (
    <g>
      {status === 'bidding' && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="14"
          fill="none"
          stroke="#00aaff"
          strokeWidth="0.5"
          opacity="0.3"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: 'ripple 2s infinite',
          }}
        />
      )}

      {status === 'idle' && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="6"
          fill="#00ff88"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: `drift ${drift} ease-in-out infinite`,
          }}
        />
      )}

      {status === 'bidding' && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="6"
          fill="#00aaff"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: `drift ${drift} ease-in-out infinite`,
          }}
        />
      )}

      {status === 'charging' && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="6"
          fill="#ffaa00"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: 'blink 1.2s infinite',
          }}
        />
      )}

      {status === 'done' && (
        <circle cx={pos.x} cy={pos.y} r="6" fill="#3a5a6a" />
      )}

      {!['idle', 'bidding', 'charging', 'done'].includes(status) && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="6"
          fill="#00ff88"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: `drift ${drift} ease-in-out infinite`,
          }}
        />
      )}

      <line
        x1={pos.x}
        y1={pos.y}
        x2={tx + 8}
        y2={ty + th / 2}
        stroke="#00aaff"
        strokeWidth="0.5"
        opacity="0.5"
      />
      <rect
        x={tx}
        y={ty}
        width={tw}
        height={th}
        rx="3"
        fill="#0d1a2e"
        stroke={colors.stroke}
        strokeWidth="0.5"
      />
      <text
        x={tx + 6}
        y={ty + 14}
        fill={colors.fill}
        fontSize="8"
        fontWeight="700"
        fontFamily="Courier New, monospace"
      >
        {nameLabel}
      </text>
      <text
        x={tx + 6}
        y={ty + 26}
        fill={socBarFill(truck.state_of_charge)}
        fontSize="8"
        fontFamily="Courier New, monospace"
      >
        {socBarText(truck.state_of_charge)}
      </text>
      <text
        x={tx + tw - 6}
        y={ty + 26}
        textAnchor="end"
        fill="#6a8aaa"
        fontSize="7"
        fontFamily="Courier New, monospace"
      >
        {formatSocPercent(truck.state_of_charge)}
      </text>
      <text
        x={tx + 6}
        y={ty + 38}
        fill="#3a7aaa"
        fontSize="7"
        fontFamily="Courier New, monospace"
      >
        {reasoning}
      </text>
    </g>
  )
}

export default function TerminalMap({ powerBids, style, demo }) {
  const { rows: trucksDb } = useRealtimeTable('trucks')
  const { rows: baysDb } = useRealtimeTable('bays')

  const trucks = demo ? [demo.truck] : trucksDb
  const baysRows = demo ? demo.bays : baysDb

  return (
    <div
      style={{
        flex: 1,
        overflow: 'hidden',
        minWidth: 0,
        ...style,
      }}
    >
      <style>{svgStyles}</style>
      <svg
        viewBox="0 0 480 440"
        width="100%"
        height="100%"
        preserveAspectRatio="xMidYMid meet"
        style={{ display: 'block' }}
      >
        <defs>
          <pattern
            id="grid"
            width="20"
            height="20"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M20 0L0 0L0 20"
              fill="none"
              stroke="#1a2035"
              strokeWidth="0.5"
            />
          </pattern>
        </defs>

        <rect width="480" height="440" fill="#0a0e1a" />
        <rect width="480" height="440" fill="url(#grid)" />
        <rect width="480" height="440" fill="#ffaa00" opacity="0.025" />

        <rect
          x="20"
          y="30"
          width="200"
          height="180"
          fill="#0d1a2e"
          stroke="#1a4a7a"
          strokeWidth="1"
        />
        <text
          x="120"
          y="20"
          textAnchor="middle"
          fill="#1a6aaa"
          fontSize="9"
          letterSpacing="3"
          fontFamily="Courier New, monospace"
        >
          PIER T
        </text>
        {[
          { id: 'Y1', x: 30, y: 42 },
          { id: 'Y2', x: 80, y: 42 },
          { id: 'Y3', x: 130, y: 42 },
          { id: 'Y4', x: 30, y: 84 },
          { id: 'Y5', x: 80, y: 84 },
          { id: 'Y6', x: 130, y: 84 },
        ].map((y) => (
          <g key={y.id}>
            <rect
              x={y.x}
              y={y.y}
              width="40"
              height="30"
              fill="#0a1525"
              stroke="#1a3a5c"
              strokeWidth="0.5"
              rx="2"
            />
            <text
              x={y.x + 20}
              y={y.y + 19}
              textAnchor="middle"
              fill="#2a5a8a"
              fontSize="8"
              fontFamily="Courier New, monospace"
            >
              {y.id}
            </text>
          </g>
        ))}

        <rect
          x="260"
          y="30"
          width="200"
          height="180"
          fill="#0d1a2e"
          stroke="#1a4a7a"
          strokeWidth="1"
        />
        <text
          x="360"
          y="20"
          textAnchor="middle"
          fill="#1a6aaa"
          fontSize="9"
          letterSpacing="3"
          fontFamily="Courier New, monospace"
        >
          PIER E
        </text>
        {[
          { id: 'Y7', x: 270, y: 42 },
          { id: 'Y8', x: 320, y: 42 },
          { id: 'Y9', x: 370, y: 42 },
          { id: 'Y10', x: 270, y: 84 },
          { id: 'Y11', x: 320, y: 84 },
        ].map((y) => (
          <g key={y.id}>
            <rect
              x={y.x}
              y={y.y}
              width="40"
              height="30"
              fill="#0a1525"
              stroke="#1a3a5c"
              strokeWidth="0.5"
              rx="2"
            />
            <text
              x={y.x + 20}
              y={y.y + 19}
              textAnchor="middle"
              fill="#2a5a8a"
              fontSize="8"
              fontFamily="Courier New, monospace"
            >
              {y.id}
            </text>
          </g>
        ))}

        <line
          x1="120"
          y1="210"
          x2="120"
          y2="290"
          stroke="#1a3a5c"
          strokeWidth="1"
          strokeDasharray="4 3"
        />
        <line
          x1="360"
          y1="210"
          x2="360"
          y2="290"
          stroke="#1a3a5c"
          strokeWidth="1"
          strokeDasharray="4 3"
        />
        <line
          x1="120"
          y1="290"
          x2="240"
          y2="310"
          stroke="#1a3a5c"
          strokeWidth="1"
          strokeDasharray="4 3"
        />
        <line
          x1="360"
          y1="290"
          x2="240"
          y2="310"
          stroke="#1a3a5c"
          strokeWidth="1"
          strokeDasharray="4 3"
        />

        <rect
          x="140"
          y="310"
          width="200"
          height="110"
          rx="4"
          fill="#0a1a10"
          stroke="#00aa44"
          strokeWidth="1.5"
        />
        <text
          x="240"
          y="304"
          textAnchor="middle"
          fill="#00aa44"
          fontSize="8"
          letterSpacing="2"
          fontFamily="Courier New, monospace"
        >
          CHARGING BAY ZONE
        </text>
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <line
            key={i}
            x1={140 + i * 28}
            y1={310}
            x2={200 + i * 32}
            y2={420}
            fill="none"
            stroke="#00aa4410"
            strokeWidth="4"
          />
        ))}

        {(baysRows ?? []).map((bay) => {
          const name = bay.name
          const br = BAY_RECTS[name]
          if (!br) return null
          const isAvail = (bay.status ?? '').toLowerCase() === 'available'
          const assigned = bay.assigned_truck_id
            ? [...(trucks ?? [])].find((t) => t.id === bay.assigned_truck_id)
            : null
          const truckLabel = assigned?.name ?? ''

          if (isAvail) {
            return (
              <g key={bay.id}>
                <rect
                  x={br.x}
                  y={br.y}
                  width={br.w}
                  height={br.h}
                  rx="3"
                  fill="#0a1a10"
                  stroke="#00aa4466"
                  strokeWidth="1"
                />
                <text
                  x={br.x + br.w / 2}
                  y={br.y + br.h / 2 - 4}
                  textAnchor="middle"
                  fill="#00aa44"
                  fontSize="8"
                  fontFamily="Courier New, monospace"
                >
                  {name}
                </text>
                <text
                  x={br.x + br.w / 2}
                  y={br.y + br.h / 2 + 10}
                  textAnchor="middle"
                  fill="#00aa4466"
                  fontSize="9"
                  fontFamily="Courier New, monospace"
                >
                  ⚡
                </text>
              </g>
            )
          }

          return (
            <g key={bay.id}>
              <rect
                x={br.x}
                y={br.y}
                width={br.w}
                height={br.h}
                rx="3"
                fill="#2a1a00"
                stroke="#ffaa00"
                strokeWidth="1.5"
                style={{
                  transformBox: 'fill-box',
                  transformOrigin: 'center',
                  animation: 'baylock 0.8s infinite',
                }}
              />
              <text
                x={br.x + br.w / 2}
                y={br.y + 12}
                textAnchor="middle"
                fill="#ffaa00"
                fontSize="8"
                fontFamily="Courier New, monospace"
              >
                {name}
              </text>
              <text
                x={br.x + br.w / 2}
                y={br.y + 24}
                textAnchor="middle"
                fill="#ffaa0088"
                fontSize="7"
                fontFamily="Courier New, monospace"
              >
                {truckLabel}
              </text>
              <text
                x={br.x + br.w / 2}
                y={br.y + br.h - 4}
                textAnchor="middle"
                fill="#ffaa00"
                fontSize="9"
                fontFamily="Courier New, monospace"
              >
                ⚡
              </text>
            </g>
          )
        })}

        {(trucks ?? []).map((truck) => (
          <TruckNode
            key={truck.id}
            truck={truck}
            baysRows={baysRows}
            powerBids={powerBids}
          />
        ))}
      </svg>
    </div>
  )
}
