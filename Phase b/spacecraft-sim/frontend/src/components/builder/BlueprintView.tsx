/**
 * BlueprintView — a deck plan of the same scenario the graph canvas edits.
 *
 * The node graph answers "what connects to what". This answers "what does the
 * ship look like": a hull wrapping pressurised modules, corridors you could
 * walk, and rooms fitted out for what they are actually for.
 *
 * Both views read the canonical scenario store and nothing else, so dragging a
 * node on the canvas moves its room here too.
 *
 * On colour: rooms share one fill. Six module-type hues fail badly as an
 * identity channel on a map — blue and violet sit ΔE 0.3 apart under
 * deuteranopia, and amber vs orange only 9.6 apart even with full colour
 * vision. Identity is carried by each room's name, its fit-out and its type
 * label; the type hue is a reinforcing accent strip only. Colour is reserved
 * for state that has to shout: fire, and corridor condition.
 */

import { useMemo } from 'react'
import { useScenarioStore } from '../../store/useScenarioStore'
import type { ScenarioConnection, ScenarioModule } from '../../types/scenario'

interface Props {
  selectedModuleId: string | null
  selectedConnectionId: string | null
  onModuleSelect: (id: string | null) => void
  onConnectionSelect: (id: string | null) => void
}

const TYPE_ACCENT: Record<string, string> = {
  habitat: '#3b82f6',
  storage: '#8b5cf6',
  life_support: '#06b6d4',
  power: '#f59e0b',
  propulsion: '#f97316',
  other: '#64748b',
}

const TYPE_GLYPH: Record<string, string> = {
  habitat: '⌂',
  storage: '▦',
  life_support: '✚',
  power: '⚡',
  propulsion: '➤',
  other: '◇',
}

const TYPE_LABEL: Record<string, string> = {
  habitat: 'HABITAT',
  storage: 'STORAGE',
  life_support: 'LIFE SUPPORT',
  power: 'POWER',
  propulsion: 'PROPULSION',
  other: 'MODULE',
}

// Deck surfaces. One fill for every room, as on a real plan.
const FLOOR = '#2f4b7c'
const FLOOR_EDGE = '#5b82c4'
const CORRIDOR = '#243c63'
const CORRIDOR_EDGE = '#3d5f96'

// The pressure hull drawn around everything, so the modules read as one ship
// rather than as boxes floating apart.
const HULL_RIM = '#8ea6c9'
const HULL_BODY = '#28324a'
const HULL_RIM_PAD = 15
const HULL_BODY_PAD = 11

/**
 * A fixed star field. Generated once from a seeded PRNG rather than
 * Math.random(), so the sky does not reshuffle on every React render.
 */
