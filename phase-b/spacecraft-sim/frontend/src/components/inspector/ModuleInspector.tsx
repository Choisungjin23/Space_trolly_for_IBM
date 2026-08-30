/**
 * ModuleInspector — panel for editing a selected module's properties.
 */

import type { ScenarioModule, ModuleType, EmergencyConfig } from '../../types/scenario'
import { useScenarioStore } from '../../store/useScenarioStore'
import CrewEditor from './CrewEditor'
import EquipmentEditor from './EquipmentEditor'
import { calculatedModulePowerDemandW } from '../../domain/resourceSizing'

interface Props {
  module: ScenarioModule
  emergency: EmergencyConfig | null
}

const MODULE_TYPES: { value: ModuleType; label: string }[] = [
  { value: 'habitat', label: 'Habitat' },
  { value: 'storage', label: 'Storage' },
  { value: 'life_support', label: 'Life Support' },
  { value: 'power', label: 'Power' },
  { value: 'propulsion', label: 'Propulsion' },
  { value: 'other', label: 'Other' },
]

export default function ModuleInspector({ module, emergency }: Props) {
  const { updateModule } = useScenarioStore()
  const hasEmergency = emergency?.affectedModuleId === module.id
  const calculatedPowerDemand = calculatedModulePowerDemandW(module)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Module ID (read-only) */}
      <div>
        <label style={labelStyle}>Module ID</label>
        <div style={{ color: 'var(--ink-4)', fontSize: 11, fontFamily: 'monospace', padding: '3px 0' }}>
          {module.id}
        </div>
      </div>

      {/* Emergency badge */}
      {hasEmergency && (
        <div
          style={{
            background: 'var(--ember-wash)',
            border: '1px solid var(--ember)',
            borderRadius: 6,
            padding: '8px 12px',
            color: 'var(--ember)',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <strong>{emergency?.type === 'electronic_short' ? 'Active electronic short' : 'Active fire emergency'}</strong>
          {emergency?.detected ? (
            <span style={{ color: 'var(--good)', marginLeft: 'auto', fontSize: 11 }}>Detected</span>
          ) : (
            <span style={{ color: 'var(--amber)', marginLeft: 'auto', fontSize: 11 }}>Undetected</span>
          )}
        </div>
      )}

      {/* Name */}
      <div>
        <label style={labelStyle}>Name</label>
        <input
          style={inputStyle}
          value={module.name}
          onChange={(e) => updateModule(module.id, { name: e.target.value })}
        />
      </div>

      {/* Type */}
      <div>
        <label style={labelStyle}>Type</label>
        <select
          style={inputStyle}
          value={module.type}
          onChange={(e) => updateModule(module.id, { type: e.target.value as ModuleType })}
        >
          {MODULE_TYPES.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </select>
      </div>

      {/* Optional physical parameters */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
        <div>
          <label style={labelStyle}>Pressure (kPa)</label>
          <input
            style={inputStyle}
            type="number"
            placeholder="101.3"
            value={module.pressure ?? ''}
            onChange={(e) =>
              updateModule(module.id, {
                pressure: e.target.value === '' ? null : parseFloat(e.target.value),
              })
            }
          />
        </div>
        <div>
          <label style={labelStyle}>Air / O₂ Level (%)</label>
          <input
            style={inputStyle}
            type="number"
            placeholder="25"
            step="0.1"
            min="0"
            max="100"
            value={module.oxygenFraction == null ? '' : module.oxygenFraction * 100}
            onChange={(e) =>
              updateModule(module.id, {
                oxygenFraction: e.target.value === '' ? null : parseFloat(e.target.value) / 100,
              })
            }
          />
        </div>
      </div>

      <div>
        <label style={labelStyle}>Other Disaster Disruption ({Math.round(module.disruptionLevel * 100)}%)</label>
        <input
          aria-label="Other disaster disruption"
          style={{ width: '100%', accentColor: 'var(--ember)' }}
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={module.disruptionLevel}
          onChange={(event) => updateModule(module.id, {
            disruptionLevel: Number(event.target.value),
          })}
        />
      </div>

      <div style={{ border: '1px solid var(--line)', borderRadius: 6, padding: 10 }}>
        <div style={{ ...labelStyle, color: 'var(--ink-2)', marginBottom: 8 }}>RESOURCE STATE</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
          <NumberInput label="Power Level (W)" value={module.powerLevelW} onChange={(value) => updateModule(module.id, { powerLevelW: value })} />
          <NumberInput label="Base Module Demand (W)" value={module.powerConsumptionW} onChange={(value) => updateModule(module.id, { powerConsumptionW: value })} />
          <NumberInput label="Water Stored (kg)" value={module.waterStoredKg} onChange={(value) => updateModule(module.id, { waterStoredKg: value })} />
          <NumberInput label="Water Capacity (kg)" value={module.waterCapacityKg} onChange={(value) => updateModule(module.id, { waterCapacityKg: value })} />
        </div>
        <div style={{ color: 'var(--ink-4)', fontSize: 10, marginTop: 7 }}>
          Calculated total power demand: <strong>{calculatedPowerDemand.toFixed(1)} W</strong>
          {' · '}Crew water demand: 0.00264 kg/min per person.
        </div>
      </div>

      {module.type === 'power' && (
        <div style={{ border: '1px solid #a77b20', borderRadius: 6, padding: 10 }}>
          <NumberInput label="Maximum Power Output (W)" value={module.maxPowerOutputW} onChange={(value) => updateModule(module.id, { maxPowerOutputW: value })} />
          <div style={{ color: 'var(--ink-4)', fontSize: 10, marginTop: 6 }}>
            Auto-sized from connected module loads and equal sharing; editable for constrained scenarios.
          </div>
        </div>
      )}

      {module.type === 'life_support' && (
        <div style={{ border: '1px solid #207c8b', borderRadius: 6, padding: 10, display: 'flex', flexDirection: 'column', gap: 9 }}>
          <div style={{ ...labelStyle, color: 'var(--ink-2)', marginBottom: 0 }}>LIFE SUPPORT OUTPUTS</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <Toggle label="AIR" enabled={module.suppliesAir} onClick={() => updateModule(module.id, { suppliesAir: !module.suppliesAir })} color="#7dd3fc" />
            <Toggle label="WATER" enabled={module.suppliesWater} onClick={() => updateModule(module.id, { suppliesWater: !module.suppliesWater })} color="#2563eb" />
          </div>
          {module.suppliesAir && <NumberInput label="Maximum Air Refill (%p/min)" value={module.maxAirOutputPercentPerMin} onChange={(value) => updateModule(module.id, { maxAirOutputPercentPerMin: value })} />}
          {module.suppliesWater && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <NumberInput label="Maximum Water Output (kg/min)" value={module.maxWaterOutputKgPerMin} onChange={(value) => updateModule(module.id, { maxWaterOutputKgPerMin: value })} />
              <NumberInput label="Recovery Efficiency" value={module.waterRecoveryEfficiency} step={0.01} max={1} onChange={(value) => updateModule(module.id, { waterRecoveryEfficiency: value })} />
            </div>
          )}
          <div style={{ color: 'var(--ink-4)', fontSize: 10 }}>
            Output defaults follow connected crew demand and path loss. AIR adds 25W and WATER adds 20W to this module.
          </div>
        </div>
      )}

      <hr style={{ border: 'none', borderTop: '1px solid var(--line)' }} />

      {/* Crew */}
      <CrewEditor moduleId={module.id} crew={module.crew} />

      <hr style={{ border: 'none', borderTop: '1px solid var(--line)' }} />

      {/* Equipment */}
      <EquipmentEditor moduleId={module.id} equipment={module.equipment} />
    </div>
  )
}

function NumberInput({ label, value, onChange, step = 0.01, max }: { label: string; value: number; onChange: (value: number) => void; step?: number; max?: number }) {
  return (
    <div>
      <label style={labelStyle}>{label}</label>
      <input style={inputStyle} type="number" min="0" max={max} step={step} value={value ?? 0} onChange={(event) => onChange(Math.max(0, Number(event.target.value) || 0))} />
    </div>
  )
}

function Toggle({ label, enabled, onClick, color }: { label: string; enabled: boolean; onClick: () => void; color: string }) {
  return (
    <button type="button" onClick={onClick} style={{ background: enabled ? `${color}22` : 'var(--surface-3)', color: enabled ? color : 'var(--ink-4)', border: `1px solid ${enabled ? color : 'var(--line)'}`, borderRadius: 4, padding: '5px 12px', fontSize: 11, cursor: 'pointer' }}>
      {label} {enabled ? 'ON' : 'OFF'}
    </button>
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
