/**
 * BuilderToolbar — top toolbar for the spacecraft builder canvas.
 */

import { useState } from 'react'
import { useScenarioStore } from '../../store/useScenarioStore'
import { useSimulationStore } from '../../store/useSimulationStore'
import { simulatorClient } from '../../api/simulatorClient'
import EmergencyInjector from '../emergency/EmergencyInjector'

interface Props {
  selectedModuleId: string | null
  selectedConnectionId: string | null
  onDeselect: () => void
  onResultsReady: () => void
}

export default function BuilderToolbar({
  selectedModuleId,
  selectedConnectionId,
  onDeselect,
  onResultsReady,
}: Props) {
  const { scenario, addModule, removeModule, removeConnection, setScenarioName } =
    useScenarioStore()
  const { startLoading, setResult, setError, status } = useSimulationStore()
  const [injectorOpen, setInjectorOpen] = useState(false)

  const moduleCount = Object.keys(scenario.modules).length
  const hasEmergency = !!scenario.emergency
  const hasValidEmergency =
    !!scenario.emergency && !!scenario.modules[scenario.emergency.affectedModuleId]
  const canAnalyze =
    hasValidEmergency &&
    moduleCount > 0 &&
    status !== 'loading'

  function handleAddModule() {
    // Add near center with slight random offset to avoid overlap
    const x = 200 + Math.random() * 200
    const y = 150 + Math.random() * 150
    addModule({ x, y })
  }

  function handleDelete() {
    if (selectedModuleId) {
      removeModule(selectedModuleId)
      onDeselect()
    } else if (selectedConnectionId) {
      removeConnection(selectedConnectionId)
      onDeselect()
    }
  }

  async function handleAnalyze() {
    if (!scenario.emergency) return
    startLoading()
    try {
      const result = await simulatorClient.simulate({
        scenario,
        emergency: scenario.emergency,
        actions: null,
        runs: 200,
        seed: 42,
      })
      setResult(result)
      onResultsReady()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed')
    }
  }

  const btnBase: React.CSSProperties = {
    background: '#1e2128',
    color: '#94a3b8',
    border: '1px solid #2a2d36',
    borderRadius: 5,
    padding: '6px 12px',
    fontSize: 12,
    cursor: 'pointer',
    fontWeight: 500,
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    whiteSpace: 'nowrap',
  }

  return (
    <>
      <div
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10,
          background: '#111318',
          borderBottom: '1px solid #2a2d36',
          padding: '8px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        {/* Scenario name */}
        <input
          style={{
            background: 'transparent',
            border: 'none',
            color: '#e2e8f0',
            fontSize: 14,
            fontWeight: 600,
            outline: 'none',
            width: 220,
            padding: '2px 4px',
            borderBottom: '1px solid transparent',
          }}
          value={scenario.name}
          onChange={(e) => setScenarioName(e.target.value)}
          onFocus={(e) => (e.target.style.borderBottomColor = '#3b82f6')}
          onBlur={(e) => (e.target.style.borderBottomColor = 'transparent')}
        />

        <div style={{ width: 1, height: 24, background: '#2a2d36', flexShrink: 0 }} />

        {/* Add module */}
        <button style={btnBase} onClick={handleAddModule}>
          <span style={{ color: '#22c55e', fontWeight: 700 }}>+</span> Module
        </button>

        {/* Delete selected */}
        <button
          style={{
            ...btnBase,
            color: (selectedModuleId || selectedConnectionId) ? '#ef4444' : '#2a2d36',
            cursor: (selectedModuleId || selectedConnectionId) ? 'pointer' : 'default',
          }}
          onClick={handleDelete}
          disabled={!selectedModuleId && !selectedConnectionId}
        >
          🗑 Delete
        </button>

        <div style={{ width: 1, height: 24, background: '#2a2d36', flexShrink: 0 }} />

        {/* Emergency injector */}
        <button
          style={{
            ...btnBase,
            color: hasEmergency ? '#fca5a5' : '#94a3b8',
            borderColor: hasEmergency ? '#7f1d1d' : '#2a2d36',
            background: hasEmergency ? '#450a0a' : '#1e2128',
          }}
          onClick={() => setInjectorOpen(true)}
          disabled={moduleCount === 0}
        >
          🔥 {hasEmergency ? 'Emergency Active' : 'Inject Emergency'}
        </button>

        {/* Spacer */}
        <div style={{ flex: 1 }} />

        {/* Module count */}
        <span style={{ color: '#475569', fontSize: 11 }}>
          {moduleCount} module{moduleCount !== 1 ? 's' : ''}
        </span>

        {/* Analyze button */}
        <button
          onClick={handleAnalyze}
          disabled={!canAnalyze}
          style={{
            background: canAnalyze ? '#1d4ed8' : '#1e2128',
            color: canAnalyze ? '#e0f2fe' : '#374151',
            border: `1px solid ${canAnalyze ? '#3b82f6' : '#374151'}`,
            borderRadius: 6,
            padding: '7px 18px',
            fontSize: 13,
            fontWeight: 700,
            cursor: canAnalyze ? 'pointer' : 'not-allowed',
            letterSpacing: '0.03em',
          }}
        >
          {status === 'loading' ? '⟳ Analyzing…' : '⚡ ANALYZE EMERGENCY'}
        </button>
      </div>

      {injectorOpen && (
        <EmergencyInjector isOpen onClose={() => setInjectorOpen(false)} />
      )}
    </>
  )
}
