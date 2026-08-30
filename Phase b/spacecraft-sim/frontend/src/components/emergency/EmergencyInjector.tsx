/**
 * EmergencyInjector — inject fire or electronic-short damage into a module.
 */

import { useEffect, useMemo, useState } from 'react'
import { useScenarioStore } from '../../store/useScenarioStore'
import type { EmergencyConfig } from '../../types/scenario'
import { escapeRouteCandidates, recommendedEscapeRoute } from '../../domain/escapeRouting'

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
  const [emergencyType, setEmergencyType] = useState<EmergencyConfig['type']>(
    scenario.emergency?.type ?? 'fire'
  )
  const [sourceProfileId, setSourceProfileId] = useState(scenario.emergency?.sourceProfileId ?? '')
  const candidates = useMemo(
    () => selectedModuleId ? escapeRouteCandidates(scenario, selectedModuleId) : [],
    [scenario, selectedModuleId],
  )
  const recommended = useMemo(
    () => selectedModuleId ? recommendedEscapeRoute(scenario, selectedModuleId) : null,
    [scenario, selectedModuleId],
  )
  const existingTarget = scenario.emergency?.escapeTarget
  const existingKey = existingTarget
    ? `${existingTarget.connectionId}|${existingTarget.fromModuleId}|${existingTarget.toModuleId}`
    : ''
  const recommendedKey = recommended
    ? `${recommended.connectionId}|${recommended.fromModuleId}|${recommended.toModuleId}`
    : ''
  const [escapeTargetKey, setEscapeTargetKey] = useState(existingKey || recommendedKey)
  const totalCrew = moduleList.reduce((total, module) => total + module.crew.length, 0)
  const [maxOccupants, setMaxOccupants] = useState(
    existingTarget?.maxOccupants ?? Math.max(1, totalCrew),
  )

  useEffect(() => {
    setEscapeTargetKey(recommendedKey)
  }, [selectedModuleId, recommendedKey])

  useEffect(() => {
    setMaxOccupants(existingTarget?.maxOccupants ?? Math.max(1, totalCrew))
  }, [existingTarget?.maxOccupants, totalCrew])

  if (!isOpen) return null

  function handleInject() {
    if (!selectedModuleId || !scenario.modules[selectedModuleId]) return
    const selectedEscape = candidates.find(
      (candidate) => `${candidate.connectionId}|${candidate.fromModuleId}|${candidate.toModuleId}` === escapeTargetKey
    )
    setEmergency({
      type: emergencyType,
      affectedModuleId: selectedModuleId,
      detected,
      sourceProfileId: sourceProfileId || null,
      escapeTarget: selectedEscape?.eligible ? {
        connectionId: selectedEscape.connectionId,
        fromModuleId: selectedEscape.fromModuleId,
        toModuleId: selectedEscape.toModuleId,
        selection: escapeTargetKey === recommendedKey ? 'recommended' : 'manual',
        maxOccupants,
      } : null,
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
          background: 'var(--surface-3)',
          border: '1px solid var(--line)',
          borderRadius: 10,
          padding: 24,
          width: 380,
          maxWidth: '90vw',
        }}
      >
        {/* Header */}
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ margin: 0, color: 'var(--ink)', fontSize: 18, fontWeight: 600 }}>
            Introduce a hazard
          </h2>
          <p style={{ margin: '4px 0 0', color: 'var(--ink-3)', fontSize: 12 }}>
            Fire or electronic short · one active emergency
          </p>
        </div>

        {moduleList.length === 0 ? (
          <div style={{ color: 'var(--ink-2)', fontSize: 13 }}>
            Add at least one module before injecting an emergency.
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 14 }}>
              <label style={labelStyle}>Emergency Type</label>
              <select
                style={inputStyle}
                value={emergencyType}
                onChange={(event) => setEmergencyType(event.target.value as EmergencyConfig['type'])}
              >
                <option value="fire">Fire</option>
                <option value="electronic_short">Electronic Short</option>
              </select>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>Refuge Capacity (crew)</label>
              <input
                aria-label="Refuge capacity"
                type="number"
                min={1}
                max={Math.max(1, totalCrew)}
                step={1}
                style={inputStyle}
                value={maxOccupants}
                onChange={(event) => setMaxOccupants(Math.max(1, Number(event.target.value) || 1))}
              />
              <div style={{ color: 'var(--ink-4)', fontSize: 10.5, marginTop: 5 }}>
                Seats are reserved by the live crew-priority ranking. Excess crew remain outside the refuge.
              </div>
            </div>
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
                style={{ accentColor: 'var(--gold)', width: 14, height: 14 }}
              />
              <label
                htmlFor="detected-toggle"
                style={{ color: 'var(--ink-2)', fontSize: 13, cursor: 'pointer' }}
              >
                {emergencyType === 'fire' ? 'Fire detected by crew / systems' : 'Short detected by crew / systems'}
              </label>
            </div>

            {/* Source profile (optional) */}
            {emergencyType === 'fire' && <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>Source Profile ID (optional)</label>
              <input
                style={inputStyle}
                placeholder="e.g. electrical-short, chemical-ignition"
                value={sourceProfileId}
                onChange={(e) => setSourceProfileId(e.target.value)}
              />
              <div style={{ color: 'var(--ink-4)', fontSize: 11, marginTop: 4 }}>
                Used by Phase A simulator for source-specific propagation
              </div>
            </div>}

            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>Evacuation Target Hatch / Direction</label>
              <select
                aria-label="Evacuation target hatch and direction"
                style={inputStyle}
                value={escapeTargetKey}
                onChange={(event) => setEscapeTargetKey(event.target.value)}
              >
                {!recommended && <option value="">No independently survivable zone</option>}
                {candidates.map((candidate) => {
                  const key = `${candidate.connectionId}|${candidate.fromModuleId}|${candidate.toModuleId}`
                  const from = scenario.modules[candidate.fromModuleId]?.name ?? candidate.fromModuleId
                  const to = scenario.modules[candidate.toModuleId]?.name ?? candidate.toModuleId
                  return (
                    <option key={key} value={key} disabled={!candidate.eligible}>
                      {key === recommendedKey ? 'RECOMMENDED · ' : ''}{from} → {to}
                      {candidate.eligible ? '' : ` · ${candidate.reasons.join(', ')}`}
                    </option>
                  )
                })}
              </select>
              {recommended ? (
                <div style={{ color: 'var(--good)', fontSize: 10.5, marginTop: 5, lineHeight: 1.5 }}>
                  Target zone: {recommended.zoneModuleIds.map((id) => scenario.modules[id]?.name ?? id).join(', ')} · independent power, air and {60}-minute water reserve verified.
                </div>
              ) : (
                <div style={{ color: 'var(--ember)', fontSize: 10.5, marginTop: 5 }}>
                  No direction currently satisfies independent power, air and emergency-water requirements.
                </div>
              )}
            </div>

            <div style={{ color: 'var(--ink-4)', fontSize: 11, lineHeight: 1.5, marginBottom: 14 }}>
              Adjacent hatch connectivity is rolled to 1–50 immediately. Fire then follows air-level feedback; an electronic short also reduces adjacent power transfer to 5–20%.
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 10 }}>
              <button
                onClick={handleInject}
                style={{
                  flex: 1,
                  background: 'var(--ember)',
                  color: 'var(--ember)',
                  border: '1px solid var(--ember)',
                  borderRadius: 6,
                  padding: '8px 16px',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                INTRODUCE HAZARD
              </button>
              {hasEmergency && (
                <button
                  onClick={handleClear}
                  style={{
                    background: 'var(--surface-3)',
                    color: 'var(--ink-2)',
                    border: '1px solid var(--line)',
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
                  color: 'var(--ink-3)',
                  border: '1px solid var(--line)',
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
  color: 'var(--ink-3)',
  fontSize: 11,
  marginBottom: 4,
  letterSpacing: '0.04em',
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--void)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  color: 'var(--ink)',
  fontSize: 12,
  padding: '5px 8px',
  outline: 'none',
}
