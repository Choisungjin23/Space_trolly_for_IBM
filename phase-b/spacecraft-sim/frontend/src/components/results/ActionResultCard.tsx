/**
 * ActionResultCard — displays one action's simulation outcome.
 *
 * Uses sample-count wording for Monte Carlo counts. Survival/return percentages
 * are separately labelled as assumed model estimates from the example run.
 * Never shows "BEST ACTION". Per-metric relative labels ("Strongest containment") are OK.
 *
 * Hazard and crew counts are the numbers an operator scans across cards, so
 * they lead as stat tiles with meters. Equipment and crew statuses carry an
 * icon and a word, never colour alone.
 */

import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import type { SpacecraftScenario } from '../../types/scenario'
import { StatTile, StatusPill } from './StatDisplay'
import {
  CAPABILITY_LOOK,
  CREW_LOOK,
  EQUIPMENT_LOOK,
  look,
} from './statusLook'

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

/**
 * The card's job is comparison across actions, so equipment is summarised as
 * counts and only outright losses are named. Naming every affected item would
 * make each card hundreds of pixels taller and stop the row scanning side by
 * side; the full per-item breakdown lives in the Timeline tab.
 */
const LOST_STATE = 'explicitly_failed'
const AFFECTED_STATES = ['explicitly_failed', 'exposed_at_risk', 'unavailable']

