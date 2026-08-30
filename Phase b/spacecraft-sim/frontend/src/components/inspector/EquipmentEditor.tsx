/**
 * EquipmentEditor — add/edit/remove equipment within a module.
 *
 * Equipment items have name, type, state, and providesCapabilities.
 * No numeric importance weights — capability provision is semantic.
 */

import { useState } from 'react'
import type { Equipment, EquipmentState } from '../../types/scenario'
import { useScenarioStore } from '../../store/useScenarioStore'
import { defaultEquipmentPortable, defaultEquipmentPowerW } from '../../domain/resourceSizing'

interface Props {
  moduleId: string
  equipment: Equipment[]
}

const EQUIPMENT_TYPES = [
  'life_support', 'power', 'propulsion', 'gnc', 'comms', 'fuel',
  'fire_suppression', 'medical', 'science', 'other',
]

const EQUIPMENT_STATE_OPTIONS: { value: EquipmentState; label: string; color: string }[] = [
  { value: 'operational', label: 'Operational', color: 'var(--good)' },
  { value: 'exposed_at_risk', label: 'Exposed / At Risk', color: 'var(--amber)' },
  { value: 'unavailable', label: 'Unavailable', color: 'var(--ember)' },
  { value: 'explicitly_failed', label: 'Failed', color: 'var(--ember)' },
]

const CAPABILITY_SUGGESTIONS = [
  'habitation', 'co2_removal',
  'thermal_control', 'main_propulsion', 'attitude_control', 'rcs',
  'navigation', 'communications', 'fire_suppression', 'return_capability',
  'emergency_life_support', 'docking',
]

