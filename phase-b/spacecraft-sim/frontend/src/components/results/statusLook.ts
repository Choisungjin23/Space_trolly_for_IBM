/**
 * Status vocabulary shared by the results views.
 *
 * Kept apart from the components that render it: a module that exports both
 * components and plain values loses React fast refresh, and these tables are
 * imported from several places.
 *
 * The rule these encode: a status never speaks through colour alone. Green and
 * amber sit only ΔE 5.7 apart under protanopia, so every status ships an icon
 * and a word as well - the colour is the third channel, not the only one.
 */

export interface StatusLook {
  icon: string
  label: string
  color: string
  bg: string
  border: string
}

const GOOD = { color: 'var(--good)', bg: 'var(--good)', border: 'var(--good)' }
const WARN = { color: 'var(--amber)', bg: 'var(--amber-wash)', border: 'var(--amber)' }
const BAD = { color: 'var(--ember)', bg: 'var(--ember-wash)', border: 'var(--ember)' }
const IDLE = { color: 'var(--ink-2)', bg: 'var(--line)', border: 'var(--ink-3)' }

export const EQUIPMENT_LOOK: Record<string, StatusLook> = {
  operational: { icon: '✓', label: 'OPERATIONAL', ...GOOD },
  exposed_at_risk: { icon: '▲', label: 'AT RISK', ...WARN },
  unavailable: { icon: '◌', label: 'UNAVAILABLE', ...IDLE },
  explicitly_failed: { icon: '✕', label: 'FAILED', ...BAD },
}

export const CREW_LOOK: Record<string, StatusLook> = {
  safe: { icon: '✓', label: 'SAFE', ...GOOD },
  evacuated: { icon: '✓', label: 'EVACUATED', ...GOOD },
  evacuating: { icon: '→', label: 'EVACUATING', ...WARN },
  exposed: { icon: '▲', label: 'EXPOSED', ...WARN },
  trapped: { icon: '✕', label: 'TRAPPED', ...BAD },
}

export const CAPABILITY_LOOK: Record<string, StatusLook> = {
  available: { icon: '✓', label: 'AVAILABLE', ...GOOD },
  degraded: { icon: '▲', label: 'DEGRADED', ...WARN },
  unavailable: { icon: '✕', label: 'UNAVAILABLE', ...BAD },
}

export function look(table: Record<string, StatusLook>, key: string): StatusLook {
  return table[key] ?? { icon: '·', label: key.toUpperCase(), ...IDLE }
}

/** Severity ramp for a 0..1 ratio, plus the lighter track step of the same hue. */
export function ratioRamp(ratio: number, higherIsBetter: boolean) {
  const good = higherIsBetter ? ratio >= 0.99 : ratio <= 0.001
  const bad = higherIsBetter ? ratio < 0.5 : ratio > 0.5
  if (good) return { fill: 'var(--good)', track: 'var(--good)', ink: 'var(--good)' }
  if (bad) return { fill: 'var(--ember)', track: 'var(--ember-wash)', ink: 'var(--ember)' }
  return { fill: 'var(--amber)', track: 'var(--amber-wash)', ink: 'var(--amber)' }
}
