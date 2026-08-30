/**
 * TimelineView — step through one action's example trajectory.
 *
 * The reading the view is built around is *change*: each module shows its
 * severity across every step as a sparkline, with the current step accented and
 * the step-over-step delta spelled out, so movement is visible without scrubbing.
 *
 * Sample-count wording only; no probability language. Statuses carry an icon and
 * a word as well as a colour.
 */

import { useEffect, useState } from 'react'
import type { ActionSimulationResult, ActionSpec } from '../../types/simulator'
import type { SpacecraftScenario } from '../../types/scenario'
import { Meter, Sparkline, StatusPill } from './StatDisplay'
import { CREW_LOOK, EQUIPMENT_LOOK, look } from './statusLook'

interface Props {
  results: ActionSimulationResult[]
  actions: ActionSpec[]
  scenario: SpacecraftScenario
}

/** Severity is a fraction of the egress-impairment threshold, not a probability. */
function severityRamp(severity: number) {
  if (severity > 0.5)
    return {
      fill: 'var(--ember)',
      track: 'var(--ember-wash)',
      ink: 'var(--ember)',
      label: 'SEVERE',
    }
  if (severity > 0.2)
    return {
      fill: 'var(--amber)',
      track: 'var(--amber-wash)',
      ink: 'var(--amber)',
      label: 'ELEVATED',
    }
  if (severity > 0.02)
    return {
      fill: 'var(--good)',
      track: 'var(--good-wash)',
      ink: 'var(--good-bright)',
      label: 'LOW',
    }
  return {
    fill: 'var(--good)',
    track: 'var(--good-wash)',
    ink: 'var(--good-bright)',
    label: 'CLEAR',
  }
}

const DAMAGED_STATES = ['explicitly_failed', 'exposed_at_risk', 'unavailable']