function mulberry32(seed: number) {
  return function () {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

const SPACE_BACKGROUND = (() => {
  const rand = mulberry32(20260826)
  const stars: string[] = []
  for (let i = 0; i < 90; i += 1) {
    const x = (rand() * 100).toFixed(2)
    const y = (rand() * 100).toFixed(2)
    const big = rand() < 0.12
    const size = big ? 2 : 1
    const alpha = (big ? 0.55 : 0.2) + rand() * 0.4
    stars.push(
      `radial-gradient(${size}px ${size}px at ${x}% ${y}%, rgba(255,255,255,${alpha.toFixed(
        2
      )}), rgba(255,255,255,0))`
    )
  }
  const nebula = [
    'radial-gradient(55% 42% at 16% 20%, rgba(56,89,168,0.22), rgba(0,0,0,0) 70%)',
    'radial-gradient(48% 38% at 84% 76%, rgba(118,62,158,0.18), rgba(0,0,0,0) 70%)',
    'radial-gradient(40% 30% at 62% 12%, rgba(30,110,140,0.12), rgba(0,0,0,0) 70%)',
  ]
  return [...nebula, ...stars].join(', ')
})()

// A graph node's stored position is its top-left, and the node renders about
// this big. Centring the room on the node's centre — not on its corner — keeps
// the deck plan in the same arrangement the user laid out on the canvas.
const NODE_W = 180
const NODE_H = 120

interface Room {
  module: ScenarioModule
  x: number
  y: number
  w: number
  h: number
}

/** Rooms grow with what they hold, so a crowded module reads as a bigger space. */
function roomSize(module: ScenarioModule) {
  return {
    w: 146 + Math.min(module.crew.length, 6) * 10,
    h: 108 + Math.min(module.equipment.length, 6) * 6,
  }
}

/** Where a line from the room's centre toward `tx,ty` crosses its wall. */
function wallPoint(room: Room, tx: number, ty: number) {
  const cx = room.x + room.w / 2
  const cy = room.y + room.h / 2
  const dx = tx - cx
  const dy = ty - cy
  if (dx === 0 && dy === 0) return { x: cx, y: cy }
  const sx = dx === 0 ? Infinity : room.w / 2 / Math.abs(dx)
  const sy = dy === 0 ? Infinity : room.h / 2 / Math.abs(dy)
  const s = Math.min(sx, sy)
  return { x: cx + dx * s, y: cy + dy * s }
}

function corridorWidth(connection: ScenarioConnection) {
  return connection.type === 'leak' ? 8 : 22
}

export default function BlueprintView({
  selectedModuleId,
  selectedConnectionId,
  onModuleSelect,
  onConnectionSelect,
}: Props) {
  const { scenario } = useScenarioStore()

  const rooms = useMemo<Record<string, Room>>(() => {
    const out: Record<string, Room> = {}
    for (const module of Object.values(scenario.modules)) {
      const { w, h } = roomSize(module)
      out[module.id] = {
        module,
        x: module.position.x + NODE_W / 2 - w / 2,
        y: module.position.y + NODE_H / 2 - h / 2,
        w,
        h,
      }
    }
    return out
  }, [scenario.modules])

  const roomList = Object.values(rooms)
  const connections = Object.values(scenario.connections)

  const viewBox = useMemo(() => {
    if (roomList.length === 0) return '0 0 600 400'
    const pad = 90
    const minX = Math.min(...roomList.map((r) => r.x)) - pad
    const minY = Math.min(...roomList.map((r) => r.y)) - pad
    const maxX = Math.max(...roomList.map((r) => r.x + r.w)) + pad
    const maxY = Math.max(...roomList.map((r) => r.y + r.h)) + pad
    return `${minX} ${minY} ${Math.max(1, maxX - minX)} ${Math.max(1, maxY - minY)}`
  }, [roomList])

  if (roomList.length === 0) {
    return (
      <Shell>
        <div
          style={{
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#64748b',
            fontSize: 12,
            textAlign: 'center',
            padding: 24,
          }}
        >
          Add a module to see the deck plan.
        </div>
      </Shell>
    )
  }

  /**
   * The hull is one silhouette, drawn as overlapping opaque shapes: every room
   * inflated, every corridor thickened. Because they share a fill they merge
   * into a single outline without any polygon union maths.
   */
  const hullLayer = (pad: number, fill: string, key: string) => (
    <g key={key}>
      {connections.map((conn) => {
        const from = rooms[conn.source]
        const to = rooms[conn.target]
        if (!from || !to) return null
        const a = wallPoint(from, to.x + to.w / 2, to.y + to.h / 2)
        const b = wallPoint(to, from.x + from.w / 2, from.y + from.h / 2)
        return (
          <line
            key={conn.id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={fill}
            strokeWidth={corridorWidth(conn) + pad * 2}
            strokeLinecap="round"
          />
        )
      })}
      {roomList.map((room) => (
        <rect
          key={room.module.id}
          x={room.x - pad}
          y={room.y - pad}
          width={room.w + pad * 2}
          height={room.h + pad * 2}
          rx={pad + 12}
          fill={fill}
        />
      ))}
    </g>
  )

  return (
    <Shell>
      <svg
        viewBox={viewBox}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block', position: 'relative' }}
        role="img"
        aria-label={`Deck plan: ${roomList.length} modules, ${connections.length} connections.`}
      >
        <defs>
          {[
            ['power', '#facc15'],
            ['air', '#7dd3fc'],
            ['water', '#2563eb'],
          ].map(([id, color]) => (
            <marker key={id} id={`utility-arrow-${id}`} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto" markerUnits="strokeWidth">
              <path d="M0,0 L0,6 L6,3 z" fill={color} />
            </marker>
          ))}
        </defs>
        {hullLayer(HULL_RIM_PAD, HULL_RIM, 'hull-rim')}
        {hullLayer(HULL_BODY_PAD, HULL_BODY, 'hull-body')}

        {/* Corridors sit under the rooms so they read as floor running between. */}
        <g>
          {connections.map((conn) => (
            <Corridor
              key={conn.id}
              connection={conn}
              from={rooms[conn.source]}
              to={rooms[conn.target]}
              selected={conn.id === selectedConnectionId}
              escapeTarget={
                scenario.emergency?.escapeTarget?.connectionId === conn.id
                  ? scenario.emergency.escapeTarget
                  : undefined
              }
              onSelect={() => {
                onConnectionSelect(conn.id)
                onModuleSelect(null)
              }}
            />
          ))}
        </g>

        <g>
          {roomList.map((room) => (
            <RoomShape
              key={room.module.id}
              room={room}
              onFire={scenario.emergency?.affectedModuleId === room.module.id}
              selected={room.module.id === selectedModuleId}
              onSelect={() => {
                onModuleSelect(room.module.id)
                onConnectionSelect(null)
              }}
            />
          ))}
        </g>
      </svg>

      <Legend />
    </Shell>
  )
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        backgroundColor: '#05060a',
        backgroundImage: SPACE_BACKGROUND,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          position: 'absolute',
          top: 10,
          left: 14,
          color: '#7c8ba4',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.1em',
          zIndex: 2,
          pointerEvents: 'none',
        }}
      >
        DECK PLAN
      </div>
      {children}
    </div>
  )
}

