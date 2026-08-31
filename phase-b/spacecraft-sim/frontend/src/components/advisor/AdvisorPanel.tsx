/**
 * AdvisorPanel — the Phase C multi-agent layer.
 *
 * This is the only place in the product where an action is recommended. The
 * comparison table stays recommendation-free by design; here the coordinator
 * advises, the critic argues back, and the operator decides.
 */

import { useEffect, useState } from 'react'
import {
  analyzeWithProgress,
  fetchAdvisorStatus,
  type RunProgress,
} from '../../api/simulatorClient'
import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import { StatusPill } from '../results/StatDisplay'
import { IconAdvisory } from '../shared/Icons'
import EthicalAssessmentCard from './EthicalAssessmentCard'
import {
  CREW_LOOK,
  EQUIPMENT_LOOK,
  look,
  type StatusLook,
} from '../results/statusLook'
import type {
  AdvisorStatus,
  AgentFinding,
  Claim,
  DecisionPackage,
  Severity,
} from '../../types/advisor'

interface Props {
  scenario: unknown
  emergency: unknown
  focusActionId?: string | null
  /** Simulated outcomes, so the recommendation can show what it costs. */
  results?: ActionSimulationResult[]
  actions?: ActionSpec[]
}

const AGENT_LABELS: Record<string, string> = {
  hazard: 'Hazard',
  crew_safety: 'Crew Safety',
  systems: 'Systems',
  mission: 'Mission',
}

const BASIS_COLOR: Record<string, string> = {
  SIMULATION_FACT: 'var(--good)',
  EVIDENCE: 'var(--gold)',
  INFERENCE: 'var(--amber)',
  ASSUMPTION: 'var(--gold)',
}

const SEVERITY_COLOR: Record<Severity, string> = {
  BLOCKER: 'var(--ember)',
  MAJOR: 'var(--amber)',
  MINOR: 'var(--ink-3)',
}

const card: React.CSSProperties = {
  background: 'var(--surface-2)',
  border: '1px solid var(--line)',
  borderRadius: 8,
  padding: '14px 16px',
}

function ClaimRow({ claim }: { claim: Claim }) {
  return (
    <li style={{ marginBottom: 8, lineHeight: 1.55 }}>
      <span
        style={{
          display: 'inline-block',
          fontSize: 9,
          letterSpacing: '0.06em',
          padding: '1px 6px',
          borderRadius: 3,
          marginRight: 8,
          color: BASIS_COLOR[claim.basis] ?? 'var(--ink-2)',
          border: `1px solid ${BASIS_COLOR[claim.basis] ?? 'var(--ink-2)'}`,
        }}
      >
        {claim.basis.replace('_', ' ')}
      </span>
      <span style={{ color: 'var(--ink-2)', fontSize: 13 }}>{claim.statement}</span>
      {claim.refs.length > 0 && (
        <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 2, marginLeft: 2 }}>
          traced to {claim.refs.join(', ')}
        </div>
      )}
    </li>
  )
}

