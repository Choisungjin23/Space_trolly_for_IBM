/**
 * Readouts for the results views.
 *
 * Counts out of sampled scenarios are ratios against a limit, so they are drawn
 * as meters: a filled bar on a lighter step of the same hue. Sample counts are
 * never phrased as probabilities.
 *
 * The status vocabulary these render lives in `statusLook.ts`.
 */

import { ratioRamp, type StatusLook } from './statusLook'

export function StatusPill({ status }: { status: StatusLook }) {
  return (
    <span
      style={{
        background: status.bg,
        color: status.color,
        border: `1px solid ${status.border}`,
        borderRadius: 3,
        padding: '3px 8px',
        fontSize: 10.5,
        fontWeight: 600,
        letterSpacing: '.06em',
        whiteSpace: 'nowrap',
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
      }}
    >
      <span aria-hidden style={{ fontSize: 10 }}>
        {status.icon}
      </span>
      {status.label}
    </span>
  )
}

// ── Stat tile ──────────────────────────────────────────────

/**
 * A headline count with its scale underneath. `of` is the denominator when the
 * value is a share of sampled scenarios; omit it for a plain count.
 */
export function StatTile({
  label,
  value,
  of,
  unit,
  higherIsBetter = true,
  badge,
  emphasis = true,
}: {
  label: string
  value: number
  of?: number
  unit?: string
  higherIsBetter?: boolean
  badge?: string
  emphasis?: boolean
}) {
  const ratio = of && of > 0 ? value / of : null
  const ramp = ratio === null ? null : ratioRamp(ratio, higherIsBetter)

  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          color: 'var(--ink-2)',
          fontSize: 12.5,
          fontWeight: 500,
          letterSpacing: '.01em',
          marginBottom: 4,
        }}
      >
        {label}
      </div>

      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span
          style={{
            // Proportional figures: tabular-nums looks loose at display sizes.
            color: ramp ? ramp.ink : 'var(--ink)',
            fontSize: emphasis ? 30 : 20,
            fontWeight: 700,
            lineHeight: 1.05,
          }}
        >
          {value}
        </span>
        {of !== undefined && (
          <span style={{ color: 'var(--ink-2)', fontSize: 15, fontWeight: 500 }}>
            / {of}
          </span>
        )}
        {unit && (
          <span style={{ color: 'var(--ink-2)', fontSize: 12.5 }}>{unit}</span>
        )}
      </div>

      {ramp && (
        <>
          <Meter ratio={ratio!} fill={ramp.fill} track={ramp.track} />
          <div
            style={{
              color: 'var(--ink-3)',
              fontSize: 11.5,
              marginTop: 5,
              letterSpacing: '.02em',
            }}
          >
            sampled scenarios
          </div>
        </>
      )}

      {badge && (
        <div style={{ marginTop: 5 }}>
          <span
            style={{
              background: 'var(--gold-wash)',
              color: 'var(--gold-bright)',
              border: '1px solid var(--gold-dim)',
              borderRadius: 3,
              padding: '3px 9px',
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '.05em',
            }}
          >
            {badge}
          </span>
        </div>
      )}
    </div>
  )
}

export function Meter({
  ratio,
  fill,
  track,
  height = 9,
}: {
  ratio: number
  fill: string
  track: string
  height?: number
}) {
  return (
    <div
      style={{
        marginTop: 5,
        height,
        background: track,
        borderRadius: height / 2,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: `${Math.max(0, Math.min(1, ratio)) * 100}%`,
          height: '100%',
          background: fill,
          borderRadius: height / 2,
          transition: 'width 0.25s ease',
        }}
      />
    </div>
  )
}

// ── Sparkline ───────────────────────────────────────────────────────────────

/**
 * Severity over time for one module. One de-emphasis hue for the whole series;
 * only the current step is accented, so scrubbing reads as movement along a
 * fixed line rather than a colour change.
 */
export function Sparkline({
  values,
  currentIndex,
  accent,
  width = 132,
  height = 34,
}: {
  values: number[]
  currentIndex: number
  accent: string
  width?: number
  height?: number
}) {
  if (values.length < 2) return null

  const pad = 4
  const w = width - pad * 2
  const h = height - pad * 2
  const max = Math.max(0.001, ...values)

  const x = (i: number) => pad + (i / (values.length - 1)) * w
  const y = (v: number) => pad + h - (v / max) * h

  const line = values.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ')
  const area = `${line} L${x(values.length - 1)},${pad + h} L${x(0)},${pad + h} Z`
  const cx = x(currentIndex)
  const cy = y(values[currentIndex] ?? 0)

  const first = values[0] ?? 0
  const now = values[currentIndex] ?? 0

  return (
    <svg
      width={width}
      height={height}
      style={{ display: 'block', overflow: 'visible' }}
      role="img"
      aria-label={
        `Severity across ${values.length} steps: ` +
        `${(first * 100).toFixed(0)}% at the start, ` +
        `${(now * 100).toFixed(0)}% now, ` +
        `peak ${(max * 100).toFixed(0)}%.`
      }
    >
      <path d={area} fill="var(--line)" opacity={0.45} />
      <path d={line} fill="none" stroke="var(--ink-3)" strokeWidth={2} strokeLinejoin="round" />
      {/* Progress to the current step, in the accent. */}
      <path
        d={values
          .slice(0, currentIndex + 1)
          .map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`)
          .join(' ')}
        fill="none"
        stroke={accent}
        strokeWidth={2}
        strokeLinejoin="round"
      />
      {/* Surface ring keeps the marker legible where it sits on the line. */}
      <circle cx={cx} cy={cy} r={5} fill="var(--surface-3)" />
      <circle cx={cx} cy={cy} r={3} fill={accent} />
    </svg>
  )
}
