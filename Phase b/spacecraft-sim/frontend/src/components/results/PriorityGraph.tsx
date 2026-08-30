import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import type { SpacecraftScenario } from '../../types/scenario'

interface Props {
  result: ActionSimulationResult
  action?: ActionSpec
  scenario: SpacecraftScenario
}

interface PriorityRow {
  id: string
  name: string
  kind: 'CREW' | 'EQUIPMENT'
  score: number
  rank: number | null
  reasons: string[]
  waiting?: string | null
  capacityDenied?: boolean
}

const reasonLabel = (reason: string) => reason.replaceAll('_', ' ')

export default function PriorityGraph({ result, action, scenario }: Props) {
  const crewNames = Object.fromEntries(
    Object.values(scenario.modules).flatMap((module) =>
      module.crew.map((crew) => [crew.id, crew.name])
    )
  )
  const crewRows: PriorityRow[] = Object.entries(result.crew.byCrewMember ?? {}).map(
    ([id, outcome]) => ({
      id,
      name: crewNames[id] ?? id,
      kind: 'CREW',
      score: outcome.priorityScore,
      rank: outcome.priorityRank ?? null,
      reasons: outcome.priorityReasons,
      waiting: outcome.waitingForConnectionId,
      capacityDenied: outcome.escapeCapacityDenied,
    })
  )
  const equipmentRows: PriorityRow[] = Object.entries(
    result.equipment.byEquipmentId
  )
    .filter(([, outcome]) => outcome.portable)
    .map(([id, outcome]) => ({
      id,
      name: outcome.name,
      kind: 'EQUIPMENT',
      score: outcome.priorityScore,
      rank: outcome.priorityRank ?? null,
      reasons: outcome.priorityReasons,
    }))
  const rows = [...crewRows, ...equipmentRows].sort(
    (a, b) =>
      (a.kind === b.kind ? 0 : a.kind === 'CREW' ? -1 : 1) ||
      (a.rank ?? 999) - (b.rank ?? 999) ||
      b.score - a.score
  )
  const bottlenecks = Object.entries(result.connectivity.byConnectionId)
    .sort(([, a], [, b]) => a.connectivity - b.connectivity)
    .slice(0, 3)

  return (
    <section
      aria-label="Evacuation passage priority graph"
      style={{
        background: 'var(--surface)',
        border: '1px solid var(--line)',
        borderRadius: 4,
        marginBottom: 18,
        padding: '14px 16px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12 }}>
        <span className="circe-label" style={{ color: 'var(--ink-2)' }}>
          EVACUATION PASSAGE PRIORITY
        </span>
        <span className="mono" style={{ color: 'var(--ink-4)', fontSize: 9 }}>
          {action?.label ?? result.actionId} · CREW CAPACITY IS ALLOCATED BEFORE PORTABLE EQUIPMENT
        </span>
      </div>

      {rows.length === 0 ? (
        <div style={{ color: 'var(--ink-4)', fontSize: 11 }}>No crew or portable equipment to rank.</div>
      ) : (
        <div style={{ display: 'grid', gap: 7 }}>
          {rows.map((row) => {
            const color = row.kind === 'CREW' ? '#d7b35a' : '#62a6d9'
            return (
              <div key={`${row.kind}-${row.id}`} style={{ display: 'grid', gridTemplateColumns: '180px minmax(120px, 1fr) 44px', gap: 10, alignItems: 'center' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ color: 'var(--ink)', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    <span className="mono" style={{ color, fontSize: 9, marginRight: 7 }}>
                      {row.rank ? `#${row.rank}` : '—'} {row.kind}
                    </span>
                    {row.name}
                  </div>
                  <div title={row.reasons.map(reasonLabel).join(' · ')} style={{ color: 'var(--ink-4)', fontSize: 9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {row.capacityDenied ? 'REFUGE CAPACITY DENIED · ' : row.waiting ? `waiting at ${row.waiting} · ` : ''}
                    {row.reasons.map(reasonLabel).join(' · ')}
                  </div>
                </div>
                <div style={{ height: 8, background: 'var(--surface-3)', borderRadius: 8, overflow: 'hidden' }}>
                  <div style={{ width: `${Math.max(1, row.score)}%`, height: '100%', background: color, boxShadow: `0 0 9px ${color}66`, transition: 'width .35s ease' }} />
                </div>
                <span className="mono" style={{ color, fontSize: 10, textAlign: 'right' }}>{row.score.toFixed(1)}</span>
              </div>
            )
          })}
        </div>
      )}

      {bottlenecks.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--line)' }}>
          <span className="mono" style={{ color: 'var(--ink-4)', fontSize: 9 }}>HATCH BOTTLENECKS</span>
          {bottlenecks.map(([id, value]) => (
            <span key={id} className="mono" style={{ color: value.connectivity < 50 ? 'var(--ember)' : 'var(--ink-3)', fontSize: 9 }}>
              {id} {value.connectivity.toFixed(0)}/100 · {value.crewThroughputPerMin.toFixed(2)} crew/min · {value.airThroughputPercentPerMin.toFixed(1)}% air/min · PWR {value.powerTransferPercent.toFixed(0)}%
            </span>
          ))}
        </div>
      )}
      <div style={{ color: 'var(--ink-4)', fontSize: 9, marginTop: 9, lineHeight: 1.5 }}>
        Scores combine immediate exposure, modeled survival risk, and preservation of non-redundant mission functions. They schedule a constrained passage; they do not assign human worth.
      </div>
    </section>
  )
}
