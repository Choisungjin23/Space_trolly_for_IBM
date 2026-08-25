/**
 * AdvisorPanel — the Phase C multi-agent layer.
 *
 * This is the only place in the product where an action is recommended. The
 * comparison table stays recommendation-free by design; here the coordinator
 * advises, the critic argues back, and the operator decides.
 */

import { useEffect, useState } from 'react'
import { analyzeEmergency, fetchAdvisorStatus } from '../../api/simulatorClient'
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
}

const AGENT_LABELS: Record<string, string> = {
  hazard: 'Hazard',
  crew_safety: 'Crew Safety',
  systems: 'Systems',
  mission: 'Mission',
}

const BASIS_COLOR: Record<string, string> = {
  SIMULATION_FACT: '#22c55e',
  EVIDENCE: '#3b82f6',
  INFERENCE: '#f59e0b',
  ASSUMPTION: '#a855f7',
}

const SEVERITY_COLOR: Record<Severity, string> = {
  BLOCKER: '#ef4444',
  MAJOR: '#f59e0b',
  MINOR: '#64748b',
}

const card: React.CSSProperties = {
  background: '#12151c',
  border: '1px solid #232833',
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
          color: BASIS_COLOR[claim.basis] ?? '#94a3b8',
          border: `1px solid ${BASIS_COLOR[claim.basis] ?? '#94a3b8'}`,
        }}
      >
        {claim.basis.replace('_', ' ')}
      </span>
      <span style={{ color: '#cbd5e1', fontSize: 13 }}>{claim.statement}</span>
      {claim.refs.length > 0 && (
        <div style={{ fontSize: 10, color: '#64748b', marginTop: 2, marginLeft: 2 }}>
          traced to {claim.refs.join(', ')}
        </div>
      )}
    </li>
  )
}

