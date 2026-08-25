/**
 * ConnectionInspector — panel for editing a selected connection's properties.
 *
 * Does NOT expose hazard_spread_probability — physical interpretation belongs to Phase A.
 * Does NOT map transfer class to numeric probability values.
 */

import type { ScenarioConnection, ConnectionType, ConnectionState, FlowDirection, TransferClass } from '../../types/scenario'
import { useScenarioStore } from '../../store/useScenarioStore'

interface Props {
  connection: ScenarioConnection
  sourceModuleName: string
  targetModuleName: string
}

export default function ConnectionInspector({ connection, sourceModuleName, targetModuleName }: Props) {
  const { updateConnection } = useScenarioStore()

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* Connection ID (read-only) */}
      <div>
        <label style={labelStyle}>Connection ID</label>
        <div style={{ color: '#475569', fontSize: 11, fontFamily: 'monospace', padding: '3px 0' }}>
          {connection.id}
        </div>
      </div>

      {/* Endpoints (read-only) */}
      <div>
        <label style={labelStyle}>Pathway</label>
        <div
          style={{
            background: '#111318',
            border: '1px solid #2a2d36',
            borderRadius: 5,
            padding: '6px 10px',
            color: '#e2e8f0',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span>{sourceModuleName}</span>
          <span style={{ color: '#64748b' }}>↔</span>
          <span>{targetModuleName}</span>
        </div>
      </div>

      {/* Type */}
      <div>
        <label style={labelStyle}>Connection Type</label>
        <select
          style={inputStyle}
          value={connection.type}
          onChange={(e) => updateConnection(connection.id, { type: e.target.value as ConnectionType })}
        >
          <option value="hatch">Hatch</option>
          <option value="imv">IMV (Ventilation Duct)</option>
          <option value="leak">Leak / Atmospheric Path</option>
          <option value="other">Other</option>
        </select>
      </div>

      {/* State */}
      <div>
        <label style={labelStyle}>Path State</label>
        <select
          style={{
            ...inputStyle,
            color: connection.state === 'open' ? '#22c55e' : connection.state === 'closed' ? '#ef4444' : '#f59e0b',
          }}
          value={connection.state}
          onChange={(e) => updateConnection(connection.id, { state: e.target.value as ConnectionState })}
        >
          <option value="open" style={{ color: '#22c55e' }}>Open</option>
          <option value="closed" style={{ color: '#ef4444' }}>Closed</option>
          <option value="unknown" style={{ color: '#f59e0b' }}>Unknown</option>
        </select>
      </div>

      {/* Ventilation (IMV only) */}
      <div>
        <label style={labelStyle}>Ventilation</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            onClick={() =>
              updateConnection(connection.id, { ventilationOn: !connection.ventilationOn })
            }
            disabled={connection.type !== 'imv'}
            style={{
              background: connection.ventilationOn ? '#164e63' : '#1e2128',
              color: connection.ventilationOn ? '#67e8f9' : '#475569',
              border: `1px solid ${connection.ventilationOn ? '#06b6d4' : '#2a2d36'}`,
              borderRadius: 5,
              padding: '4px 12px',
              fontSize: 12,
              cursor: connection.type !== 'imv' ? 'not-allowed' : 'pointer',
              opacity: connection.type !== 'imv' ? 0.4 : 1,
            }}
          >
            {connection.ventilationOn ? '↻ ON' : 'OFF'}
          </button>
          {connection.type !== 'imv' && (
            <span style={{ color: '#475569', fontSize: 11 }}>IMV only</span>
          )}
        </div>
      </div>

      {/* Flow direction */}
      <div>
        <label style={labelStyle}>Flow Direction</label>
        <select
          style={inputStyle}
          value={connection.flowDirection}
          onChange={(e) => updateConnection(connection.id, { flowDirection: e.target.value as FlowDirection })}
        >
          <option value="bidirectional">Bidirectional</option>
          <option value="source_to_target">Source → Target</option>
          <option value="target_to_source">Target → Source</option>
          <option value="none">None</option>
          <option value="unknown">Unknown</option>
        </select>
      </div>

      {/* Transfer class */}
      <div>
        <label style={labelStyle}>Transfer Class</label>
        <select
          style={inputStyle}
          value={connection.transferClass}
          onChange={(e) => updateConnection(connection.id, { transferClass: e.target.value as TransferClass })}
        >
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
          <option value="none">None</option>
          <option value="unknown">Unknown</option>
        </select>
        <div style={{ color: '#475569', fontSize: 11, marginTop: 4 }}>
          Numerical interpretation handled by Phase A simulator
        </div>
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
