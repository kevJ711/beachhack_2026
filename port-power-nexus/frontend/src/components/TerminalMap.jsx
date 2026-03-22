import { useEffect, useRef, useState } from 'react'
import useRealtimeTable from '../hooks/useRealtimeTable'
import useSmoothPosition from '../hooks/useSmoothPosition'
import useSmoothSoc from '../hooks/useSmoothSoc'
import {
  bayIsActivelyCharging,
  effectiveMapStatus,
} from '../lib/mapTruckStatus'
import {
  EXIT_RIGHT_X,
  PIER_BOXES,
  SPAWN_LEFT_X,
  getIdleCenterForTruck,
} from '../lib/pierSlots'
import { formatSocPercent, normalizeSoc } from '../lib/truckDisplay'

/** Approach + UI offsets — idle berth centers come from `getIdleCenterForTruck` (pier Y1…Y11). */
const TRUCK_PATHS = {
  amazon_truck: {
    approachPosition: { x: 175, y: 275 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 4.2,
  },
  fedex_truck: {
    approachPosition: { x: 210, y: 268 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 5.1,
  },
  ups_truck: {
    approachPosition: { x: 265, y: 280 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 3.6,
  },
  dhl_truck: {
    approachPosition: { x: 150, y: 272 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 4.5,
  },
  rivian_truck: {
    approachPosition: { x: 230, y: 285 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 5.8,
  },
  TRUCK_01: {
    approachPosition: { x: 175, y: 275 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 4.2,
  },
  TRUCK_07: {
    approachPosition: { x: 210, y: 268 },
    tooltipOffset: { x: 20, y: -50 },
    driftDuration: 5.1,
  },
  TRUCK_12: {
    approachPosition: { x: 265, y: 280 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 3.6,
  },
  TRUCK_15: {
    approachPosition: { x: 300, y: 272 },
    tooltipOffset: { x: -110, y: -50 },
    driftDuration: 4.8,
  },
  TRUCK_03: {
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
  const status = effectiveMapStatus(truck, baysRows)
  const idle = getIdleCenterForTruck(truck.name)

  if (status === 'at_port') {
    return { x: EXIT_RIGHT_X, y: idle.y }
  }
  if (status === 'charging') {
    const bay = (baysRows ?? []).find((b) => b.id === truck.bay_id)
    const bayName = bay?.name
    if (bayName && BAY_POSITIONS[bayName]) {
      const p = BAY_POSITIONS[bayName]
      return { x: p.cx, y: p.cy }
    }
    return { x: idle.x, y: idle.y }
  }
  if (status === 'bidding') {
    // Approach from the truck's own pier slot toward the charging zone
    return { x: idle.x, y: idle.y + 20 }
  }
  return { x: idle.x, y: idle.y }
}

function nodeColors(status) {
  const s = (status ?? 'idle').toLowerCase()
  if (s === 'idle') return { fill: '#00ff88', stroke: '#00ff88' }
  if (s === 'bidding') return { fill: '#00aaff', stroke: '#00aaff' }
  if (s === 'charging') return { fill: '#ffaa00', stroke: '#ffaa00' }
  if (s === 'at_port') return { fill: '#6a8aaa', stroke: '#88aacc' }
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

const TOOLTIP_OFFSETS = [
  { x: 20, y: -50 },
  { x: 20, y: -50 },
  { x: -110, y: -50 },
  { x: 20, y: -50 },
  { x: -110, y: -50 },
]

const TRUCK_ORDER = ['amazon_truck', 'fedex_truck', 'ups_truck', 'dhl_truck', 'rivian_truck']

function getTruckTooltipOffset(name) {
  const idx = TRUCK_ORDER.indexOf(name)
  return TOOLTIP_OFFSETS[idx >= 0 ? idx : 0]
}

function TruckNode({ truck, baysRows, powerBids, respawnEpoch = 0 }) {
  const status = effectiveMapStatus(truck, baysRows)
  const idleCenter = getIdleCenterForTruck(truck.name)
  const target = resolveTruckPosition(truck, baysRows)
  const moveMs =
    respawnEpoch > 0 ? 2000 : status === 'at_port' ? 2200 : 1500
  const pos = useSmoothPosition(
    target.x,
    target.y,
    moveMs,
    respawnEpoch,
    respawnEpoch > 0 ? SPAWN_LEFT_X : null,
    respawnEpoch > 0 ? idleCenter.y : null
  )
  const path = getTruckPath(truck.name)
  const off = getTruckTooltipOffset(truck.name)
  const colors = nodeColors(status)
  const drift = `${path?.driftDuration ?? 4}s`
  const reasoning = latestReasoningForTruck(
    powerBids,
    truck.id,
    MAP_TOOLTIP_REASON_MAX
  )
  const nameLabel = truncateTooltipText(String(truck.name ?? ''), MAP_TOOLTIP_NAME_MAX)
  const anchorX = status === 'charging' ? target.x : pos.x
  const anchorY = status === 'charging' ? target.y : pos.y
  const tx = anchorX + off.x
  const ty = anchorY + off.y
  const tw = 100
  const th = 46
  const socDisplay = useSmoothSoc(truck.state_of_charge ?? 0)

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
          cx={target.x}
          cy={target.y}
          r="6"
          fill="#ffaa00"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: 'blink 1.2s infinite',
          }}
        />
      )}

      {status === 'at_port' && (
        <circle
          cx={pos.x}
          cy={pos.y}
          r="5"
          fill="#88aacc"
          opacity="0.85"
          style={{
            transformBox: 'fill-box',
            transformOrigin: 'center',
            animation: 'drift 3s ease-in-out infinite',
          }}
        />
      )}

      {status === 'done' && (
        <circle cx={pos.x} cy={pos.y} r="6" fill="#3a5a6a" />
      )}

      {!['idle', 'bidding', 'charging', 'at_port', 'done'].includes(status) && (
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
        x1={anchorX}
        y1={anchorY}
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
        fill={socBarFill(socDisplay)}
        fontSize="8"
        fontFamily="Courier New, monospace"
      >
        {socBarText(socDisplay)}
      </text>
      <text
        x={tx + tw - 6}
        y={ty + 26}
        textAnchor="end"
        fill="#6a8aaa"
        fontSize="7"
        fontFamily="Courier New, monospace"
      >
        {formatSocPercent(socDisplay)}
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

  const [respawnEpoch, setRespawnEpoch] = useState({})
  const prevStatusRef = useRef({})

  useEffect(() => {
    for (const t of trucks ?? []) {
      const st = effectiveMapStatus(t, baysRows)
      const id = t.id
      const was = prevStatusRef.current[id]
      if (was === 'at_port' && st === 'idle') {
        setRespawnEpoch((r) => ({ ...r, [id]: (r[id] ?? 0) + 1 }))
      }
      prevStatusRef.current[id] = st
    }
  }, [trucks, baysRows])

  const idlePierLit = new Set(
    (trucks ?? [])
      .filter((t) => effectiveMapStatus(t, baysRows) === 'idle')
      .map((t) => getIdleCenterForTruck(t.name).pierId)
  )

  // Hide trucks at 100% / departed (at_port) — next tick they reset as a “new” inbound unit.
  const mapTrucks = (trucks ?? []).filter(
    (t) => effectiveMapStatus(t, baysRows) !== 'at_port'
  )

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
        {PIER_BOXES.filter((b) => b.x < 200).map((box) => {
          const lit = idlePierLit.has(box.id)
          return (
            <g key={box.id}>
              <rect
                x={box.x}
                y={box.y}
                width={box.w}
                height={box.h}
                fill={lit ? '#2a2210' : '#0a1525'}
                stroke={lit ? '#ffcc00' : '#1a3a5c'}
                strokeWidth={lit ? 1.8 : 0.5}
                rx="2"
                style={
                  lit
                    ? {
                        filter: 'drop-shadow(0 0 6px rgba(255, 204, 0, 0.45))',
                      }
                    : undefined
                }
              />
              <text
                x={box.x + box.w / 2}
                y={box.y + 19}
                textAnchor="middle"
                fill={lit ? '#ffdd66' : '#2a5a8a'}
                fontSize="8"
                fontFamily="Courier New, monospace"
              >
                {box.id}
              </text>
            </g>
          )
        })}

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
        {PIER_BOXES.filter((b) => b.x >= 200).map((box) => {
          const lit = idlePierLit.has(box.id)
          return (
            <g key={box.id}>
              <rect
                x={box.x}
                y={box.y}
                width={box.w}
                height={box.h}
                fill={lit ? '#2a2210' : '#0a1525'}
                stroke={lit ? '#ffcc00' : '#1a3a5c'}
                strokeWidth={lit ? 1.8 : 0.5}
                rx="2"
                style={
                  lit
                    ? {
                        filter: 'drop-shadow(0 0 6px rgba(255, 204, 0, 0.45))',
                      }
                    : undefined
                }
              />
              <text
                x={box.x + box.w / 2}
                y={box.y + 19}
                textAnchor="middle"
                fill={lit ? '#ffdd66' : '#2a5a8a'}
                fontSize="8"
                fontFamily="Courier New, monospace"
              >
                {box.id}
              </text>
            </g>
          )
        })}

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
          const activeCharge = bayIsActivelyCharging(bay, trucks)
          const isAvail = (bay.status ?? '').toLowerCase() === 'available' || !activeCharge
          const assigned = bay.assigned_truck_id
            ? [...(trucks ?? [])].find((t) => t.id === bay.assigned_truck_id)
            : null
          const truckLabel =
            activeCharge && assigned?.name ? assigned.name : ''

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

        {mapTrucks.map((truck) => (
          <TruckNode
            key={truck.id}
            truck={truck}
            baysRows={baysRows}
            powerBids={powerBids}
            respawnEpoch={respawnEpoch[truck.id] ?? 0}
          />
        ))}
      </svg>
    </div>
  )
}
