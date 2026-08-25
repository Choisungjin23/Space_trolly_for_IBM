/**
 * ModuleInspector — panel for editing a selected module's properties.
 */

import type { ScenarioModule, ModuleType, EmergencyConfig } from '../../types/scenario'
import { useScenarioStore } from '../../store/useScenarioStore'
import CrewEditor from './CrewEditor'
import EquipmentEditor from './EquipmentEditor'

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Module ID (read-only) */}
      <div>
        <label style={labelStyle}>Module ID</label>
        <div style={{ color: '#475569', fontSize: 11, fontFamily: 'monospace', padding: '3px 0' }}>
          {module.id}
        </div>
      </div>

      {/* Emergency badge */}
      {hasEmergency && (
        <div
          style={{
            background: '#450a0a',
            border: '1px solid #7f1d1d',
            borderRadius: 6,
            padding: '8px 12px',
            color: '#fca5a5',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          🔥 <strong>Active Fire Emergency</strong>
          {emergency?.detected ? (
            <span style={{ color: '#86efac', marginLeft: 'auto', fontSize: 11 }}>Detected</span>
          ) : (
            <span style={{ color: '#f59e0b', marginLeft: 'auto', fontSize: 11 }}>Undetected</span>
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
          <label style={labelStyle}>O₂ Fraction</label>
          <input
            style={inputStyle}
            type="number"
            placeholder="0.21"
            step="0.01"
            min="0"
            max="1"
            value={module.oxygenFraction ?? ''}
            onChange={(e) =>
              updateModule(module.id, {
                oxygenFraction: e.target.value === '' ? null : parseFloat(e.target.value),
              })
            }
          />
        </div>
      </div>

      <hr style={{ border: 'none', borderTop: '1px solid #2a2d36' }} />

      {/* Crew */}
      <CrewEditor moduleId={module.id} crew={module.crew} />

      <hr style={{ border: 'none', borderTop: '1px solid #2a2d36' }} />

      {/* Equipment */}
      <EquipmentEditor moduleId={module.id} equipment={module.equipment} />
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
