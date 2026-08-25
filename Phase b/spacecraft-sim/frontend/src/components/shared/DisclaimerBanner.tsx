/**
 * DisclaimerBanner — persistent PoC disclaimer.
 * Never hidden. Always labels mock/PoC outputs correctly.
 */

interface Props {
  sourceLabel?: string
}

export default function DisclaimerBanner({ sourceLabel }: Props) {
  return (
    <div
      style={{
        background: '#1a1d24',
        border: '1px solid #2a2d36',
        borderLeft: '3px solid #f59e0b',
        borderRadius: 5,
        padding: '8px 14px',
        fontSize: 11,
        color: '#94a3b8',
        display: 'flex',
        alignItems: 'flex-start',
        gap: 8,
      }}
    >
      <span style={{ color: '#f59e0b', flexShrink: 0 }}>⚠</span>
      <div>
        {sourceLabel && (
          <div style={{ color: '#f59e0b', fontWeight: 600, marginBottom: 2 }}>
            {sourceLabel}
          </div>
        )}
        <div>
          Results come from the Phase A engine under configurable PoC assumptions
          (NASA-sourced constants are labeled VERIFIED_, unvalidated ones ASSUMED_).
          Sample counts are counts over sampled scenario assumptions — not
          validated physical survival probabilities.
        </div>
      </div>
    </div>
  )
}