function FindingCard({ finding }: { finding: AgentFinding }) {
  return (
    <div style={card}>
      <h4 style={{ margin: '0 0 10px', fontSize: 13, color: 'var(--ink)' }}>
        {AGENT_LABELS[finding.agent] ?? finding.agent}
      </h4>
      {finding.claims.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {finding.claims.map((claim, i) => (
            <ClaimRow key={i} claim={claim} />
          ))}
        </ul>
      ) : (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-3)' }}>No claims returned.</p>
      )}
      {finding.concerns.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: 'var(--amber)', letterSpacing: '0.06em' }}>
            CONCERNS
          </div>
          <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 12, color: 'var(--ink-2)' }}>
            {finding.concerns.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function AdvisorPanel({
  scenario,
  emergency,
  focusActionId,
  results,
  actions,
}: Props) {
  const [status, setStatus] = useState<AdvisorStatus | null>(null)
  const [pkg, setPkg] = useState<DecisionPackage | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState<RunProgress | null>(null)

  useEffect(() => {
    fetchAdvisorStatus()
      .then(setStatus)
      .catch((e) => setStatus({ available: false, detail: String(e) }))
  }, [])

  async function run() {
    setBusy(true)
    setError(null)
    setProgress(null)
    try {
      setPkg(
        await analyzeWithProgress(
          {
            scenario,
            emergency,
            focusActionId: focusActionId ?? null,
            samples: 20,
            seed: 42,
          },
          setProgress,
        ),
      )
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const violations = pkg?.critic.grounding_violations ?? []

  // Phase C names actions the engine's way; the results table names them Phase
  // B's way. The backend ships the mapping so the two can be lined up here.
  const recommendedId = pkg?.recommendation?.recommended_action_id
  const phaseBId = recommendedId
    ? ((pkg?.provenance as Record<string, Record<string, string>> | undefined)
        ?.action_id_map?.[recommendedId] ?? recommendedId)
    : undefined
  const outcome = results?.find((r) => r.actionId === phaseBId)
  const recommendedLabel =
    actions?.find((a) => a.id === phaseBId)?.label ?? recommendedId ?? ''

  // Equipment the action destroys or takes offline, and crew who do not come
  // through clean. Read from the simulation, so they hold even where an
  // agent's wording is disputed.
  const lostEquipment = Object.entries(outcome?.equipment?.byEquipmentId ?? {}).filter(
    ([, item]) => item.state === 'explicitly_failed' || item.state === 'unavailable',
  )
  const atRiskCrew = Object.entries(outcome?.crew.byCrewMember ?? {}).filter(
    ([, member]) => member.status !== 'safe' || member.exposureExampleSeconds > 0,
  )

  function crewName(crewId: string): string {
    const modules = (scenario as { modules?: Record<string, { crew?: { id: string; name: string }[] }> })
      ?.modules
    for (const module of Object.values(modules ?? {})) {
      const found = module.crew?.find((c) => c.id === crewId)
      if (found) return found.name
    }
    return crewId
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ ...card, borderLeft: '2px solid var(--gold)' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 9,
            color: 'var(--gold)',
          }}
        >
          <IconAdvisory size={15} />
          <span className="circe-label" style={{ color: 'var(--gold)' }}>
            MISSION CONTROL ADVISORY
          </span>
        </div>
        <p
          style={{
            margin: '10px 0 0',
            fontSize: 13.5,
            color: 'var(--ink-2)',
            lineHeight: 1.75,
            maxWidth: '62ch',
          }}
        >
          A deterministic human-preservation policy ranks the Phase A outcomes. Seven
          agents then explain the result: four specialists, a NASA evidence retriever,
          a red-team critic, and a coordinator. Every number they state is
          machine-checked against the simulation.
        </p>
        <div style={{ marginTop: 20, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={run}
            disabled={busy || (status !== null && !status.available)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              padding: '14px 30px',
              borderRadius: 3,
              border: 'none',
              cursor: busy ? 'wait' : 'pointer',
              // Filled, not outlined: this is the decision the panel exists for.
              background:
                status?.available === false
                  ? 'var(--surface-3)'
                  : 'linear-gradient(180deg, var(--gold-bright) 0%, var(--gold) 100%)',
              color: status?.available === false ? 'var(--ink-4)' : '#181205',
              fontFamily: 'var(--font-mono)',
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: '.2em',
              boxShadow:
                status?.available === false
                  ? 'none'
                  : '0 2px 18px rgba(194,161,91,.28)',
              transition: 'filter .16s, box-shadow .16s',
            }}
            onMouseEnter={(e) => {
              if (status?.available !== false && !busy) {
                e.currentTarget.style.filter = 'brightness(1.08)'
                e.currentTarget.style.boxShadow = '0 3px 26px rgba(194,161,91,.42)'
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.filter = 'none'
              e.currentTarget.style.boxShadow =
                status?.available === false ? 'none' : '0 2px 18px rgba(194,161,91,.28)'
            }}
          >
            <IconAdvisory size={15} />
            {busy ? 'CIRCE IS DELIBERATING…' : 'CONSULT CIRCE'}
          </button>
          {status && !status.available && (
            <span style={{ fontSize: 11.5, color: 'var(--amber)' }}>
              {status.detail}
            </span>
          )}
        </div>

        {busy && (
          <div style={{ marginTop: 14 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                marginBottom: 6,
              }}
            >
              <span style={{ color: 'var(--ink)', fontSize: 12.5 }}>
                {progress ? progress.label : 'Starting the pipeline'}
              </span>
              <span className="mono" style={{ color: 'var(--gold)', fontSize: 12 }}>
                {progress ? `${progress.percent}%` : ''}
              </span>
            </div>

            <div
              style={{
                height: 2,
                background: 'var(--line)',
                overflow: 'hidden',
              }}
            >
              <div
                style={{
                  width: `${progress?.percent ?? 0}%`,
                  height: '100%',
                  background: 'var(--gold)',
                  transition: 'width .3s ease',
                }}
              />
            </div>

            <div
              className="mono"
              style={{ color: 'var(--ink-3)', fontSize: 10.5, marginTop: 7, letterSpacing: '.08em' }}
            >
              {progress
                ? `Stage ${Math.min(progress.done + 1, progress.total)} of ${progress.total}`
                : 'Running the simulation the agents will read'}
            </div>
          </div>
        )}
      </div>

      {error && (
        <div style={{ ...card, borderLeft: '3px solid var(--ember)', color: 'var(--ember)', fontSize: 12 }}>
          {error}
        </div>
      )}

      {pkg && (
        <>
          {pkg.ethical_assessment && (
            <EthicalAssessmentCard assessment={pkg.ethical_assessment} />
          )}

          {pkg.recommendation && (
            <div
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--line)',
                borderLeft: '2px solid var(--gold)',
                borderRadius: 3,
                padding: '24px 28px',
              }}
            >
              <div
                style={{
                  fontSize: 10,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--gold)',
                  letterSpacing: '.2em',
                  fontWeight: 500,
                }}
              >
                FINAL COORDINATOR
              </div>

              <h3
                style={{
                  margin: '12px 0 6px',
                  fontSize: 30,
                  lineHeight: 1.2,
                  color: 'var(--ink)',
                  fontWeight: 400,
                  fontFamily: 'var(--font-display)',
                  letterSpacing: '.01em',
                }}
              >
                {recommendedLabel}
              </h3>
              <code style={{ fontSize: 11, color: 'var(--ink-4)', fontFamily: 'var(--font-mono)' }}>
                {pkg.recommendation.recommended_action_id}
              </code>

              {pkg.recommendation.policy_override_applied && (
                <div
                  style={{
                    marginTop: 13,
                    padding: '9px 12px',
                    border: '1px solid var(--amber)',
                    color: 'var(--amber)',
                    fontSize: 11.5,
                  }}
                >
                  The language model proposed{' '}
                  <code>{pkg.recommendation.model_proposed_action_id}</code>; the
                  deterministic policy enforced this action. The mismatch remains in
                  the audit trail.
                </div>
              )}

              {/* Consequences come from the simulation, not from anything an
                  agent wrote, so they stand even where a claim is disputed. */}
              {outcome && (
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(152px, 1fr))',
                    gap: 12,
                    margin: '18px 0 0',
                  }}
                >
                  <Consequence
                    label="Crew trapped"
                    value={outcome.crew.anyTrappedCount}
                    of={outcome.crew.totalScenarios}
                    bad={outcome.crew.anyTrappedCount > 0}
                  />
                  <Consequence
                    label="All evacuated"
                    value={outcome.crew.allEvacuatedCount}
                    of={outcome.crew.totalScenarios}
                    bad={outcome.crew.allEvacuatedCount < outcome.crew.totalScenarios}
                  />
                  <Consequence
                    label="Equipment lost"
                    value={lostEquipment.length}
                    of={Object.keys(outcome.equipment?.byEquipmentId ?? {}).length}
                    bad={lostEquipment.length > 0}
                  />
                  <Consequence
                    label="Modules reached"
                    value={outcome.hazard.modulesReached}
                    bad={outcome.hazard.modulesReached > 1}
                  />
                </div>
              )}

              {(lostEquipment.length > 0 || atRiskCrew.length > 0) && (
                <div
                  style={{
                    background: 'var(--ember-wash)',
                    border: '1px solid var(--ember)33',
                    borderRadius: 3,
                    padding: '15px 17px',
                    marginTop: 18,
                  }}
                >
                  <div
                    style={{
                      fontSize: 10,
                      fontFamily: 'var(--font-mono)',
                      color: 'var(--ember)',
                      letterSpacing: '.18em',
                      fontWeight: 500,
                      marginBottom: 12,
                    }}
                  >
                    WHAT THIS ACTION COSTS
                  </div>

                  {atRiskCrew.length > 0 && (
                    <LossList
                      title="Crew at risk"
                      items={atRiskCrew.map(([id, member]) => ({
                        key: id,
                        name: crewName(id),
                        note:
                          member.exposureExampleSeconds > 0
                            ? `${member.exposureExampleSeconds}s exposed to smoke`
                            : undefined,
                        status: look(CREW_LOOK, member.status),
                      }))}
                    />
                  )}

                  {lostEquipment.length > 0 && (
                    <LossList
                      title="Equipment destroyed or unusable"
                      items={lostEquipment.map(([id, item]) => ({
                        key: id,
                        name: item.name,
                        status: look(EQUIPMENT_LOOK, item.state),
                      }))}
                    />
                  )}
                </div>
              )}

              <SectionLabel color="var(--good)">WHY</SectionLabel>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {pkg.recommendation.rationale.map((claim, i) => (
                  <ClaimRow key={i} claim={claim} />
                ))}
              </ul>

              <SectionLabel color="var(--amber)">TRADE-OFFS</SectionLabel>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--ink-2)' }}>
                {pkg.recommendation.tradeoffs.map((t, i) => (
                  <li key={i} style={{ marginBottom: 10, lineHeight: 1.6 }}>
                    <span style={{ color: 'var(--ink-2)' }}>vs</span>{' '}
                    <code style={{ color: 'var(--ink)' }}>{t.versus_action_id}</code>
                    <div style={{ marginTop: 3 }}>
                      <strong style={{ color: 'var(--ember)' }}>gives up</strong> {t.gives_up}
                    </div>
                    <div>
                      <strong style={{ color: 'var(--good)' }}>gains</strong> {t.gains}
                    </div>
                  </li>
                ))}
              </ul>

              <SectionLabel color="var(--ink-2)">UNCERTAINTY</SectionLabel>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--ink-2)' }}>
                {pkg.recommendation.uncertainty.map((u, i) => (
                  <li key={i} style={{ marginBottom: 6, lineHeight: 1.6 }}>
                    {u}
                  </li>
                ))}
              </ul>

              {pkg.recommendation.dissent.length > 0 && (
                <>
                  <SectionLabel color="var(--ember)">UNRESOLVED DISSENT</SectionLabel>
                  <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, color: 'var(--ember)' }}>
                    {pkg.recommendation.dissent.map((d, i) => (
                      <li key={i} style={{ marginBottom: 6, lineHeight: 1.6 }}>
                        {d}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              <div
                style={{
                  marginTop: 20,
                  paddingTop: 14,
                  borderTop: '1px solid var(--line)',
                  fontSize: 12,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--ink-2)',
                  letterSpacing: '.06em',
                }}
              >
                ADVISORY ONLY · HUMAN CONFIRMATION REQUIRED
              </div>
            </div>
          )}

          {violations.length > 0 && (
            <div style={{ ...card, borderLeft: '3px solid var(--ember)' }}>
              <div style={{ fontSize: 11, color: 'var(--ember)', letterSpacing: '0.08em' }}>
                GROUNDING VIOLATIONS — {violations.length} caught by the validator
              </div>
              <p style={{ margin: '6px 0 8px', fontSize: 11, color: 'var(--ink-3)' }}>
                An agent asserted something the simulation does not support. Shown, not
                silently corrected.
              </p>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                {violations.map((v, i) => (
                  <li key={i} style={{ marginBottom: 6, color: 'var(--ink-2)' }}>
                    <span style={{ color: SEVERITY_COLOR[v.severity] }}>[{v.rule}]</span>{' '}
                    <span style={{ color: 'var(--ink-2)' }}>{v.agent}</span> — {v.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div
            style={{
              display: 'grid',
              gap: 12,
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            }}
          >
            {pkg.findings.map((finding) => (
              <FindingCard key={finding.agent} finding={finding} />
            ))}
          </div>

          {pkg.critic.issues.length > 0 && (
            <div style={{ ...card, borderLeft: '3px solid var(--amber)' }}>
              <div style={{ fontSize: 11, color: 'var(--amber)', letterSpacing: '0.08em' }}>
                RED-TEAM CRITIC
              </div>
              <ul style={{ margin: '8px 0 0', paddingLeft: 16, fontSize: 12 }}>
                {pkg.critic.issues.map((issue, i) => (
                  <li key={i} style={{ marginBottom: 6, color: 'var(--ink-2)' }}>
                    <span style={{ color: SEVERITY_COLOR[issue.severity] }}>
                      [{issue.severity}]
                    </span>{' '}
                    <span style={{ color: 'var(--ink-2)' }}>{issue.target_agent}</span> —{' '}
                    {issue.issue}
                    {issue.suggested_correction && (
                      <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 2 }}>
                        → {issue.suggested_correction}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {pkg.evidence.length > 0 && (
            <div style={card}>
              <div style={{ fontSize: 11, color: 'var(--gold)', letterSpacing: '0.08em' }}>
                NASA EVIDENCE
              </div>
              <ul style={{ margin: '8px 0 0', paddingLeft: 16, fontSize: 12 }}>
                {pkg.evidence.map((answer, i) => (
                  <li key={i} style={{ marginBottom: 10, color: 'var(--ink-2)' }}>
                    {answer.claim}
                    <div style={{ fontSize: 11, color: 'var(--ink-3)', marginTop: 3 }}>
                      {answer.citation.title} — {answer.citation.locator}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--ink-2)', marginTop: 2 }}>
                      Applicability: {answer.applicability}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ fontSize: 10, color: 'var(--ink-4)', lineHeight: 1.6 }}>
            {String(pkg.provenance.sampling_note ?? '')}
            <br />
            Engine: {String(pkg.provenance.engine ?? '')} · focus:{' '}
            {String(pkg.provenance.focus_action_id ?? '')}
          </div>
        </>
      )}
    </div>
  )
}

/** A single headline consequence of the recommended action. */
function Consequence({
  label,
  value,
  of,
  bad,
}: {
  label: string
  value: number
  of?: number
  bad: boolean
}) {
  return (
    <div
      style={{
        background: bad ? 'var(--ember-wash)' : 'var(--surface)',
        border: `1px solid ${bad ? 'var(--ember)' : 'var(--good)'}`,
        borderRadius: 8,
        padding: '10px 14px',
      }}
    >
      <div style={{ color: 'var(--ink-2)', fontSize: 11, fontWeight: 600, marginBottom: 2 }}>
        {label}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 5 }}>
        <span
          style={{
            color: bad ? 'var(--ember)' : 'var(--good)',
            fontSize: 26,
            fontWeight: 700,
            lineHeight: 1.1,
          }}
        >
          {value}
        </span>
        {of !== undefined && (
          <span style={{ color: 'var(--ink-3)', fontSize: 12, fontWeight: 600 }}>/ {of}</span>
        )}
      </div>
    </div>
  )
}

/**
 * Named losses. A count says how much; only a list says which, and "which" is
 * what an operator has to plan around.
 */
function LossList({
  title,
  items,
}: {
  title: string
  items: { key: string; name: string; note?: string; status: StatusLook }[]
}) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ color: 'var(--ink-2)', fontSize: 11, fontWeight: 600, marginBottom: 6 }}>
        {title}
      </div>
      {items.map((item) => (
        <div
          key={item.key}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 10,
            padding: '5px 0',
            borderBottom: '1px solid var(--line)',
          }}
        >
          <span style={{ color: 'var(--ink)', fontSize: 13 }}>
            {item.name}
            {item.note && (
              <span style={{ color: 'var(--amber)', fontSize: 11, marginLeft: 8 }}>
                {item.note}
              </span>
            )}
          </span>
          <StatusPill status={item.status} />
        </div>
      ))}
    </div>
  )
}

function SectionLabel({ children, color }: { children: React.ReactNode; color: string }) {
  return (
    <div
      style={{
        color,
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: '0.08em',
        margin: '20px 0 8px',
      }}
    >
      {children}
    </div>
  )
}