function Corridor({
  connection,
  from,
  to,
  selected,
  escapeTarget,
  onSelect,
}: {
  connection: ScenarioConnection
  from?: Room
  to?: Room
  selected: boolean
  escapeTarget?: import('../../types/scenario').EscapeTarget
  onSelect: () => void
}) {
  if (!from || !to) return null

  const a = wallPoint(from, to.x + to.w / 2, to.y + to.h / 2)
  const b = wallPoint(to, from.x + from.w / 2, from.y + from.h / 2)

  const closed = connection.state === 'closed'
  const isLeak = connection.type === 'leak'
  const isImv = connection.type === 'imv'

  const width = corridorWidth(connection)
  const stroke = isLeak ? '#7f1d1d' : CORRIDOR
  const edge = isLeak ? '#ef4444' : selected ? '#93c5fd' : escapeTarget ? '#34d399' : CORRIDOR_EDGE

  const mx = (a.x + b.x) / 2
  const my = (a.y + b.y) / 2

  return (
    <g style={{ cursor: 'pointer' }} onClick={onSelect}>
      {/* Wide invisible hit area — the corridor itself is thin to land on. */}
      <line
        x1={a.x}
        y1={a.y}
        x2={b.x}
        y2={b.y}
        stroke="transparent"
        strokeWidth={Math.max(width + 14, 26)}
      />
      <line
        x1={a.x}
        y1={a.y}
        x2={b.x}
        y2={b.y}
        stroke={edge}
        strokeWidth={width + 3}
        opacity={closed ? 0.5 : 1}
      />
      <line
        x1={a.x}
        y1={a.y}
        x2={b.x}
        y2={b.y}
        stroke={stroke}
        strokeWidth={width}
        strokeDasharray={isImv ? '10,7' : undefined}
        opacity={closed ? 0.55 : 1}
      />

      {connection.type === 'hatch' && (
        <UtilityLines connection={connection} from={from} to={to} a={a} b={b} />
      )}

      {/* Condition marker. Never colour alone: each state carries a glyph. */}
      <g transform={`translate(${mx} ${my})`}>
        <circle
          r={13}
          fill="#0f1319"
          stroke={closed ? '#ef4444' : isLeak ? '#ef4444' : isImv ? '#06b6d4' : CORRIDOR_EDGE}
          strokeWidth={2}
        />
        <text
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={closed ? 13 : connection.type === 'hatch' ? 8.5 : 11}
          fontWeight={700}
          fill={closed ? '#fca5a5' : isLeak ? '#fca5a5' : isImv ? '#67e8f9' : '#cbd5e1'}
        >
          {closed ? '✕' : isLeak ? '≈' : isImv ? '↻' : `H ${Math.round(connection.connectivity)}`}
        </text>
      </g>
      {escapeTarget && (
        <text
          x={mx}
          y={my + 22}
          textAnchor="middle"
          fontSize={8}
          fontWeight={700}
          fill="#34d399"
        >
          ESC {escapeTarget.fromModuleId === connection.source ? '→' : '←'}
        </text>
      )}
    </g>
  )
}

