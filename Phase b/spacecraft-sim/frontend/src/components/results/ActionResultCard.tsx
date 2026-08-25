/**
 * ActionResultCard — displays one action's simulation outcome.
 *
 * Uses sample-count wording ("824 / 1000 sampled scenarios") never probability language.
 * Never shows "BEST ACTION". Per-metric relative labels ("Strongest containment") are OK.
 */

import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import type { SpacecraftScenario } from '../../types/scenario'

interface Props {
  result: ActionSimulationResult
  action: ActionSpec
  scenario: SpacecraftScenario
  allResults: ActionSimulationResult[]
  isSelected: boolean
  onSelect: () => void
}

const CAPABILITY_LABELS: Record<string, string> = {
  habitation: 'Habitation',
  oxygen_supply: 'O₂ Supply',
  co2_removal: 'CO₂ Removal',
  electrical_power: 'Electrical Power',
  thermal_control: 'Thermal Control',
  main_propulsion: 'Main Propulsion',
  attitude_control: 'Attitude Control',
  return_capability: 'Return Capability',
  communications: 'Communications',
  fire_suppression: 'Fire Suppression',
  emergency_life_support: 'Emergency Life Support',
  rcs: 'RCS',
  navigation: 'Navigation',
  docking: 'Docking',
}

function CapabilityPill({ status }: { status: string }) {
  const colors = {
    available: { bg: '#14532d', color: '#86efac', border: '#22c55e' },
    degraded: { bg: '#451a03', color: '#fed7aa', border: '#f59e0b' },
    unavailable: { bg: '#450a0a', color: '#fca5a5', border: '#ef4444' },
  }
  const c = colors[status as keyof typeof colors] ?? colors.degraded
  return (
    <span
      style={{
        background: c.bg,
        color: c.color,
        border: `1px solid ${c.border}`,
        borderRadius: 3,
        padding: '1px 6px',
        fontSize: 10,
        fontWeight: 600,
        letterSpacing: '0.04em',
      }}
    >
      {status.toUpperCase()}
    </span>
  )
}

