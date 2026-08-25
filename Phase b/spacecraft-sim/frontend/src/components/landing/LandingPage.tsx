/**
 * LandingPage — entry point for the application.
 *
 * Two choices:
 *   "Build New Spacecraft" — empty canvas
 *   "Load 5-Module Demo"  — loads the demo fixture from the API
 */

import { useState } from 'react'
import { fetchTemplate } from '../../api/simulatorClient'
import { useScenarioStore } from '../../store/useScenarioStore'
import type { EmergencyConfig, SpacecraftScenario } from '../../types/scenario'

interface Props {
  onStart: () => void
}

export default function LandingPage({ onStart }: Props) {
  const { loadScenario, setEmergency, addModule } = useScenarioStore()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleLoadDemo() {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchTemplate('five-module-demo')
      // The fixture has emergency embedded at the top level
      const { emergency, ...scenarioFields } = data as SpacecraftScenario & { emergency?: EmergencyConfig }
      loadScenario(scenarioFields as SpacecraftScenario)
      if (emergency) {
        setEmergency(emergency)
      }
      onStart()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load demo')
    } finally {
      setLoading(false)
    }
  }

  function handleNewSpacecraft() {
    addModule({ x: 300, y: 250 })
    onStart()
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        background: '#0a0c10',
        padding: 40,
      }}
    >
      {/* Title block */}
      <div style={{ textAlign: 'center', marginBottom: 48 }}>
        <div
          style={{
            color: '#3b82f6',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.14em',
            marginBottom: 12,
          }}
        >
          IBM AI BUILDERS CHALLENGE · PHASE B
        </div>
        <h1
          style={{
            margin: 0,
            color: '#e2e8f0',
            fontSize: 36,
            fontWeight: 700,
            letterSpacing: '-0.01em',
            lineHeight: 1.2,
          }}
        >
          Spacecraft Emergency
          <br />
          <span style={{ color: '#3b82f6' }}>Decision-Support Sandbox</span>
        </h1>
        <p
          style={{
            marginTop: 16,
            color: '#64748b',
            fontSize: 14,
            maxWidth: 520,
            lineHeight: 1.6,
          }}
        >
          Build an arbitrary spacecraft topology, inject a fire emergency, and
          analyze simulated action outcomes side-by-side.
        </p>
        <div
          style={{
            marginTop: 14,
            display: 'inline-block',
            background: '#1a1d24',
            border: '1px solid #2a2d36',
            borderLeft: '3px solid #f59e0b',
            borderRadius: 4,
            padding: '6px 12px',
            fontSize: 11,
            color: '#94a3b8',
          }}
        >
          ⚠ Phase A engine connected — real-unit PoC simulation, not a validated NASA model.
        </div>
      </div>

      {/* Workflow steps */}
      <div
        style={{
          display: 'flex',
          gap: 8,
          alignItems: 'center',
          marginBottom: 40,
          flexWrap: 'wrap',
          justifyContent: 'center',
        }}
      >
        {[
          'Build spacecraft',
          '→',
          'Configure',
          '→',
          'Inject emergency',
          '→',
          'ANALYZE',
          '→',
          'Compare actions',
        ].map((step, i) => (
          <span
            key={i}
            style={{
              color: step === '→' ? '#2a2d36' : step === 'ANALYZE' ? '#3b82f6' : '#64748b',
              fontSize: step === 'ANALYZE' ? 13 : 12,
              fontWeight: step === 'ANALYZE' ? 700 : 400,
              letterSpacing: step === 'ANALYZE' ? '0.05em' : 0,
            }}
          >
            {step}
          </span>
        ))}
      </div>

      {/* Action cards */}
      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap', justifyContent: 'center' }}>
        {/* Build New */}
        <button
          onClick={handleNewSpacecraft}
          style={{
            background: '#1e2128',
            border: '2px solid #2a2d36',
            borderRadius: 12,
            padding: '28px 36px',
            cursor: 'pointer',
            textAlign: 'left',
            width: 260,
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#3b82f6')}
          onMouseLeave={(e) => (e.currentTarget.style.borderColor = '#2a2d36')}
        >
          <div style={{ fontSize: 28, marginBottom: 12 }}>🛸</div>
          <div style={{ color: '#e2e8f0', fontWeight: 700, fontSize: 16, marginBottom: 6 }}>
            Build New Spacecraft
          </div>
          <div style={{ color: '#64748b', fontSize: 12, lineHeight: 1.5 }}>
            Start from scratch. Add modules, connect them, assign crew and equipment, then
            inject an emergency.
          </div>
        </button>

        {/* Load Demo */}
        <button
          onClick={handleLoadDemo}
          disabled={loading}
          style={{
            background: '#1a2540',
            border: '2px solid #1d4ed8',
            borderRadius: 12,
            padding: '28px 36px',
            cursor: loading ? 'wait' : 'pointer',
            textAlign: 'left',
            width: 260,
            opacity: loading ? 0.7 : 1,
            transition: 'border-color 0.15s',
          }}
          onMouseEnter={(e) => !loading && (e.currentTarget.style.borderColor = '#3b82f6')}
          onMouseLeave={(e) => !loading && (e.currentTarget.style.borderColor = '#1d4ed8')}
        >
          <div style={{ fontSize: 28, marginBottom: 12 }}>🔥</div>
          <div style={{ color: '#bfdbfe', fontWeight: 700, fontSize: 16, marginBottom: 6 }}>
            {loading ? 'Loading…' : 'Load 5-Module Demo'}
          </div>
          <div style={{ color: '#64748b', fontSize: 12, lineHeight: 1.5 }}>
            5 modules, 4 crew, fire in Storage. Ready to analyze immediately.
            Demo — same code path as user-created scenarios.
          </div>
        </button>
      </div>

      {error && (
        <div
          style={{
            marginTop: 20,
            background: '#450a0a',
            border: '1px solid #7f1d1d',
            borderRadius: 6,
            padding: '10px 16px',
            color: '#fca5a5',
            fontSize: 13,
          }}
        >
          {error}
        </div>
      )}

      {/* Footer */}
      <div
        style={{
          position: 'absolute',
          bottom: 20,
          color: '#1e2128',
          fontSize: 11,
          textAlign: 'center',
        }}
      >
        Built with IBM Bob · IBM AI Builders Challenge
      </div>
    </div>
  )
}