function FindingCard({ finding }: { finding: AgentFinding }) {
  return (
    <div style={card}>
      <h4 style={{ margin: '0 0 10px', fontSize: 13, color: '#e2e8f0' }}>
        {AGENT_LABELS[finding.agent] ?? finding.agent}
      </h4>
      {finding.claims.length > 0 ? (
        <ul style={{ margin: 0, paddingLeft: 16 }}>
          {finding.claims.map((claim, i) => (
            <ClaimRow key={i} claim={claim} />
          ))}
        </ul>
      ) : (
        <p style={{ margin: 0, fontSize: 12, color: '#64748b' }}>No claims returned.</p>
      )}
      {finding.concerns.length > 0 && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 10, color: '#f59e0b', letterSpacing: '0.06em' }}>
            CONCERNS
          </div>
          <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 12, color: '#94a3b8' }}>
            {finding.concerns.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function AdvisorPanel({ scenario, emergency, focusActionId }: Props) {
  const [status, setStatus] = useState<AdvisorStatus | null>(null)
  const [pkg, setPkg] = useState<DecisionPackage | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchAdvisorStatus()
      .then(setStatus)
      .catch((e) => setStatus({ available: false, detail: String(e) }))
  }, [])

  async function run() {
    setBusy(true)
    setError(null)
    try {
      setPkg(
        await analyzeEmergency({
          scenario,
          emergency,
          focusActionId: focusActionId ?? null,
          samples: 20,
          seed: 42,
        }),
      )
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  const violations = pkg?.critic.grounding_violations ?? []

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ ...card, borderLeft: '3px solid #a855f7' }}>
        <div style={{ fontSize: 11, color: '#a855f7', letterSpacing: '0.08em' }}>
          PHASE C — MULTI-AGENT ADVISOR
        </div>
        <p style={{ margin: '6px 0 0', fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>
          Seven agents read the Phase A simulation output: four specialists, a NASA
          evidence retriever, a red-team critic, and a coordinator. Every number they
          state is machine-checked against the simulation; unsupported assertions are
          shown rather than removed. The recommendation is advisory — you decide.
        </p>
        <div style={{ marginTop: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
          <button
            onClick={run}
            disabled={busy || (status !== null && !status.available)}
            style={{
              padding: '8px 18px',
              borderRadius: 6,
              border: 'none',
              cursor: busy ? 'wait' : 'pointer',
              background: status?.available === false ? '#334155' : '#a855f7',
              color: '#fff',
              fontSize: 13,
            }}
          >
            {busy ? 'Agents deliberating…' : 'Run advisor'}
          </button>
          {status && !status.available && (
            <span style={{ fontSize: 11, color: '#f59e0b' }}>{status.detail}</span>
          )}
        </div>
      </div>

      {error && (
        <div style={{ ...card, borderLeft: '3px solid #ef4444', color: '#fca5a5', fontSize: 12 }}>
          {error}
        </div>
      )}

      {pkg && (
        <>
          {pkg.recommendation && (
            <div style={{ ...card, borderLeft: '3px solid #22c55e' }}>
              <div style={{ fontSize: 11, color: '#22c55e', letterSpacing: '0.08em' }}>
                COORDINATOR RECOMMENDATION
              </div>
              <h3 style={{ margin: '6px 0 10px', fontSize: 16, color: '#e2e8f0' }}>
                {pkg.recommendation.recommended_action_id}
              </h3>

              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {pkg.recommendation.rationale.map((claim, i) => (
                  <ClaimRow key={i} claim={claim} />
                ))}
              </ul>

              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 10, color: '#f59e0b', letterSpacing: '0.06em' }}>
                  TRADE-OFFS
                </div>
                <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 12, color: '#94a3b8' }}>
                  {pkg.recommendation.tradeoffs.map((t, i) => (
                    <li key={i} style={{ marginBottom: 4 }}>
                      vs <code style={{ color: '#cbd5e1' }}>{t.versus_action_id}</code> — gives up{' '}
                      {t.gives_up}; gains {t.gains}
                    </li>
                  ))}
                </ul>
              </div>

              <div style={{ marginTop: 12 }}>
                <div style={{ fontSize: 10, color: '#64748b', letterSpacing: '0.06em' }}>
                  UNCERTAINTY
                </div>
                <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 12, color: '#94a3b8' }}>
                  {pkg.recommendation.uncertainty.map((u, i) => (
                    <li key={i}>{u}</li>
                  ))}
                </ul>
              </div>

              {pkg.recommendation.dissent.length > 0 && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 10, color: '#ef4444', letterSpacing: '0.06em' }}>
                    UNRESOLVED DISSENT
                  </div>
                  <ul style={{ margin: '4px 0 0', paddingLeft: 16, fontSize: 12, color: '#fca5a5' }}>
                    {pkg.recommendation.dissent.map((d, i) => (
                      <li key={i}>{d}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div
                style={{
                  marginTop: 14,
                  paddingTop: 10,
                  borderTop: '1px solid #232833',
                  fontSize: 11,
                  color: '#f59e0b',
                }}
              >
                ⚠ Advisory only. The operator makes the decision.
              </div>
            </div>
          )}

          {violations.length > 0 && (
            <div style={{ ...card, borderLeft: '3px solid #ef4444' }}>
              <div style={{ fontSize: 11, color: '#ef4444', letterSpacing: '0.08em' }}>
                GROUNDING VIOLATIONS — {violations.length} caught by the validator
              </div>
              <p style={{ margin: '6px 0 8px', fontSize: 11, color: '#64748b' }}>
                An agent asserted something the simulation does not support. Shown, not
                silently corrected.
              </p>
              <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12 }}>
                {violations.map((v, i) => (
                  <li key={i} style={{ marginBottom: 6, color: '#94a3b8' }}>
                    <span style={{ color: SEVERITY_COLOR[v.severity] }}>[{v.rule}]</span>{' '}
                    <span style={{ color: '#cbd5e1' }}>{v.agent}</span> — {v.detail}
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
            <div style={{ ...card, borderLeft: '3px solid #f59e0b' }}>
              <div style={{ fontSize: 11, color: '#f59e0b', letterSpacing: '0.08em' }}>
                RED-TEAM CRITIC
              </div>
              <ul style={{ margin: '8px 0 0', paddingLeft: 16, fontSize: 12 }}>
                {pkg.critic.issues.map((issue, i) => (
                  <li key={i} style={{ marginBottom: 6, color: '#94a3b8' }}>
                    <span style={{ color: SEVERITY_COLOR[issue.severity] }}>
                      [{issue.severity}]
                    </span>{' '}
                    <span style={{ color: '#cbd5e1' }}>{issue.target_agent}</span> —{' '}
                    {issue.issue}
                    {issue.suggested_correction && (
                      <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>
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
              <div style={{ fontSize: 11, color: '#3b82f6', letterSpacing: '0.08em' }}>
                NASA EVIDENCE
              </div>
              <ul style={{ margin: '8px 0 0', paddingLeft: 16, fontSize: 12 }}>
                {pkg.evidence.map((answer, i) => (
                  <li key={i} style={{ marginBottom: 10, color: '#cbd5e1' }}>
                    {answer.claim}
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>
                      {answer.citation.title} — {answer.citation.locator}
                    </div>
                    <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
                      Applicability: {answer.applicability}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div style={{ fontSize: 10, color: '#475569', lineHeight: 1.6 }}>
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