function UtilityLines({ connection, from, to, a, b }: { connection: ScenarioConnection; from: Room; to: Room; a: { x: number; y: number }; b: { x: number; y: number } }) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const length = Math.hypot(dx, dy) || 1
  const nx = -dy / length
  const ny = dx / length
  const utility = [
    { id: 'power', on: connection.powerLineOn, color: '#facc15', offset: -6, fromLevel: from.module.powerLevelW ?? 0, toLevel: to.module.powerLevelW ?? 0 },
    { id: 'air', on: connection.airLineOn && connection.state === 'open', color: '#7dd3fc', offset: 0, fromLevel: (from.module.oxygenFraction ?? 0) * 100, toLevel: (to.module.oxygenFraction ?? 0) * 100 },
    { id: 'water', on: connection.waterLineOn, color: '#2563eb', offset: 6, fromLevel: from.module.waterStoredKg ?? 0, toLevel: to.module.waterStoredKg ?? 0 },
  ]

  return (
    <g pointerEvents="none">
      {utility.filter((line) => line.on).map((line) => {
        const reverse = line.toLevel > line.fromLevel
        const start = reverse ? b : a
        const end = reverse ? a : b
        const flowing = line.fromLevel !== line.toLevel
        const connectivityFactor = line.id === 'air'
          ? Math.max(0.05, connection.connectivity / 100)
          : line.id === 'power'
            ? Math.max(0.03, connection.powerTransferFactor)
            : 1
        const coordinates = {
          x1: start.x + nx * line.offset,
          y1: start.y + ny * line.offset,
          x2: end.x + nx * line.offset,
          y2: end.y + ny * line.offset,
        }
        return (
          <g key={line.id}>
            <line
              {...coordinates}
              stroke={line.color}
              strokeWidth={5}
              opacity={(flowing ? 0.16 : 0.08) * connectivityFactor}
            />
            <line
              {...coordinates}
              stroke={line.color}
              strokeWidth={2.4 * Math.max(0.35, connectivityFactor)}
              strokeDasharray={flowing ? '2,7' : '5,3'}
              strokeLinecap="round"
              opacity={0.35 + 0.63 * connectivityFactor}
              markerEnd={flowing ? `url(#utility-arrow-${line.id})` : undefined}
            >
              {flowing && (
                <animate
                  attributeName="stroke-dashoffset"
                  from="0"
                  to="-18"
                  dur={line.id === 'power' ? '0.7s' : line.id === 'air' ? `${(1 / connectivityFactor).toFixed(2)}s` : '1.25s'}
                  repeatCount="indefinite"
                />
              )}
            </line>
          </g>
        )
      })}
    </g>
  )
}

/**
 * What the room is fitted out with. Drawn faintly, as furniture on a plan:
 * it tells you at a glance that this is somewhere people sleep, or where the
 * reactor lives, without competing with the label.
 */
