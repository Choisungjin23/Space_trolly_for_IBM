import type {
  EthicalAssessment,
  EthicsStatus,
  PolicyCheckStatus,
} from '../../types/advisor'

const STATUS_LOOK: Record<EthicsStatus, { color: string; label: string }> = {
  POLICY_CONSISTENT: { color: 'var(--good)', label: 'POLICY CONSISTENT' },
  REVIEW_REQUIRED: { color: 'var(--amber)', label: 'REVIEW REQUIRED' },
  BLOCKED: { color: 'var(--ember)', label: 'BLOCKED' },
}

const CHECK_COLOR: Record<PolicyCheckStatus, string> = {
  PASS: 'var(--good)',
  REVIEW: 'var(--amber)',
  BLOCK: 'var(--ember)',
}

function metric(value: number | null, digits = 2): string {
  return value === null ? 'Not modeled' : value.toFixed(digits)
}

export default function EthicalAssessmentCard({
  assessment,
}: {
  assessment: EthicalAssessment
}) {
  const status = STATUS_LOOK[assessment.status]
  const selected = assessment.action_assessments.find(
    (action) => action.action_id === assessment.selected_action_id,
  )
  const decidingStep = [...assessment.tie_break_steps]
    .reverse()
    .find((step) => step.remaining_action_ids.length === 1)

  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--line)',
        borderLeft: `3px solid ${status.color}`,
        borderRadius: 8,
        padding: '18px 20px',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div className="circe-label" style={{ color: 'var(--gold)' }}>
            ETHICAL ASSESSMENT · POC POLICY
          </div>
          <div className="mono" style={{ marginTop: 5, fontSize: 10, color: 'var(--ink-4)' }}>
            {assessment.policy_id} · v{assessment.policy_version}
          </div>
        </div>
        <span
          className="mono"
          style={{
            color: status.color,
            border: `1px solid ${status.color}`,
            borderRadius: 3,
            padding: '4px 8px',
            fontSize: 10,
            letterSpacing: '.08em',
          }}
        >
          {status.label}
        </span>
      </div>

      <p style={{ margin: '14px 0 0', color: 'var(--ink-2)', fontSize: 13, lineHeight: 1.65 }}>
        {assessment.selection_basis}
      </p>
      <p style={{ margin: '6px 0 0', color: 'var(--ink-3)', fontSize: 11.5, lineHeight: 1.55 }}>
        This is consistency with a declared project policy—not a universal moral score.
      </p>

      {selected && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(155px, 1fr))',
            gap: 10,
            marginTop: 16,
          }}
        >
          <EthicsMetric label="Expected returnees" value={metric(selected.expected_returnees)} />
          <EthicsMetric label="Expected survivors" value={metric(selected.expected_survivors)} />
          <EthicsMetric
            label="Worst-off survival"
            value={
              selected.minimum_crew_survival_probability === null
                ? 'Not modeled'
                : `${(selected.minimum_crew_survival_probability * 100).toFixed(1)}%`
            }
          />
          <EthicsMetric label="Crew trapped" value={String(selected.trapped_crew_count)} />
        </div>
      )}

      {decidingStep && (
        <div
          style={{
            marginTop: 14,
            padding: '11px 13px',
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 4,
          }}
        >
          <div className="mono" style={{ color: 'var(--gold)', fontSize: 10 }}>
            TIE-BREAK · {decidingStep.criterion.replaceAll('_', ' ').toUpperCase()}
          </div>
          <div style={{ marginTop: 5, color: 'var(--ink-2)', fontSize: 12.5, lineHeight: 1.55 }}>
            {decidingStep.explanation}
          </div>
        </div>
      )}

      {assessment.co_recommended_action_ids.length > 1 && (
        <div style={{ marginTop: 12, color: 'var(--amber)', fontSize: 12 }}>
          Unresolved equal candidates: {assessment.co_recommended_action_ids.join(', ')}
        </div>
      )}

      <details style={{ marginTop: 14 }}>
        <summary style={{ cursor: 'pointer', color: 'var(--ink-2)', fontSize: 12 }}>
          Compare human outcomes for every action
        </summary>
        <div style={{ overflowX: 'auto', marginTop: 9 }}>
          <table
            style={{
              width: '100%',
              minWidth: 690,
              borderCollapse: 'collapse',
              fontSize: 11,
              color: 'var(--ink-2)',
            }}
          >
            <thead>
              <tr style={{ color: 'var(--ink-3)', textAlign: 'left' }}>
                <th style={th}>Action</th>
                <th style={th}>Returnees</th>
                <th style={th}>Survivors</th>
                <th style={th}>Worst-off</th>
                <th style={th}>Trapped</th>
                <th style={th}>Max dose</th>
                <th style={th}>Modules reached</th>
              </tr>
            </thead>
            <tbody>
              {assessment.action_assessments.map((action) => (
                <tr
                  key={action.action_id}
                  style={{
                    borderTop: '1px solid var(--line)',
                    color: action.co_recommended ? 'var(--good)' : 'var(--ink-2)',
                  }}
                >
                  <td style={td}>
                    <code>{action.action_id}</code>
                    {action.co_recommended ? ' · candidate' : ''}
                  </td>
                  <td style={td}>{metric(action.expected_returnees)}</td>
                  <td style={td}>{metric(action.expected_survivors)}</td>
                  <td style={td}>
                    {action.minimum_crew_survival_probability === null
                      ? '—'
                      : `${(action.minimum_crew_survival_probability * 100).toFixed(1)}%`}
                  </td>
                  <td style={td}>{action.trapped_crew_count}</td>
                  <td style={td}>{metric(action.maximum_smac_dose_fraction)}</td>
                  <td style={td}>{action.hazard_reached_module_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>

      {selected && (
        <div style={{ marginTop: 16 }}>
          <div className="mono" style={{ color: 'var(--ink-3)', fontSize: 10, letterSpacing: '.08em' }}>
            POLICY CHECKS
          </div>
          <ul style={{ margin: '7px 0 0', paddingLeft: 17, fontSize: 12 }}>
            {selected.policy_checks.map((check) => (
              <li key={check.rule_id} style={{ marginBottom: 6, color: 'var(--ink-2)' }}>
                <span style={{ color: CHECK_COLOR[check.status] }}>
                  [{check.status}] {check.rule_id}
                </span>{' '}
                — {check.summary}
              </li>
            ))}
          </ul>
        </div>
      )}

      <details style={{ marginTop: 14 }}>
        <summary style={{ cursor: 'pointer', color: 'var(--ink-2)', fontSize: 12 }}>
          Policy sources and limits
        </summary>
        <ul style={{ margin: '9px 0 0', paddingLeft: 17, fontSize: 11.5, color: 'var(--ink-3)' }}>
          {assessment.sources.map((source) => (
            <li key={source.source_id} style={{ marginBottom: 7 }}>
              {source.url ? (
                <a href={source.url} target="_blank" rel="noreferrer" style={{ color: 'var(--gold)' }}>
                  {source.title}
                </a>
              ) : (
                source.title
              )}{' '}
              — {source.locator}
            </li>
          ))}
          {assessment.limitations.map((limit, index) => (
            <li key={`limit-${index}`} style={{ marginBottom: 7 }}>
              Limit: {limit}
            </li>
          ))}
        </ul>
      </details>

      <div
        className="mono"
        style={{
          marginTop: 15,
          paddingTop: 11,
          borderTop: '1px solid var(--line)',
          color: 'var(--ink-2)',
          fontSize: 10.5,
          letterSpacing: '.06em',
        }}
      >
        DETERMINISTIC POLICY CHECK · HUMAN DECISION REQUIRED
      </div>
    </div>
  )
}

const th: React.CSSProperties = {
  padding: '7px 8px',
  fontWeight: 500,
  whiteSpace: 'nowrap',
}

const td: React.CSSProperties = {
  padding: '8px',
  whiteSpace: 'nowrap',
}

function EthicsMetric({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', padding: '9px 11px' }}>
      <div style={{ color: 'var(--ink-3)', fontSize: 10 }}>{label}</div>
      <div className="mono" style={{ color: 'var(--ink)', fontSize: 17, marginTop: 3 }}>
        {value}
      </div>
    </div>
  )
}