export default function TimelineView({ results, actions, scenario }: Props) {
  const [selectedActionId, setSelectedActionId] = useState(
    results[0]?.actionId ?? ''
  )
  const [stepIndex, setStepIndex] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)

  const selectedResult = results.find((r) => r.actionId === selectedActionId)
  const trajectory = selectedResult?.exampleTrajectory

  // Declared before the early return below: hooks must run on every render.
  const maxStep = Math.max(0, (trajectory?.steps.length ?? 1) - 1)
  const atEnd = stepIndex >= maxStep
  // Reaching the last step is derived, not signalled by flipping state from
  // inside the effect - that would start a second render pass to say something
  // the current one already knows.
  const isRunning = playing && !atEnd

  // Auto-advance. Each tick schedules only the next one rather than running a
  // repeating interval, so playback halts exactly at the last step and a change
  // of speed takes effect immediately instead of after the current period.
  useEffect(() => {
    if (!isRunning) return
    const timer = setTimeout(() => setStepIndex((i) => i + 1), 900 / speed)
    return () => clearTimeout(timer)
  }, [isRunning, stepIndex, speed])

  function handlePlayPause() {
    if (isRunning) {
      setPlaying(false)
      return
    }
    // Pressing play at the end replays from the top rather than doing nothing.
    if (atEnd) setStepIndex(0)
    setPlaying(true)
  }

  if (!trajectory) {
    return (
      <div
        style={{
          background: 'var(--surface-3)',
          border: '1px solid var(--line)',
          borderRadius: 10,
          padding: 24,
          textAlign: 'center',
          color: 'var(--ink-4)',
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
  const previousStep = stepIndex > 0 ? trajectory.steps[stepIndex - 1] : null

  const equipment = Object.entries(selectedResult?.equipment?.byEquipmentId ?? {})
  const equipmentHit = equipment.filter(([, item]) => DAMAGED_STATES.includes(item.state))
  const crewMembers = Object.entries(selectedResult?.crew.byCrewMember ?? {})

  // Peak severity across the whole run tells the operator how bad it ever got,
  // which the current step alone cannot.
  const peakSeverity = Math.max(
    0,
    ...trajectory.steps.flatMap((s) =>
      Object.values(s.moduleStates).map((m) => m.hazardSeverity)
    )
  )
  const crewInDanger = currentStep
    ? Object.entries(currentStep.moduleStates)
        .filter(([, m]) => m.crewPresent > 0 && m.hazardSeverity > 0.2)
        .reduce((n, [, m]) => n + m.crewPresent, 0)
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
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
                setPlaying(false)
              }}
              style={{
                background: r.actionId === selectedActionId ? 'var(--gold-dim)' : 'var(--surface-3)',
                color: r.actionId === selectedActionId ? 'var(--gold-bright)' : 'var(--ink-2)',
                border: `1px solid ${r.actionId === selectedActionId ? 'var(--gold)' : 'var(--line)'}`,
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

      {/* Run headline: where we are, how bad it ever gets, who is in it */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 28,
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 8,
          padding: '14px 20px',
          flexWrap: 'wrap',
        }}
      >
        <div>
          <div className="circe-label" style={{ color: 'var(--ink-2)' }}>
            ELAPSED
          </div>
          <div style={{ color: 'var(--ink)', fontSize: 34, fontWeight: 700, lineHeight: 1.05 }}>
            T+{currentStep?.timeSeconds ?? 0}
            <span style={{ fontSize: 15, color: 'var(--ink-3)', fontWeight: 600 }}>s</span>
          </div>
          <div style={{ color: 'var(--ink-3)', fontSize: 11.5, marginTop: 3 }}>
            step {stepIndex + 1} of {maxStep + 1} · seed {trajectory.seed}
          </div>
        </div>

        <div>
          <div className="circe-label" style={{ color: 'var(--ink-2)' }}>
            PEAK SEVERITY THIS RUN
          </div>
          <div
            style={{
              color: severityRamp(peakSeverity).ink,
              fontSize: 34,
              fontWeight: 700,
              lineHeight: 1.05,
            }}
          >
            {(peakSeverity * 100).toFixed(0)}
            <span style={{ fontSize: 15, fontWeight: 600 }}>%</span>
          </div>
          <div style={{ color: 'var(--ink-3)', fontSize: 11.5, marginTop: 3 }}>
            of the egress-impairment threshold
          </div>
        </div>

        <div>
          <div className="circe-label" style={{ color: 'var(--ink-2)' }}>
            CREW IN ELEVATED SMOKE
          </div>
          <div
            style={{
              color: crewInDanger > 0 ? 'var(--ember)' : 'var(--good-bright)',
              fontSize: 34,
              fontWeight: 700,
              lineHeight: 1.05,
            }}
          >
            {crewInDanger > 0 ? '▲' : '✓'} {crewInDanger}
          </div>
          <div style={{ color: 'var(--ink-3)', fontSize: 11.5, marginTop: 3 }}>at this step</div>
        </div>
      </div>

      {/* Transport */}
      <div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 8,
            flexWrap: 'wrap',
          }}
        >
          <button
            onClick={handlePlayPause}
            style={{
              background: playing ? 'var(--ember)' : 'var(--gold-dim)',
              color: playing ? 'var(--ember)' : 'var(--gold-bright)',
              border: `1px solid ${playing ? 'var(--ember)' : 'var(--gold)'}`,
              borderRadius: 6,
              padding: '6px 16px',
              fontSize: 13,
              fontWeight: 700,
              cursor: 'pointer',
              minWidth: 96,
            }}
          >
            {isRunning ? 'PAUSE' : atEnd ? 'REPLAY' : 'PLAY'}
          </button>

          <button
            onClick={() => {
              setPlaying(false)
              setStepIndex(0)
            }}
            title="Back to the start"
            style={{
              background: 'var(--surface-3)',
              color: 'var(--ink-2)',
              border: '1px solid var(--line)',
              borderRadius: 6,
              padding: '6px 12px',
              fontSize: 13,
              cursor: 'pointer',
            }}
          >
            RESTART
          </button>

          <div style={{ display: 'flex', gap: 4 }}>
            {[0.5, 1, 2].map((option) => (
              <button
                key={option}
                onClick={() => setSpeed(option)}
                style={{
                  background: speed === option ? 'var(--gold-wash)' : 'var(--surface-3)',
                  color: speed === option ? 'var(--gold-bright)' : 'var(--ink-3)',
                  border: `1px solid ${speed === option ? 'var(--gold)' : 'var(--line)'}`,
                  borderRadius: 5,
                  padding: '5px 9px',
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {option}x
              </button>
            ))}
          </div>

          <span style={{ color: 'var(--ink-3)', fontSize: 12, marginLeft: 'auto' }}>
            {trajectory.steps[maxStep]?.timeSeconds}s total
          </span>
        </div>

        <input
          type="range"
          min={0}
          max={maxStep}
          value={stepIndex}
          onChange={(e) => {
            // Taking the slider hands over control; carrying on playing would
            // yank it straight back.
            setPlaying(false)
            setStepIndex(parseInt(e.target.value))
          }}
          style={{ width: '100%', accentColor: 'var(--gold)' }}
        />

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
          <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>
            {isRunning ? 'Playing' : 'Drag, or press Play'}
          </span>
          <span style={{ color: 'var(--ink-3)', fontSize: 11.5 }}>
            step {stepIndex + 1} / {maxStep + 1}
          </span>
        </div>
      </div>

      {/* Events at this step */}
      {currentStep && currentStep.events.length > 0 && (
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderLeft: '3px solid var(--gold)',
            borderRadius: 6,
            padding: '8px 12px',
          }}
        >
          {currentStep.events.map((ev, i) => (
            <div key={i} style={{ color: 'var(--ink)', fontSize: 12, padding: '2px 0' }}>
              <span style={{ color: 'var(--ink-4)', marginRight: 8 }}>T+{currentStep.timeSeconds}s</span>
              {ev}
            </div>
          ))}
        </div>
      )}

      {/* Module states — severity trend per module */}
      {currentStep && (
        <div>
          <SectionTitle>SEVERITY OVER TIME — per module</SectionTitle>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 10,
            }}
          >
            {Object.entries(currentStep.moduleStates).map(([modId, state]) => {
              const mod = scenario.modules[modId]
              const hasEmergency = scenario.emergency?.affectedModuleId === modId
              const ramp = severityRamp(state.hazardSeverity)
              const series = trajectory.steps.map(
                (s) => s.moduleStates[modId]?.hazardSeverity ?? 0
              )
              const previous = previousStep?.moduleStates[modId]?.hazardSeverity ?? null
              const delta =
                previous === null ? null : state.hazardSeverity - previous

              return (
                <div
                  key={modId}
                  style={{
                    background: 'var(--surface-3)',
                    border: `1px solid ${state.hazardSeverity > 0.2 ? ramp.fill : 'var(--line)'}`,
                    borderRadius: 8,
                    padding: '12px 14px',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      marginBottom: 8,
                    }}
                  >
                    <span style={{ color: 'var(--ink)', fontWeight: 600, fontSize: 13 }}>
                      {mod?.name ?? modId}
                      {hasEmergency && (
                        <span
                          className="mono"
                          style={{ marginLeft: 8, fontSize: 9, color: 'var(--ember)' }}
                        >
                          {scenario.emergency?.type === 'electronic_short' ? 'SHORT' : 'FIRE'}
                        </span>
                      )}
                    </span>
                    <span
                      style={{
                        color: ramp.ink,
                        fontSize: 9,
                        fontWeight: 700,
                        letterSpacing: '0.05em',
                        border: `1px solid ${ramp.fill}`,
                        borderRadius: 3,
                        padding: '1px 6px',
                      }}
                    >
                      {ramp.label}
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: 12 }}>
                    <div>
                      <div
                        style={{
                          color: ramp.ink,
                          fontSize: 32,
                          fontWeight: 700,
                          lineHeight: 1.05,
                        }}
                      >
                        {(state.hazardSeverity * 100).toFixed(0)}
                        <span style={{ fontSize: 14, fontWeight: 600 }}>%</span>
                      </div>
                      {delta !== null && (
                        <div
                          style={{
                            color:
                              delta > 0.005
                                ? 'var(--ember)'
                                : delta < -0.005
                                ? 'var(--good-bright)'
                                : 'var(--ink-2)',
                            fontSize: 12,
                            fontWeight: 600,
                          }}
                        >
                          {delta > 0.005 ? '▲' : delta < -0.005 ? '▼' : '—'}{' '}
                          {Math.abs(delta * 100).toFixed(0)}% vs previous step
                        </div>
                      )}
                    </div>
                    <div style={{ marginLeft: 'auto' }}>
                      <Sparkline
                        values={series}
                        currentIndex={stepIndex}
                        accent={ramp.fill}
                      />
                    </div>
                  </div>

                  <Meter
                    ratio={state.hazardSeverity}
                    fill={ramp.fill}
                    track={ramp.track}
                    height={6}
                  />

                  <div
                    style={{
                      marginTop: 10,
                      paddingTop: 8,
                      borderTop: '1px solid var(--line)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                    }}
                  >
                    <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>Crew present</span>
                    <span
                      style={{
                        color:
                          state.crewPresent === 0
                            ? 'var(--ink-4)'
                            : state.hazardSeverity > 0.2
                            ? 'var(--ember)'
                            : 'var(--ink)',
                        fontSize: 22,
                        fontWeight: 700,
                        lineHeight: 1,
                      }}
                    >
                      {state.crewPresent > 0 && state.hazardSeverity > 0.2 ? '▲ ' : ''}
                      {state.crewPresent}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Crew outcome for this action */}
      {crewMembers.length > 0 && (
        <div>
          <SectionTitle>CREW STATUS — end of this run</SectionTitle>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
              gap: 8,
            }}
          >
            {crewMembers.map(([id, member]) => {
              const status = look(CREW_LOOK, member.status)
              return (
                <div
                  key={id}
                  style={{
                    background: 'var(--surface-3)',
                    border: `1px solid ${status.border}`,
                    borderRadius: 6,
                    padding: '10px 12px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  <div>
                    <div style={{ color: 'var(--ink)', fontSize: 13, fontWeight: 600 }}>
                      {nameOfCrew(scenario, id)}
                    </div>
                    <div style={{ color: 'var(--ink-2)', fontSize: 12 }}>
                      {member.exposureExampleSeconds > 0
                        ? `${member.exposureExampleSeconds}s exposed to smoke`
                        : 'no smoke exposure'}
                    </div>
                  </div>
                  <StatusPill status={status} />
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Equipment outcome for this action */}
      {equipment.length > 0 && (
        <div>
          <SectionTitle>
            EQUIPMENT DAMAGE — {equipmentHit.length} of {equipment.length} affected
          </SectionTitle>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
              gap: 8,
            }}
          >
            {equipment.map(([id, item]) => {
              const status = look(EQUIPMENT_LOOK, item.state)
              const affected = DAMAGED_STATES.includes(item.state)
              return (
                <div
                  key={id}
                  style={{
                    background: 'var(--surface-3)',
                    border: `1px solid ${affected ? status.border : 'var(--line)'}`,
                    borderRadius: 6,
                    padding: '10px 12px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                    opacity: affected ? 1 : 0.65,
                  }}
                >
                  <span style={{ color: 'var(--ink)', fontSize: 12, fontWeight: 500 }}>
                    {item.name}
                  </span>
                  <StatusPill status={status} />
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Full event log */}
      <div>
        <SectionTitle>FULL EVENT LOG</SectionTitle>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--line)', borderRadius: 6, padding: '8px 12px' }}>
          {trajectory.steps.map((step) =>
            step.events.map((ev, i) => (
              <div
                key={`${step.stepIndex}-${i}`}
                style={{
                  padding: '3px 0',
                  borderBottom: '1px solid var(--surface-2)',
                  display: 'flex',
                  gap: 12,
                  fontSize: 12.5,
                  opacity: step.stepIndex > stepIndex ? 0.45 : 1,
                }}
              >
                <span
                  className="mono"
                  style={{ color: 'var(--ink-3)', flexShrink: 0, width: 52 }}
                >
                  T+{step.timeSeconds}s
                </span>
                <span style={{ color: 'var(--ink)' }}>{ev}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function nameOfCrew(scenario: SpacecraftScenario, crewId: string): string {
  for (const mod of Object.values(scenario.modules)) {
    const found = mod.crew.find((c) => c.id === crewId)
    if (found) return found.name
  }
  return crewId
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        color: 'var(--ink-2)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        fontWeight: 500,
        letterSpacing: '.16em',
        marginBottom: 10,
      }}
    >
      {children}
    </div>
  )
}