function Fitout({ type }: { type: string }) {
  const ink = '#bcd2f5'
  const soft = { fill: 'none', stroke: ink, strokeWidth: 1.6, opacity: 0.55 } as const
  const solid = { fill: ink, opacity: 0.34 } as const

  switch (type) {
    case 'habitat': // two bunks and a table
      return (
        <g>
          <rect x={-30} y={-13} width={26} height={11} rx={3} {...soft} />
          <rect x={-30} y={-13} width={8} height={11} rx={3} {...solid} />
          <rect x={-30} y={3} width={26} height={11} rx={3} {...soft} />
          <rect x={-30} y={3} width={8} height={11} rx={3} {...solid} />
          <circle cx={12} cy={0} r={9} {...soft} />
          <circle cx={12} cy={0} r={3} {...solid} />
        </g>
      )
    case 'storage': // stacked crates
      return (
        <g>
          {[
            [-30, -12],
            [-13, -12],
            [4, -12],
            [-22, 4],
            [-5, 4],
          ].map(([cx, cy], i) => (
            <g key={i}>
              <rect x={cx} y={cy} width={15} height={15} rx={2} {...soft} />
              <line
                x1={cx}
                y1={cy + 7.5}
                x2={cx + 15}
                y2={cy + 7.5}
                stroke={ink}
                strokeWidth={1.2}
                opacity={0.35}
              />
            </g>
          ))}
        </g>
      )
    case 'life_support': // gas tanks feeding a scrubber
      return (
        <g>
          <rect x={-30} y={-14} width={13} height={28} rx={6.5} {...soft} />
          <rect x={-13} y={-14} width={13} height={28} rx={6.5} {...soft} />
          <rect x={-30} y={2} width={13} height={12} rx={4} {...solid} />
          <path d="M2 0 h10 v-9 h12" {...soft} />
          <rect x={22} y={-13} width={12} height={26} rx={3} {...soft} />
          <line x1={24} y1={-6} x2={32} y2={-6} stroke={ink} strokeWidth={1.2} opacity={0.4} />
          <line x1={24} y1={0} x2={32} y2={0} stroke={ink} strokeWidth={1.2} opacity={0.4} />
          <line x1={24} y1={6} x2={32} y2={6} stroke={ink} strokeWidth={1.2} opacity={0.4} />
        </g>
      )
    case 'power': // reactor core and battery cells
      return (
        <g>
          <circle cx={-16} cy={0} r={15} {...soft} />
          <circle cx={-16} cy={0} r={8} {...soft} />
          <circle cx={-16} cy={0} r={3.5} {...solid} />
          {[0, 1, 2].map((i) => (
            <rect key={i} x={10} y={-14 + i * 10} width={24} height={7} rx={2} {...soft} />
          ))}
        </g>
      )
    case 'propulsion': // engine bell and thrust
      return (
        <g>
          <path d="M-8 -15 L10 -22 L10 22 L-8 15 Z" {...soft} />
          <rect x={-24} y={-9} width={16} height={18} rx={3} {...soft} />
          {[-9, 0, 9].map((dy, i) => (
            <line
              key={i}
              x1={13}
              y1={dy}
              x2={30}
              y2={dy}
              stroke={ink}
              strokeWidth={1.6}
              opacity={0.4}
              strokeDasharray="4,3"
            />
          ))}
        </g>
      )
    default: // unassigned deck space
      return (
        <g>
          {[0, 1, 2].map((r) =>
            [0, 1, 2, 3].map((c) => (
              <rect
                key={`${r}-${c}`}
                x={-28 + c * 16}
                y={-14 + r * 12}
                width={9}
                height={7}
                rx={1.5}
                fill={ink}
                opacity={0.16}
              />
            ))
          )}
        </g>
      )
  }
}