export default function ActionResultCard({
  result,
  action,
  allResults,
  isSelected,
  onSelect,
}: Props) {
  const total = result.crew.totalScenarios

  // Determine per-metric "best" labels
  const allContainment = allResults.map((r) => r.hazard.containedInNScenarios)
  const allEvacuated = allResults.map((r) => r.crew.allEvacuatedCount)
  const allTrapped = allResults.map((r) => r.crew.anyTrappedCount)

  const bestContainment = Math.max(...allContainment) === result.hazard.containedInNScenarios
  const bestEvacuated = Math.max(...allEvacuated) === result.crew.allEvacuatedCount
  const fewestTrapped = Math.min(...allTrapped) === result.crew.anyTrappedCount

  const isIsolation = action.operations.some((op) => op.type === 'isolate_module')
  const isDoNothing = action.operations.some((op) => op.type === 'do_nothing')

  const capabilities = result.capabilities.byCapability

  const badgeStyle: React.CSSProperties = {
    background: '#1e3a5f',
    color: '#93c5fd',
    border: '1px solid #3b82f6',
    borderRadius: 3,
    padding: '1px 7px',
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: '0.04em',
  }

  return (
    <div
      onClick={onSelect}
      style={{
        background: isSelected ? '#1a2540' : '#1e2128',
        border: `2px solid ${isSelected ? '#3b82f6' : '#2a2d36'}`,
        borderRadius: 10,
        padding: 18,
        minWidth: 260,
        maxWidth: 300,
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      {/* Action label */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: '#e2e8f0', fontWeight: 700, fontSize: 14, marginBottom: 2 }}>
          {action.label}
        </div>
        <div style={{ color: '#64748b', fontSize: 11, lineHeight: 1.4 }}>
          {action.description}
        </div>
      </div>

      {/* ── HAZARD ── */}
      <Section title="HAZARD">
        <Row
          label="Modules reached"
          value={`${result.hazard.modulesReached}`}
          badge={bestContainment ? 'Strongest containment' : undefined}
          badgeStyle={badgeStyle}
        />
        <Row
          label="Contained"
          value={`${result.hazard.containedInNScenarios} / ${total} sampled scenarios`}
        />
      </Section>

      {/* ── CREW ── */}
      <Section title="CREW">
        <Row
          label="All evacuated"
          value={`${result.crew.allEvacuatedCount} / ${total} sampled scenarios`}
          badge={bestEvacuated ? 'Best evacuation' : undefined}
          badgeStyle={badgeStyle}
        />
        <Row
          label="Any trapped"
          value={`${result.crew.anyTrappedCount} / ${total} sampled scenarios`}
          badge={fewestTrapped ? 'Fewest trapped' : undefined}
          badgeStyle={badgeStyle}
          valueColor={result.crew.anyTrappedCount === 0 ? '#22c55e' : undefined}
        />
      </Section>

      {/* ── CAPABILITIES ── */}
      {Object.keys(capabilities).length > 0 && (
        <Section title="CAPABILITIES">
          {Object.entries(capabilities).map(([cap, status]) => (
            <div
              key={cap}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 4,
              }}
            >
              <span style={{ color: '#94a3b8', fontSize: 12 }}>
                {CAPABILITY_LABELS[cap] ?? cap}
              </span>
              <CapabilityPill status={status} />
            </div>
          ))}
        </Section>
      )}

      {/* ── CRITICAL FUNCTIONS ── */}
      {Object.keys(result.criticalFunctions.byFunction).length > 0 && (
        <Section title="CRITICAL FUNCTIONS">
          {Object.entries(result.criticalFunctions.byFunction).map(([fn, entry]) => (
            <div
              key={fn}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}
            >
              <span style={{ color: '#94a3b8', fontSize: 12 }}>{fn}</span>
              <span
                style={{
                  color:
                    entry.status === 'nominal'
                      ? '#22c55e'
                      : entry.status === 'single_provider'
                      ? '#f59e0b'
                      : '#ef4444',
                  fontSize: 11,
                  fontWeight: 600,
                }}
              >
                {entry.providersAvailable}/{entry.totalProviders}
              </span>
            </div>
          ))}
        </Section>
      )}

      {/* Trade-off note for isolation */}
      {isIsolation && (
        <div
          style={{
            background: '#451a03',
            border: '1px solid #7c2d12',
            borderRadius: 4,
            padding: '6px 10px',
            fontSize: 11,
            color: '#fed7aa',
            marginTop: 10,
          }}
        >
          ⚠ All equipment inside isolated module becomes unavailable
        </div>
      )}

      {/* Do-nothing note */}
      {isDoNothing && (
        <div
          style={{
            background: '#1a1d24',
            border: '1px solid #374151',
            borderRadius: 4,
            padding: '6px 10px',
            fontSize: 11,
            color: '#94a3b8',
            marginTop: 10,
          }}
        >
          Baseline: no intervention, hazard pathways remain open
        </div>
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          color: '#475569',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.08em',
          marginBottom: 6,
          borderBottom: '1px solid #1e2028',
          paddingBottom: 3,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  )
}

function Row({
  label,
  value,
  badge,
  badgeStyle,
  valueColor,
}: {
  label: string
  value: string
  badge?: string
  badgeStyle?: React.CSSProperties
  valueColor?: string
}) {
  return (
    <div style={{ marginBottom: 5 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
        <span style={{ color: '#94a3b8', fontSize: 12, flexShrink: 0 }}>{label}</span>
        <span style={{ color: valueColor ?? '#e2e8f0', fontSize: 12, textAlign: 'right' }}>{value}</span>
      </div>
      {badge && (
        <div style={{ marginTop: 2 }}>
          <span style={badgeStyle}>{badge}</span>
        </div>
      )}
    </div>
  )
}
