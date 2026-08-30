/**
 * The hero's right half: a chart that reads as spacecraft topology and as a
 * star chart at the same time.
 *
 * It is deliberately the same grammar the builder uses — nodes joined by thin
 * paths — because that graph *is* the product. A rendered spacecraft would be
 * decoration; this is a preview of the thing you are about to draw.
 *
 * Geometry is fixed rather than generated: a layout that reshuffles on every
 * render would flicker, and the arrangement is a composition, not data.
 */

const NODES = [
  { id: 'n1', x: 118, y: 96, r: 4.5, label: 'HAB' },
  { id: 'n2', x: 244, y: 62, r: 3.5, label: null },
  { id: 'n3', x: 322, y: 148, r: 5.5, label: 'STO' },
  { id: 'n4', x: 196, y: 208, r: 4, label: null },
  { id: 'n5', x: 88, y: 266, r: 3.5, label: 'PWR' },
  { id: 'n6', x: 300, y: 300, r: 4.5, label: null },
  { id: 'n7', x: 392, y: 236, r: 3, label: null },
  { id: 'n8', x: 156, y: 352, r: 3, label: null },
]

/** Structural links — the vessel. */
const SPINE: [string, string][] = [
  ['n1', 'n2'],
  ['n2', 'n3'],
  ['n1', 'n4'],
  ['n3', 'n4'],
  ['n4', 'n5'],
  ['n4', 'n6'],
  ['n3', 'n7'],
  ['n6', 'n7'],
  ['n5', 'n8'],
  ['n6', 'n8'],
]

/** A single traced route — the advice, drawn through the architecture. */
const ROUTE = ['n5', 'n4', 'n3', 'n7']

const byId = Object.fromEntries(NODES.map((n) => [n.id, n]))

export default function ConstellationChart() {
  const routePath = ROUTE.map((id, i) => {
    const n = byId[id]
    return `${i === 0 ? 'M' : 'L'}${n.x},${n.y}`
  }).join(' ')

  return (
    <svg
      viewBox="0 0 460 420"
      role="img"
      aria-label="An abstract spacecraft topology drawn as a navigation chart: eight modules joined by pathways, with one route traced through them."
      style={{ width: '100%', height: 'auto', display: 'block', overflow: 'visible' }}
    >
      <defs>
        <pattern id="circe-grid" width="46" height="46" patternUnits="userSpaceOnUse">
          <path
            d="M46 0H0V46"
            fill="none"
            stroke="var(--line-soft)"
            strokeWidth="0.5"
          />
        </pattern>
        <radialGradient id="circe-vignette" cx="50%" cy="45%" r="62%">
          <stop offset="0%" stopColor="var(--void)" stopOpacity="0" />
          <stop offset="100%" stopColor="var(--void)" stopOpacity="1" />
        </radialGradient>
      </defs>

      {/* Coordinate ground */}
      <rect width="460" height="420" fill="url(#circe-grid)" />
      <rect width="460" height="420" fill="url(#circe-vignette)" />

      {/* Chart frame ticks — navigation instrument, not decoration */}
      <g stroke="var(--ink-4)" strokeWidth="0.75" opacity="0.55">
        {[0, 1, 2, 3, 4].map((i) => (
          <path key={`t${i}`} d={`M${18 + i * 106} 14v7`} />
        ))}
        {[0, 1, 2, 3].map((i) => (
          <path key={`l${i}`} d={`M14 ${52 + i * 106}h7`} />
        ))}
      </g>

      {/* Structural pathways */}
      <g stroke="var(--line)" strokeWidth="1" fill="none">
        {SPINE.map(([a, b]) => (
          <path key={`${a}${b}`} d={`M${byId[a].x},${byId[a].y} L${byId[b].x},${byId[b].y}`} />
        ))}
      </g>

      {/* The traced route, drawn in once on load */}
      <path
        d={routePath}
        fill="none"
        stroke="var(--gold)"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.85"
        style={{
          strokeDasharray: 520,
          strokeDashoffset: 520,
          animation: 'circe-draw 2.4s .35s ease-out forwards',
        }}
      />

      {/* Nodes */}
      <g>
        {NODES.map((n) => {
          const onRoute = ROUTE.includes(n.id)
          return (
            <g key={n.id}>
              {onRoute && (
                <circle
                  cx={n.x}
                  cy={n.y}
                  r={n.r + 5}
                  fill="none"
                  stroke="var(--gold)"
                  strokeWidth="0.6"
                  opacity="0.32"
                />
              )}
              <circle cx={n.x} cy={n.y} r={n.r} fill="var(--void)" />
              <circle
                cx={n.x}
                cy={n.y}
                r={n.r}
                fill="none"
                stroke={onRoute ? 'var(--gold)' : 'var(--ink-4)'}
                strokeWidth="1.1"
              />
              {n.label && (
                <text
                  x={n.x + n.r + 9}
                  y={n.y + 3.5}
                  fill="var(--ink-3)"
                  fontSize="9"
                  fontFamily="var(--font-mono)"
                  letterSpacing="0.14em"
                >
                  {n.label}
                </text>
              )}
            </g>
          )
        })}
      </g>

      {/* One node carries the hazard — the only warm colour on the page */}
      <g>
        <circle
          cx={byId.n3.x}
          cy={byId.n3.y}
          r="13"
          fill="none"
          stroke="var(--ember)"
          strokeWidth="0.7"
          opacity="0.4"
          style={{ animation: 'circe-pulse 3.6s ease-in-out infinite' }}
        />
        <circle cx={byId.n3.x} cy={byId.n3.y} r="2" fill="var(--ember)" />
      </g>

      {/* Bearing readout */}
      <text
        x="18"
        y="404"
        fill="var(--ink-4)"
        fontSize="9"
        fontFamily="var(--font-mono)"
        letterSpacing="0.16em"
      >
        8 MODULES · 10 PATHWAYS · 1 ROUTE TRACED
      </text>
    </svg>
  )
}
