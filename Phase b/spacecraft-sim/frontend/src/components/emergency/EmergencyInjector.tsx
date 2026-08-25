/**
 * EmergencyInjector — dialog for injecting a fire emergency into a module.
 *
 * Phase B supports one active fire emergency only.
 * No decompression, radiation, medical events — extensible but Phase B = fire only.
 */

import { useState } from 'react'
import { useScenarioStore } from '../../store/useScenarioStore'

interface Props {
  isOpen: boolean
  onClose: () => void
}

export default function EmergencyInjector({ isOpen, onClose }: Props) {
  const { scenario, setEmergency } = useScenarioStore()

  const moduleList = Object.values(scenario.modules)
  const [selectedModuleId, setSelectedModuleId] = useState(
    scenario.emergency?.affectedModuleId ?? moduleList[0]?.id ?? ''
  )
  const [detected, setDetected] = useState(scenario.emergency?.detected ?? true)
  const [sourceProfileId, setSourceProfileId] = useState(scenario.emergency?.sourceProfileId ?? '')

  if (!isOpen) return null

  function handleInject() {
    if (!selectedModuleId || !scenario.modules[selectedModuleId]) return
    setEmergency({
      type: 'fire',
      affectedModuleId: selectedModuleId,
      detected,
      sourceProfileId: sourceProfileId || null,
    })
    onClose()
  }

  function handleClear() {
    setEmergency(null)
    onClose()
  }

  const hasEmergency = !!scenario.emergency

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 200,
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        style={{
          background: '#1e2128',
          border: '1px solid #2a2d36',
          borderRadius: 10,
          padding: 24,
          width: 380,
          maxWidth: '90vw',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ margin: 0, color: '#e2e8f0', fontSize: 18, fontWeight: 600 }}>
            🔥 Inject Emergency
          </h2>
          <p style={{ margin: '4px 0 0', color: '#64748b', fontSize: 12 }}>
            Phase B: fire emergencies only
          </p>
        </div>

        {moduleList.length === 0 ? (
          <div style={{ color: '#94a3b8', fontSize: 13 }}>
            Add at least one module before injecting an emergency.
          </div>
        ) : (
          <>
            {/* Module selector */}
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Affected Module</label>
              <select
                style={inputStyle}
                value={selectedModuleId}
                onChange={(e) => setSelectedModuleId(e.target.value)}
              >
                {moduleList.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>

            {/* Detected toggle */}
            <div style={{ marginBottom: 14, display: 'flex', alignItems: 'center', gap: 10 }}>
              <input
                type="checkbox"
                id="detected-toggle"
                checked={detected}
                onChange={(e) => setDetected(e.target.checked)}
                style={{ accentColor: '#3b82f6', width: 14, height: 14 }}
              />
              <label
                htmlFor="detected-toggle"
                style={{ color: '#94a3b8', fontSize: 13, cursor: 'pointer' }}
              >
                Fire detected by crew / systems
              </label>
            </div>

            {/* Source profile (optional) */}
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>Source Profile ID (optional)</label>
              <input
                style={inputStyle}
                placeholder="e.g. electrical-short, chemical-ignition"
                value={sourceProfileId}
                onChange={(e) => setSourceProfileId(e.target.value)}
              />
              <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
                Used by Phase A simulator for source-specific propagation
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleInject}
                style={{
                  flex: 1,
                  background: '#7f1d1d',
                  color: '#fca5a5',
                  border: '1px solid #ef4444',
                  borderRadius: 6,
                  padding: '8px 16px',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                🔥 Inject Fire
              </button>
              {hasEmergency && (
                <button
                  onClick={handleClear}
                  style={{
                    background: '#1e2128',
                    color: '#94a3b8',
                    border: '1px solid #2a2d36',
                    borderRadius: 6,
                    padding: '8px 14px',
                    fontSize: 13,
                    cursor: 'pointer',
                  }}
                >
                  Clear
                </button>
              )}
              <button
                onClick={onClose}
                style={{
                  background: 'none',
                  color: '#64748b',
                  border: '1px solid #2a2d36',
                  borderRadius: 6,
                  padding: '8px 14px',
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  color: '#64748b',
  fontSize: 11,
  marginBottom: 4,
  letterSpacing: '0.04em',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: '#0a0c10',
  border: '1px solid #2a2d36',
  borderRadius: 4,
  color: '#e2e8f0',
  fontSize: 12,
  padding: '5px 8px',
  outline: 'none',
}