export default function EquipmentEditor({ moduleId, equipment }: Props) {
  const { addEquipment, updateEquipment, removeEquipment } = useScenarioStore()
  const [expandedId, setExpandedId] = useState<string | null>(null)

  function handleAdd() {
    const id = `eq-${crypto.randomUUID().slice(0, 8)}`
    addEquipment(moduleId, {
      id,
      name: 'New Equipment',
      type: 'other',
      state: 'operational',
      providesCapabilities: [],
      powerConsumptionW: defaultEquipmentPowerW('other'),
      portable: defaultEquipmentPortable('other'),
      passageUnits: 1,
    })
    setExpandedId(id)
  }

  function toggleCapability(eqId: string, cap: string, current: string[]) {
    const updated = current.includes(cap)
      ? current.filter((c) => c !== cap)
      : [...current, cap]
    updateEquipment(moduleId, eqId, { providesCapabilities: updated })
  }

  const stateColor = (state: string) =>
    EQUIPMENT_STATE_OPTIONS.find((o) => o.value === state)?.color ?? 'var(--ink-3)'

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
        <span style={{ color: 'var(--ink-2)', fontSize: 11, fontWeight: 600, letterSpacing: '0.06em' }}>
          EQUIPMENT ({equipment.length})
        </span>
        <button
          onClick={handleAdd}
          style={{
            background: 'var(--gold-dim)',
            color: 'var(--gold-bright)',
            border: 'none',
            borderRadius: 4,
            padding: '3px 10px',
            fontSize: 11,
            cursor: 'pointer',
            fontWeight: 600,
          }}
        >
          + Add
        </button>
      </div>

      {equipment.length === 0 && (
        <div style={{ color: 'var(--ink-4)', fontSize: 12, fontStyle: 'italic', padding: '4px 0' }}>
          No equipment assigned
        </div>
      )}

      {equipment.map((eq) => (
        <div
          key={eq.id}
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 6,
            marginBottom: 6,
            overflow: 'hidden',
          }}
        >
          {/* Header row */}
          <div
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 10px', cursor: 'pointer' }}
            onClick={() => setExpandedId(expandedId === eq.id ? null : eq.id)}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: stateColor(eq.state),
                flexShrink: 0,
              }}
            />
            <span style={{ flex: 1, color: 'var(--ink)', fontSize: 12, fontWeight: 500 }}>{eq.name}</span>
            <span style={{ color: 'var(--ink-3)', fontSize: 11 }}>
              {eq.type} · {eq.powerConsumptionW}W
            </span>
            <button
              onClick={(e) => {
                e.stopPropagation()
                removeEquipment(moduleId, eq.id)
              }}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--ember)',
                cursor: 'pointer',
                fontSize: 14,
                padding: '0 2px',
                lineHeight: 1,
              }}
              title="Remove equipment"
            >
              ×
            </button>
          </div>

          {/* Expanded editor */}
          {expandedId === eq.id && (
            <div style={{ padding: '0 10px 10px', borderTop: '1px solid var(--surface-3)' }}>
              <label style={labelStyle}>Name</label>
              <input
                style={inputStyle}
                value={eq.name}
                onChange={(e) => updateEquipment(moduleId, eq.id, { name: e.target.value })}
              />

              <label style={labelStyle}>Type</label>
              <select
                style={inputStyle}
                value={eq.type}
                onChange={(e) => updateEquipment(moduleId, eq.id, {
                  type: e.target.value,
                  powerConsumptionW: defaultEquipmentPowerW(e.target.value),
                  portable: defaultEquipmentPortable(e.target.value),
                })}
              >
                {EQUIPMENT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>

              <label style={labelStyle}>Power Consumption (W)</label>
              <input
                style={inputStyle}
                type="number"
                min="0"
                step="1"
                value={eq.powerConsumptionW}
                onChange={(e) => updateEquipment(moduleId, eq.id, {
                  powerConsumptionW: Math.max(0, Number(e.target.value) || 0),
                })}
              />

              <label style={labelStyle}>Evacuation Passage</label>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                <button
                  type="button"
                  onClick={() => updateEquipment(moduleId, eq.id, { portable: !eq.portable })}
                  style={{
                    ...inputStyle,
                    color: eq.portable ? 'var(--good)' : 'var(--ink-4)',
                    cursor: 'pointer',
                  }}
                >
                  {eq.portable ? 'PORTABLE' : 'FIXED'}
                </button>
                <input
                  aria-label="Passage units"
                  title="Crew-equivalent hatch capacity consumed"
                  style={inputStyle}
                  type="number"
                  min="0.1"
                  step="0.1"
                  value={eq.passageUnits}
                  onChange={(e) => updateEquipment(moduleId, eq.id, {
                    passageUnits: Math.max(0.1, Number(e.target.value) || 0.1),
                  })}
                />
              </div>

              <label style={labelStyle}>State</label>
              <select
                style={{ ...inputStyle, color: stateColor(eq.state) }}
                value={eq.state}
                onChange={(e) =>
                  updateEquipment(moduleId, eq.id, { state: e.target.value as EquipmentState })
                }
              >
                {EQUIPMENT_STATE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} style={{ color: o.color }}>
                    {o.label}
                  </option>
                ))}
              </select>

              <label style={labelStyle}>Provides Capabilities</label>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                {CAPABILITY_SUGGESTIONS.map((cap) => {
                  const active = eq.providesCapabilities.includes(cap)
                  return (
                    <button
                      key={cap}
                      onClick={() => toggleCapability(eq.id, cap, eq.providesCapabilities)}
                      style={{
                        background: active ? 'var(--good)' : 'var(--surface-3)',
                        color: active ? 'var(--good)' : 'var(--ink-3)',
                        border: `1px solid ${active ? 'var(--good)' : 'var(--line)'}`,
                        borderRadius: 4,
                        padding: '2px 8px',
                        fontSize: 11,
                        cursor: 'pointer',
                      }}
                    >
                      {cap}
                    </button>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

const labelStyle: React.CSSProperties = {
  display: 'block',
  color: 'var(--ink-3)',
  fontSize: 11,
  marginTop: 8,
  marginBottom: 3,
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  background: 'var(--void)',
  border: '1px solid var(--line)',
  borderRadius: 4,
  color: 'var(--ink)',
  fontSize: 12,
  padding: '4px 8px',
  outline: 'none',
}