function RoomShape({
  room,
  onFire,
  selected,
  onSelect,
}: {
  room: Room
  onFire: boolean
  selected: boolean
  onSelect: () => void
}) {
  const { module, x, y, w, h } = room
  const accent = TYPE_ACCENT[module.type] ?? TYPE_ACCENT.other
  const glyph = TYPE_GLYPH[module.type] ?? TYPE_GLYPH.other
  const label = TYPE_LABEL[module.type] ?? TYPE_LABEL.other

  const border = onFire ? '#ef4444' : selected ? '#93c5fd' : FLOOR_EDGE
  const crew = module.crew.length
  const equipment = module.equipment.length

  // Three bands: header, fit-out, then the occupancy footer.
  const headerBottom = y + 46
  const footerTop = y + h - 30
  const fitoutCy = (headerBottom + footerTop) / 2
  // Occupancy marks keep to the left half; the fit-out drawing owns the right,
  // so a busy module never stamps crew dots over its own furniture.
  const perRow = Math.max(1, Math.floor((w / 2 - 26) / 15))

  return (
    <g style={{ cursor: 'pointer' }} onClick={onSelect}>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={10}
        fill={FLOOR}
        stroke={border}
        strokeWidth={onFire || selected ? 3 : 2}
      />

      {/* Type accent: reinforcement for the label, never the identity itself. */}
      <rect x={x} y={y} width={w} height={5} rx={2.5} fill={accent} />

      <text x={x + 12} y={y + 26} fontSize={13} fontWeight={700} fill="#f8fafc">
        {glyph} {module.name}
      </text>
      <text
        x={x + 12}
        y={y + 40}
        fontSize={8.5}
        fontWeight={700}
        fill="#bfdbfe"
        letterSpacing="0.08em"
      >
        {label}
      </text>

      {onFire && (
        <text x={x + w - 11} y={y + 27} fontSize={15} textAnchor="end">
          ◉
        </text>
      )}

      <g transform={`translate(${x + w / 2 + 14} ${fitoutCy})`}>
        <Fitout type={module.type} />
      </g>

      {/* Crew: filled circles. Equipment: squares. Counted in text too, so the
          room stays readable when the marks get small. */}
      <g>
        {Array.from({ length: Math.min(crew, perRow * 2) }).map((_, i) => (
          <circle
            key={`c${i}`}
            cx={x + 17 + (i % perRow) * 15}
            cy={headerBottom + 12 + Math.floor(i / perRow) * 15}
            r={5}
            fill="#fcd34d"
            stroke="#16203a"
            strokeWidth={1.5}
          />
        ))}
      </g>
      <g>
        {Array.from({ length: Math.min(equipment, perRow * 2) }).map((_, i) => (
          <rect
            key={`e${i}`}
            x={x + 12 + (i % perRow) * 15}
            y={footerTop + 4 + Math.floor(i / perRow) * 13}
            width={9}
            height={9}
            rx={1.5}
            fill="#9fb4d4"
            stroke="#16203a"
            strokeWidth={1.5}
          />
        ))}
      </g>

      <text
        x={x + w - 10}
        y={y + h - 10}
        fontSize={9.5}
        textAnchor="end"
        fill="#cbd5e1"
        fontWeight={600}
      >
        {crew} crew · {equipment} eq
      </text>
    </g>
  )
}

function Legend() {
  const items: Array<[string, string, string]> = [
    ['H', 'var(--ink-2)', 'Hatch'],
    ['↻', 'var(--verified)', 'IMV duct'],
    ['✕', 'var(--ember)', 'Closed'],
    ['≈', 'var(--ember)', 'Leak'],
    ['━', '#facc15', 'Power'],
    ['━', '#7dd3fc', 'Air'],
    ['━', '#2563eb', 'Water'],
  ]
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 10,
        left: 12,
        right: 12,
        display: 'flex',
        gap: 14,
        flexWrap: 'wrap',
        alignItems: 'center',
        background: 'rgba(5, 6, 10, 0.82)',
        border: '1px solid #1e2530',
        borderRadius: 6,
        padding: '6px 10px',
        fontSize: 10,
        color: '#7c8ba4',
        pointerEvents: 'none',
      }}
    >
      {items.map(([glyph, color, text]) => (
        <span key={text} style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
          <span style={{ color, fontWeight: 700 }}>{glyph}</span>
          {text}
        </span>
      ))}
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <span
          style={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: '#fcd34d',
            display: 'inline-block',
          }}
        />
        Crew
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
        <span
          style={{ width: 9, height: 9, background: '#9fb4d4', display: 'inline-block' }}
        />
        Equipment
      </span>
    </div>
  )
}
