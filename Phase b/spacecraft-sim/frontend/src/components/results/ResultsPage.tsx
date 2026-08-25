/**
 * ResultsPage — full results view with Comparison and Timeline tabs.
 */

import { useState } from 'react'
import { useSimulationStore } from '../../store/useSimulationStore'
import { useScenarioStore } from '../../store/useScenarioStore'
import ActionResultCard from './ActionResultCard'
import TimelineView from './TimelineView'
import AdvisorPanel from '../advisor/AdvisorPanel'
import DisclaimerBanner from '../shared/DisclaimerBanner'

interface Props {
  onBack: () => void
}

export default function ResultsPage({ onBack }: Props) {
  const { result } = useSimulationStore()
  const { scenario } = useScenarioStore()
  const [activeTab, setActiveTab] = useState<'comparison' | 'timeline' | 'advisor'>('comparison')
  const [selectedActionId, setSelectedActionId] = useState<string | null>(null)

  if (!result) {
    return (
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          color: '#64748b',
          fontSize: 14,
          background: '#0a0c10',
        }}
      >
        No results available.{' '}
        <button
          onClick={onBack}
          style={{
            background: 'none',
            border: 'none',
            color: '#3b82f6',
            cursor: 'pointer',
            marginLeft: 8,
            fontSize: 14,
          }}
        >
          Go back
        </button>
      </div>
    )
  }

  const { generatedActions, results, simulatedHorizonSeconds, runsRequested, sourceLabel } = result

  const tabStyle = (tab: string): React.CSSProperties => ({
    background: 'none',
    border: 'none',
    borderBottom: `2px solid ${activeTab === tab ? '#3b82f6' : 'transparent'}`,
    color: activeTab === tab ? '#3b82f6' : '#64748b',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 600,
    padding: '8px 16px',
    letterSpacing: '0.04em',
  })

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: '#0a0c10',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          background: '#111318',
          borderBottom: '1px solid #2a2d36',
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexShrink: 0,
        }}
      >
        <button
          onClick={onBack}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748b',
            cursor: 'pointer',
            fontSize: 13,
            padding: '12px 0',
            display: 'flex',
            alignItems: 'center',
            gap: 5,
          }}
        >
          ← Back to Builder
        </button>

        <div style={{ width: 1, height: 20, background: '#2a2d36' }} />

        <div style={{ flex: 1 }}>
          <span style={{ color: '#e2e8f0', fontWeight: 600, fontSize: 14 }}>
            Emergency Analysis
          </span>
          <span style={{ color: '#475569', fontSize: 12, marginLeft: 10 }}>
            {scenario.name}
          </span>
        </div>

        <div style={{ color: '#475569', fontSize: 11 }}>
          {runsRequested} sampled scenarios · {simulatedHorizonSeconds}s horizon
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button style={tabStyle('comparison')} onClick={() => setActiveTab('comparison')}>
            Comparison
          </button>
          <button style={tabStyle('timeline')} onClick={() => setActiveTab('timeline')}>
            Timeline
          </button>
          <button style={tabStyle('advisor')} onClick={() => setActiveTab('advisor')}>
            Advisor
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
        {/* Disclaimer */}
        <div style={{ marginBottom: 16 }}>
          <DisclaimerBanner sourceLabel={sourceLabel} />
        </div>

        {/* Emergency context */}
        {scenario.emergency && (
          <div
            style={{
              background: '#450a0a',
              border: '1px solid #7f1d1d',
              borderRadius: 8,
              padding: '10px 16px',
              marginBottom: 16,
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              fontSize: 13,
            }}
          >
            <span>🔥</span>
            <div>
              <strong style={{ color: '#fca5a5' }}>
                Fire — {scenario.modules[scenario.emergency.affectedModuleId]?.name ?? scenario.emergency.affectedModuleId}
              </strong>
              <span style={{ color: '#9ca3af', marginLeft: 8 }}>
                {scenario.emergency.detected ? 'Detected' : 'Undetected'}
              </span>
            </div>
            <div style={{ marginLeft: 'auto', color: '#9ca3af', fontSize: 12 }}>
              {generatedActions.length} actions analyzed
            </div>
          </div>
        )}

        {activeTab === 'comparison' && (
          <div>
            <div style={{ color: '#475569', fontSize: 11, marginBottom: 14, letterSpacing: '0.05em' }}>
              SIMULATED ACTION OUTCOMES — click a card to highlight
            </div>
            <div
              style={{
                display: 'flex',
                gap: 14,
                overflowX: 'auto',
                paddingBottom: 12,
              }}
            >
              {results.map((r) => {
                const action = generatedActions.find((a) => a.id === r.actionId)
                if (!action) return null
                return (
                  <ActionResultCard
                    key={r.actionId}
                    result={r}
                    action={action}
                    scenario={scenario}
                    allResults={results}
                    isSelected={selectedActionId === r.actionId}
                    onSelect={() =>
                      setSelectedActionId(selectedActionId === r.actionId ? null : r.actionId)
                    }
                  />
                )
              })}
            </div>

            {/* No "BEST ACTION" — trade-off note only */}
            <div
              style={{
                marginTop: 16,
                padding: '10px 14px',
                background: '#1a1d24',
                border: '1px solid #2a2d36',
                borderRadius: 6,
                fontSize: 12,
                color: '#64748b',
              }}
            >
              <strong style={{ color: '#94a3b8' }}>Trade-off note:</strong> Each action presents different
              containment, crew evacuation, and capability trade-offs. No single "best action" is
              automatically recommended — this decision rests with the operator.
              Open the Advisor tab for the Phase C multi-agent analysis.
            </div>
          </div>
        )}

        {activeTab === 'timeline' && (
          <TimelineView
            results={results}
            actions={generatedActions}
            scenario={scenario}
          />
        )}

        {activeTab === 'advisor' && (
          <AdvisorPanel
            scenario={scenario}
            emergency={scenario.emergency}
            focusActionId={selectedActionId}
          />
        )}
      </div>
    </div>
  )
}
