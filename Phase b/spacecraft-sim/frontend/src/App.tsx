/**
 * App — root component handling view routing.
 *
 * Views: landing | builder | results
 * No router library — simple state-based navigation for a single-page app.
 */

import { useState } from 'react'
import { useSimulationStore } from './store/useSimulationStore'
import { useScenarioStore } from './store/useScenarioStore'
import LandingPage from './components/landing/LandingPage'
import SpacecraftCanvas from './components/builder/SpacecraftCanvas'
import BuilderToolbar from './components/builder/BuilderToolbar'
import InspectorPanel from './components/builder/InspectorPanel'
import ResultsPage from './components/results/ResultsPage'
import './styles/index.css'

type View = 'landing' | 'builder' | 'results'

export default function App() {
  const [view, setView] = useState<View>('landing')
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null)
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null)

  const { status: simStatus, error: simError, reset: resetSim } = useSimulationStore()
  const { resetScenario } = useScenarioStore()

  function handleDeselect() {
    setSelectedModuleId(null)
    setSelectedConnectionId(null)
  }

  function handleResultsReady() {
    setView('results')
  }

  function handleBackToBuilder() {
    setView('builder')
  }

  function handleBackToLanding() {
    resetScenario()
    resetSim()
    setSelectedModuleId(null)
    setSelectedConnectionId(null)
    setView('landing')
  }

  if (view === 'landing') {
    return <LandingPage onStart={() => setView('builder')} />
  }

  if (view === 'results') {
    return <ResultsPage onBack={handleBackToBuilder} />
  }

  // Builder view
  return (
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden', position: 'relative', background: '#0a0c10' }}>
      {/* Loading overlay */}
      {simStatus === 'loading' && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(10, 12, 16, 0.85)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 500,
            gap: 16,
          }}
        >
          <div
            style={{
              width: 40,
              height: 40,
              border: '3px solid #1d4ed8',
              borderTop: '3px solid #3b82f6',
              borderRadius: '50%',
              animation: 'spin 0.8s linear infinite',
            }}
          />
          <div style={{ color: '#e2e8f0', fontSize: 16, fontWeight: 600 }}>
            Analyzing Emergency…
          </div>
          <div style={{ color: '#64748b', fontSize: 12 }}>
            Running sampled scenarios on the Phase A engine
          </div>
        </div>
      )}

      {/* Error banner */}
      {simStatus === 'error' && (
        <div
          style={{
            position: 'fixed',
            top: 60,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 300,
            background: '#450a0a',
            border: '1px solid #ef4444',
            borderRadius: 8,
            padding: '12px 20px',
            color: '#fca5a5',
            fontSize: 13,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>⚠ {simError ?? 'Simulation error.'}</span>
          <button
            onClick={resetSim}
            style={{
              background: 'none',
              border: 'none',
              color: '#3b82f6',
              cursor: 'pointer',
              fontSize: 12,
            }}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Toolbar */}
      <BuilderToolbar
        selectedModuleId={selectedModuleId}
        selectedConnectionId={selectedConnectionId}
        onDeselect={handleDeselect}
        onResultsReady={handleResultsReady}
      />

      {/* Canvas — offset by toolbar height (48px) */}
      <div
        style={{
          position: 'absolute',
          top: 48,
          left: 0,
          right: selectedModuleId || selectedConnectionId ? 320 : 0,
          bottom: 0,
          transition: 'right 0.2s ease',
        }}
      >
        <SpacecraftCanvas
          onModuleSelect={(id) => {
            setSelectedModuleId(id)
            if (id) setSelectedConnectionId(null)
          }}
          onConnectionSelect={(id) => {
            setSelectedConnectionId(id)
            if (id) setSelectedModuleId(null)
          }}
          selectedModuleId={selectedModuleId}
          selectedConnectionId={selectedConnectionId}
        />
      </div>

      {/* Inspector panel */}
      <InspectorPanel
        selectedModuleId={selectedModuleId}
        selectedConnectionId={selectedConnectionId}
        onClose={handleDeselect}
      />

      {/* Back to landing (top-left when builder is shown) */}
      <button
        onClick={handleBackToLanding}
        style={{
          position: 'absolute',
          bottom: 16,
          left: 16,
          zIndex: 20,
          background: '#111318',
          border: '1px solid #2a2d36',
          borderRadius: 5,
          padding: '4px 12px',
          color: '#475569',
          fontSize: 11,
          cursor: 'pointer',
        }}
      >
        ← Home
      </button>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