export default function ActionResultCard({
  result,
  action,
  scenario,
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
  const moduleCount = Object.keys(scenario.modules).length

  // Equipment: count every state, then name only the ones in trouble.
  const equipment = Object.entries(result.equipment?.byEquipmentId ?? {})
  const equipmentCounts = equipment.reduce<Record<string, number>>((acc, [, item]) => {
    acc[item.state] = (acc[item.state] ?? 0) + 1
    return acc
  }, {})
  const equipmentLost = equipment.filter(([, item]) => item.state === LOST_STATE)
  const affectedCount = equipment.filter(([, item]) =>
    AFFECTED_STATES.includes(item.state)
  ).length

  const crewMembers = Object.entries(result.crew.byCrewMember ?? {})
  const resourceModules = Object.entries(result.resources?.byModuleId ?? {})

  return (
    <div
      onClick={onSelect}
      style={{
        background: isSelected ? 'var(--surface-2)' : 'var(--surface)',
        border: `1px solid ${isSelected ? 'var(--gold)' : 'var(--line)'}`,
        borderRadius: 4,
        padding: 20,
        minWidth: 310,
        maxWidth: 344,
        cursor: 'pointer',
        flexShrink: 0,
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      {/* Action label */}
      <div style={{ marginBottom: 14 }}>
        <div
          style={{
            color: 'var(--ink)',
            fontWeight: 600,
            fontSize: 15,
            lineHeight: 1.35,
            marginBottom: 5,
          }}
        >
          {action.label}
        </div>
        <div style={{ color: 'var(--ink-2)', fontSize: 12, lineHeight: 1.55 }}>
          {action.description}
        </div>
      </div>

      {/* ── HAZARD ── */}
      <Section title="HAZARD">
        <StatTile
          label="Modules reached by smoke"
          value={result.hazard.modulesReached}
          unit={`of ${moduleCount} modules`}
        />
        <StatTile
          label="Contained to the affected module"
          value={result.hazard.containedInNScenarios}
          of={total}
          badge={bestContainment ? 'Strongest containment' : undefined}
        />
      </Section>

      {/* ── CREW ── */}
      <Section title="CREW">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 9 }}>
          <div style={{ background: 'var(--surface-2)', padding: '7px 8px', borderRadius: 4 }}>
            <SubTitle>EXPECTED SURVIVORS</SubTitle>
            <span style={{ color: 'var(--ink)', fontFamily: 'var(--font-mono)', fontSize: 17 }}>{result.expectedSurvivors.toFixed(2)}</span>
          </div>
          <div style={{ background: 'var(--surface-2)', padding: '7px 8px', borderRadius: 4 }}>
            <SubTitle>EXPECTED RETURNEES</SubTitle>
            <span style={{ color: 'var(--gold)', fontFamily: 'var(--font-mono)', fontSize: 17 }}>{result.expectedReturnees.toFixed(2)}</span>
          </div>
        </div>
        <StatTile
          label="All evacuated"
          value={result.crew.allEvacuatedCount}
          of={total}
          badge={bestEvacuated ? 'Best evacuation' : undefined}
        />
        <StatTile
          label="Any trapped"
          value={result.crew.anyTrappedCount}
          of={total}
          higherIsBetter={false}
          badge={fewestTrapped ? 'Fewest trapped' : undefined}
        />

        {crewMembers.length > 0 && (
          <div style={{ marginTop: 4 }}>
            <SubTitle>PER CREW MEMBER — example run</SubTitle>
            {crewMembers.map(([id, member]) => {
              const status = look(CREW_LOOK, member.status)
              return (
                <div
                  key={id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 8,
                    marginBottom: 4,
                  }}
                >
                  <span style={{ color: 'var(--ink)', fontSize: 12.5 }}>
                    {nameOfCrew(scenario, id)}
                    {member.exposureExampleSeconds > 0 && (
                      <span style={{ color: 'var(--amber)', fontSize: 11.5, marginLeft: 7 }}>
                        {member.exposureExampleSeconds}s exposed
                      </span>
                    )}
                  </span>
                  <StatusPill status={status} />
                  <span style={{ color: member.abandoned ? 'var(--ember)' : 'var(--ink-3)', fontFamily: 'var(--font-mono)', fontSize: 10, textAlign: 'right' }}>
                    S {(member.survivalProbability * 100).toFixed(1)}% · R {(member.returnProbability * 100).toFixed(1)}%
                    {member.estimatedSurvivalMinutes != null && (
                      <span style={{ display: 'block', color: member.estimatedSurvivalMinutes < 10 ? 'var(--ember)' : 'var(--amber)', marginTop: 2 }}>
                        ≈ {member.estimatedSurvivalMinutes.toFixed(1)} min to 1% · {member.resourceRiskReasons.join(', ')}
                      </span>
                    )}
                  </span>
                </div>
              )
            })}
          </div>
        )}
      </Section>

      {resourceModules.length > 0 && (
        <Section title="RESOURCE STATE — example run">
          {resourceModules.map(([moduleId, resource]) => (
            <div key={moduleId} style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, marginBottom: 5, fontSize: 10.5 }}>
              <span style={{ color: 'var(--ink-2)' }}>{scenario.modules[moduleId]?.name ?? moduleId}</span>
              <span style={{ fontFamily: 'var(--font-mono)', color: resource.powerSufficient && resource.waterSufficient ? 'var(--ink-3)' : 'var(--ember)' }}>
                <span style={{ color: '#facc15' }}>{resource.powerLevelW.toFixed(0)}W</span>
                {' · '}<span style={{ color: '#7dd3fc' }}>{resource.airLevelPercent.toFixed(1)}%</span>
                {' · '}<span style={{ color: '#60a5fa' }}>{resource.waterStoredKg.toFixed(2)}kg</span>
              </span>
            </div>
          ))}
        </Section>
      )}

      {/* ── EQUIPMENT ── */}
      {equipment.length > 0 && (
        <Section title={`EQUIPMENT — ${affectedCount} of ${equipment.length} affected`}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
            {['explicitly_failed', 'exposed_at_risk', 'unavailable', 'operational']
              .filter((state) => equipmentCounts[state])
              .map((state) => {
                const status = look(EQUIPMENT_LOOK, state)
                return (
                  <span
                    key={state}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 5,
                      background: status.bg,
                      border: `1px solid ${status.border}`,
                      borderRadius: 5,
                      padding: '3px 8px',
                    }}
                  >
                    <span style={{ color: status.color, fontSize: 15, fontWeight: 700 }}>
                      {equipmentCounts[state]}
                    </span>
                    <span
                      style={{
                        color: status.color,
                        fontSize: 9,
                        fontWeight: 700,
                        letterSpacing: '0.04em',
                      }}
                    >
                      {status.icon} {status.label}
                    </span>
                  </span>
                )
              })}
          </div>

          {equipmentLost.map(([id, item]) => {
            const status = look(EQUIPMENT_LOOK, item.state)
            return (
              <div
                key={id}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 4,
                }}
              >
                <span style={{ color: 'var(--ink)', fontSize: 12.5 }}>{item.name}</span>
                <StatusPill status={status} />
              </div>
            )
          })}
        </Section>
      )}

      {/* ── CAPABILITIES ── */}
      {Object.keys(capabilities).length > 0 && (
        <Section title="CAPABILITIES">
          {Object.entries(capabilities).map(([cap, state]) => (
            <div
              key={cap}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                gap: 8,
                marginBottom: 4,
              }}
            >
              <span style={{ color: 'var(--ink)', fontSize: 12.5 }}>
                {CAPABILITY_LABELS[cap] ?? cap}
              </span>
              <StatusPill status={look(CAPABILITY_LOOK, state)} />
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
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 4,
              }}
            >
              <span style={{ color: 'var(--ink)', fontSize: 12.5 }}>{fn}</span>
              <span
                style={{
                  color:
                    entry.status === 'nominal'
                      ? 'var(--good)'
                      : entry.status === 'single_provider'
                      ? 'var(--amber)'
                      : 'var(--ember)',
                  fontSize: 12,
                  fontWeight: 700,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {entry.status === 'nominal'
                  ? '✓'
                  : entry.status === 'single_provider'
                  ? '▲'
                  : '✕'}{' '}
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
            background: 'var(--amber-wash)',
            border: '1px solid var(--amber)',
            borderRadius: 4,
            padding: '6px 10px',
            fontSize: 12,
            color: 'var(--amber)',
            marginTop: 12,
            lineHeight: 1.55,
          }}
        >
          All equipment inside an isolated module becomes unavailable
        </div>
      )}

      {/* Do-nothing note */}
      {isDoNothing && (
        <div
          style={{
            background: 'var(--surface-2)',
            border: '1px solid var(--line)',
            borderRadius: 4,
            padding: '6px 10px',
            fontSize: 12,
            color: 'var(--ink-2)',
            marginTop: 12,
            lineHeight: 1.55,
          }}
        >
          Baseline: no intervention, hazard pathways remain open
        </div>
      )}
    </div>
  )
}

/** Crew ids are opaque; show the name the builder gave them when we have it. */
function nameOfCrew(scenario: SpacecraftScenario, crewId: string): string {
  for (const mod of Object.values(scenario.modules)) {
    const found = mod.crew.find((c) => c.id === crewId)
    if (found) return found.name
  }
  return crewId
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div
        style={{
          color: 'var(--ink-2)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          fontWeight: 500,
          letterSpacing: '.16em',
          marginBottom: 10,
          borderBottom: '1px solid var(--line)',
          paddingBottom: 6,
        }}
      >
        {title}
      </div>
      {children}
    </div>
  )
}

function SubTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        color: 'var(--ink-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
        fontWeight: 500,
        letterSpacing: '.12em',
        margin: '10px 0 6px',
      }}
    >
      {children}
    </div>
  )
}
