/**
 * ResultsPage — full results view with Comparison and Timeline tabs.
 */

import { useState } from 'react'
import { useSimulationStore } from '../../store/useSimulationStore'
import { useScenarioStore } from '../../store/useScenarioStore'
import ActionResultCard from './ActionResultCard'
import TimelineView from './TimelineView'
import AdvisorPanel from '../advisor/AdvisorPanel'
import { ProvenanceDisclosure } from '../shared/Provenance'
import PriorityGraph from './PriorityGraph'
import {
  IconAdvisory,
  IconConstellation,
  IconFutures,
  IconHazard,
} from '../shared/Icons'

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
          color: 'var(--ink-3)',
          fontSize: 14,
          background: 'var(--void)',
        }}
      >
        No results available.{' '}
        <button
          onClick={onBack}
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--gold)',
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

  const { generatedActions, results, simulatedHorizonSeconds, runsRequested } = result
  const priorityResult =
    results.find((candidate) => candidate.actionId === selectedActionId) ?? results[0]

  const tabStyle = (tab: string): React.CSSProperties => ({
    display: 'flex',
    alignItems: 'center',
    gap: 7,
    background: 'none',
    border: 'none',
    borderBottom: `1px solid ${activeTab === tab ? 'var(--gold)' : 'transparent'}`,
    color: activeTab === tab ? 'var(--gold)' : 'var(--ink-3)',
    cursor: 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: 11,
    fontWeight: 500,
    padding: '17px 15px 16px',
    letterSpacing: '.14em',
    transition: 'color .15s, border-color .15s',
  })

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: 'var(--void)',
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          background: 'var(--surface)',
          borderBottom: '1px solid var(--line)',
          padding: '0 18px',
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
            color: 'var(--ink-3)',
            cursor: 'pointer',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '.14em',
            padding: '18px 0',
          }}
        >
          ← ARCHITECTURE
        </button>

        <div style={{ width: 1, height: 20, background: 'var(--line)' }} />

        <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
          <span style={{ color: 'var(--gold)' }}>
            <IconConstellation size={15} />
          </span>
          <span style={{ color: 'var(--ink)', fontSize: 14 }}>{scenario.name}</span>
        </div>

        <div style={{ flex: 1 }} />

        <div
          className="mono"
          style={{ color: 'var(--ink-4)', fontSize: 10, letterSpacing: '.1em' }}
        >
          {runsRequested} SAMPLED SCENARIOS · {simulatedHorizonSeconds}s HORIZON
        </div>

        <ProvenanceDisclosure align="right" />

        {/* The remaining two movements */}
        <div style={{ display: 'flex', alignItems: 'center' }}>
          <button style={tabStyle('comparison')} onClick={() => setActiveTab('comparison')}>
            <IconFutures size={13} />
            FUTURES
          </button>
          <button style={tabStyle('timeline')} onClick={() => setActiveTab('timeline')}>
            TIMELINE
          </button>
          <button style={tabStyle('advisor')} onClick={() => setActiveTab('advisor')}>
            <IconAdvisory size={13} />
            ADVISORY
          </button>
        </div>
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: 'auto', padding: 20 }}>
        {/* Emergency context */}
        {scenario.emergency && (
          <div
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--line)',
              borderLeft: '2px solid var(--ember)',
              borderRadius: 3,
              padding: '11px 16px',
              marginBottom: 18,
              display: 'flex',
              alignItems: 'center',
              gap: 14,
              fontSize: 13,
            }}
          >
            <span style={{ color: 'var(--ember)' }}>
              <IconHazard size={15} />
            </span>
            <div>
              <span style={{ color: 'var(--ink)' }}>
                {scenario.emergency.type === 'electronic_short' ? 'Electronic Short' : 'Fire'} —{' '}
                {scenario.modules[scenario.emergency.affectedModuleId]?.name ??
                  scenario.emergency.affectedModuleId}
              </span>
              <span
                className="mono"
                style={{
                  color: 'var(--ink-3)',
                  marginLeft: 12,
                  fontSize: 10,
                  letterSpacing: '.12em',
                }}
              >
                {scenario.emergency.detected ? 'DETECTED' : 'UNDETECTED'}
              </span>
            </div>
            <div
              className="mono"
              style={{
                marginLeft: 'auto',
                color: 'var(--ink-3)',
                fontSize: 10,
                letterSpacing: '.1em',
              }}
            >
              {generatedActions.length} CANDIDATE ACTIONS
            </div>
            {scenario.emergency.escapeTarget && (
              <div className="mono" style={{ color: 'var(--good)', fontSize: 9 }}>
                ESCAPE {scenario.modules[scenario.emergency.escapeTarget.fromModuleId]?.name ?? scenario.emergency.escapeTarget.fromModuleId}
                {' » '}
                {scenario.modules[scenario.emergency.escapeTarget.toModuleId]?.name ?? scenario.emergency.escapeTarget.toModuleId}
                {scenario.emergency.escapeTarget.maxOccupants
                  ? ` · ${scenario.emergency.escapeTarget.maxOccupants} SEATS`
                  : ''}
              </div>
            )}
          </div>
        )}

        {priorityResult && (
          <PriorityGraph
            result={priorityResult}
            action={generatedActions.find((action) => action.id === priorityResult.actionId)}
            scenario={scenario}
          />
        )}

        {activeTab === 'comparison' && (
          <div>
            <div
              className="circe-label"
              style={{ color: 'var(--ink-3)', marginBottom: 16 }}
            >
              SIMULATED OUTCOMES · SELECT AN ACTION TO FOCUS THE ADVISORY
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
                background: 'transparent',
                border: '1px solid var(--line)',
                borderRadius: 3,
                fontSize: 12,
                color: 'var(--ink-3)',
                lineHeight: 1.7,
              }}
            >
              <span
                className="circe-label"
                style={{ color: 'var(--ink-2)', display: 'block', marginBottom: 5 }}
              >
                TRADE-OFF
              </span>
              Each action buys containment, evacuation margin, or capability at
              the cost of another. Nothing here ranks them into a winner — that
              judgement belongs to the operator. Open ADVISORY to consult the
              multi-agent analysis.
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
            results={results}
            actions={generatedActions}
          />
        )}
      </div>
    </div>
  )
}
