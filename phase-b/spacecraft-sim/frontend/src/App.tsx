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
import BlueprintView from './components/builder/BlueprintView'
import ResultsPage from './components/results/ResultsPage'
import './styles/index.css'

type View = 'landing' | 'builder' | 'results'

export default function App() {
  const [view, setView] = useState<View>('landing')
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null)
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null)
  const [blueprintOpen, setBlueprintOpen] = useState(true)

  const {
    status: simStatus,
    error: simError,
    progress: simProgress,
    reset: resetSim,
  } = useSimulationStore()
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
    <div style={{ width: '100vw', height: '100vh', overflow: 'hidden', position: 'relative', background: 'var(--void)' }}>
      {/* Loading overlay */}
      {simStatus === 'loading' && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(7, 8, 11, .93)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 500,
            gap: 14,
          }}
        >
          <div
            className="circe-label"
            style={{ color: 'var(--gold)', letterSpacing: '.28em' }}
          >
            EXPLORING FUTURES
          </div>
          <div
            className="circe-display"
            style={{ color: 'var(--ink)', fontSize: 34, letterSpacing: '.02em' }}
          >
            Where each decision leads
          </div>

          {/* Which action is being simulated, and how far through. The bar
              tracks completed actions, so it stalls visibly if one is slow
              rather than sliding on toward a finish it has not reached. */}
          <div style={{ width: 340, maxWidth: '80vw' }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                marginBottom: 6,
              }}
            >
              <span style={{ color: 'var(--ink)', fontSize: 12.5, fontWeight: 400 }}>
                {simProgress ? simProgress.label : 'Generating candidate actions'}
              </span>
              <span className="mono" style={{ color: 'var(--gold)', fontSize: 12 }}>
                {simProgress ? `${simProgress.percent}%` : ''}
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
                  width: `${simProgress?.percent ?? 0}%`,
                  height: '100%',
                  background: 'var(--gold)',
                  transition: 'width .3s ease',
                }}
              />
            </div>

            <div
              style={{
                color: 'var(--ink-3)',
                fontSize: 11,
                fontFamily: 'var(--font-mono)',
                marginTop: 8,
                textAlign: 'center',
                letterSpacing: '.06em',
              }}
            >
              {simProgress
                ? `Action ${Math.min(simProgress.done + 1, simProgress.total)} of ${simProgress.total} · 200 sampled scenarios each`
                : 'Running sampled scenarios on the Phase A engine'}
            </div>
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
            background: 'var(--surface)',
            border: '1px solid var(--ember)',
            borderRadius: 8,
            padding: '12px 20px',
            color: 'var(--ember)',
            fontSize: 12.5,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}
        >
          <span>{simError ?? 'The simulation did not complete.'}</span>
          <button
            onClick={resetSim}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--ink-2)',
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
        blueprintOpen={blueprintOpen}
        onToggleBlueprint={() => setBlueprintOpen((open) => !open)}
      />

      {/* Canvas — offset by toolbar height (48px). The deck plan shares the
          area rather than overlaying it, so both views stay fully visible. */}
      <div
        style={{
          position: 'absolute',
          top: 52,
          left: 0,
          right: selectedModuleId || selectedConnectionId ? 320 : 0,
          bottom: 0,
          transition: 'right 0.2s ease',
          display: 'flex',
        }}
      >
        <div style={{ flex: 1, minWidth: 0, position: 'relative' }}>
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

        {blueprintOpen && (
          <div
            style={{
              width: '42%',
              minWidth: 320,
              maxWidth: 720,
              borderLeft: '1px solid var(--line)',
              flexShrink: 0,
            }}
          >
            <BlueprintView
              selectedModuleId={selectedModuleId}
              selectedConnectionId={selectedConnectionId}
              onModuleSelect={setSelectedModuleId}
              onConnectionSelect={setSelectedConnectionId}
            />
          </div>
        )}
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
          background: 'var(--surface)',
          border: '1px solid var(--line)',
          borderRadius: 3,
          padding: '5px 12px',
          color: 'var(--ink-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 10,
          letterSpacing: '.14em',
          cursor: 'pointer',
        }}
      >
        ← START OVER
      </button>

      <style>{`
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
