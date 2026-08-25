/**
 * TimelineView — optional-priority timeline slider component.
 *
 * Uses exampleTrajectory from the simulation result to show
 * a step-by-step snapshot of the spacecraft state.
 *
 * Labeled: "Example sampled trajectory — not a unique predicted future"
 */

import { useState } from 'react'
import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import type { SpacecraftScenario } from '../../types/scenario'

interface Props {
  results: ActionSimulationResult[]
  actions: ActionSpec[]
  scenario: SpacecraftScenario
}

function HazardBar({ severity }: { severity: number }) {
  const color =
    severity > 0.5 ? '#ef4444' : severity > 0.2 ? '#f59e0b' : '#22c55e'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div
        style={{
          flex: 1,
          height: 6,
          background: '#1e2128',
          borderRadius: 3,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${severity * 100}%`,
            height: '100%',
            background: color,
            borderRadius: 3,
            transition: 'width 0.3s',
          }}
        />
      </div>
      <span style={{ color, fontSize: 10, width: 32, textAlign: 'right' }}>
        {(severity * 100).toFixed(0)}%
      </span>
    </div>
  )
}

export default function TimelineView({ results, actions, scenario }: Props) {
  const [selectedActionId, setSelectedActionId] = useState(
    results[0]?.actionId ?? ''
  )
  const [stepIndex, setStepIndex] = useState(0)

  const selectedResult = results.find((r) => r.actionId === selectedActionId)
  const trajectory = selectedResult?.exampleTrajectory

  if (!trajectory) {
    return (
      <div
        style={{
          background: '#1e2128',
          border: '1px solid #2a2d36',
          borderRadius: 10,
          padding: 24,
          textAlign: 'center',
          color: '#475569',
          fontSize: 13,
        }}
      >
        No example trajectory available for this simulation result.
        <br />
        <span style={{ fontSize: 11, marginTop: 8, display: 'block' }}>
          Timeline requires <code>exampleTrajectory</code> in the simulation response.
        </span>
      </div>
    )
  }

  const currentStep = trajectory.steps[stepIndex]
  const maxStep = trajectory.steps.length - 1

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Disclaimer */}
      <div
        style={{
          background: '#1a1d24',
          border: '1px solid #2a2d36',
          borderLeft: '3px solid #a855f7',
          borderRadius: 5,
          padding: '8px 14px',
          fontSize: 11,
          color: '#94a3b8',
        }}
      >
        <strong style={{ color: '#c084fc' }}>Example sampled trajectory</strong>
        {' '}— not a unique predicted future. Seed {trajectory.seed}.
        One deterministic path from the Phase A engine for illustration only.
      </div>

      {/* Action selector */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        {results.map((r) => {
          const act = actions.find((a) => a.id === r.actionId)
          return (
            <button
              key={r.actionId}
              onClick={() => {
                setSelectedActionId(r.actionId)
                setStepIndex(0)
              }}
              style={{
                background: r.actionId === selectedActionId ? '#1d4ed8' : '#1e2128',
                color: r.actionId === selectedActionId ? '#bfdbfe' : '#94a3b8',
                border: `1px solid ${r.actionId === selectedActionId ? '#3b82f6' : '#2a2d36'}`,
                borderRadius: 5,
                padding: '5px 12px',
                fontSize: 12,
                cursor: 'pointer',
                fontWeight: r.actionId === selectedActionId ? 600 : 400,
              }}
            >
              {act?.label ?? r.actionId}
            </button>
          )
        })}
      </div>

      {/* Slider */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <span style={{ color: '#64748b', fontSize: 12 }}>
            Step {currentStep?.stepIndex ?? 0} — T+{currentStep?.timeSeconds ?? 0}s
          </span>
          <span style={{ color: '#64748b', fontSize: 12 }}>
            {trajectory.steps[maxStep]?.timeSeconds}s total
          </span>
        </div>
        <input
          type="range"
          min={0}
          max={maxStep}
          value={stepIndex}
          onChange={(e) => setStepIndex(parseInt(e.target.value))}
          style={{ width: '100%', accentColor: '#3b82f6' }}
        />
      </div>

      {/* Events at this step */}
      {currentStep && currentStep.events.length > 0 && (
        <div
          style={{
            background: '#111318',
            border: '1px solid #2a2d36',
            borderRadius: 6,
            padding: '8px 12px',
          }}
        >
          {currentStep.events.map((ev, i) => (
            <div key={i} style={{ color: '#e2e8f0', fontSize: 12, padding: '2px 0' }}>
              <span style={{ color: '#475569', marginRight: 8 }}>T+{currentStep.timeSeconds}s</span>
              {ev}
            </div>
          ))}
        </div>
      )}

      {/* Module states grid */}
      {currentStep && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
            gap: 10,
          }}
        >
          {Object.entries(currentStep.moduleStates).map(([modId, state]) => {
            const mod = scenario.modules[modId]
            const hasEmergency = scenario.emergency?.affectedModuleId === modId
            return (
              <div
                key={modId}
                style={{
                  background: '#1e2128',
                  border: `1px solid ${state.hazardSeverity > 0.3 ? '#7f1d1d' : '#2a2d36'}`,
                  borderRadius: 6,
                  padding: '10px 12px',
                }}
              >
                <div style={{ color: '#e2e8f0', fontWeight: 500, fontSize: 13, marginBottom: 6 }}>
                  {mod?.name ?? modId}
                  {hasEmergency && <span style={{ color: '#ef4444', marginLeft: 6 }}>🔥</span>}
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>Hazard severity</div>
                <HazardBar severity={state.hazardSeverity} />
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 6 }}>
                  Crew present: <span style={{ color: '#e2e8f0' }}>{state.crewPresent}</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Full event log */}
      <div>
        <div style={{ color: '#64748b', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', marginBottom: 8 }}>
          FULL EVENT LOG
        </div>
        <div style={{ background: '#111318', border: '1px solid #2a2d36', borderRadius: 6, padding: '8px 12px' }}>
          {trajectory.steps.map((step) =>
            step.events.map((ev, i) => (
              <div
                key={`${step.stepIndex}-${i}`}
                style={{
                  padding: '3px 0',
                  borderBottom: '1px solid #1a1d24',
                  display: 'flex',
                  gap: 10,
                  fontSize: 12,
                  opacity: step.stepIndex > stepIndex ? 0.4 : 1,
                }}
              >
                <span style={{ color: '#475569', flexShrink: 0, width: 45 }}>T+{step.timeSeconds}s</span>
                <span style={{ color: '#e2e8f0' }}>{ev}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
