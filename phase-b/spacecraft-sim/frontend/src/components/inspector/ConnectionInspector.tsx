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
        <div style={{ color: 'var(--ink-4)', fontSize: 11, fontFamily: 'monospace', padding: '3px 0' }}>
          {connection.id}
        </div>
      </div>

      {/* Endpoints (read-only) */}
      <div>
        <label style={labelStyle}>Pathway</label>
        <div
          style={{
            background: 'var(--surface)',
            border: '1px solid var(--line)',
            borderRadius: 5,
            padding: '6px 10px',
            color: 'var(--ink)',
            fontSize: 12,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span>{sourceModuleName}</span>
          <span style={{ color: 'var(--ink-3)' }}>↔</span>
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
            color: connection.state === 'open' ? 'var(--good)' : connection.state === 'closed' ? 'var(--ember)' : 'var(--amber)',
          }}
          value={connection.state}
          onChange={(e) => updateConnection(connection.id, { state: e.target.value as ConnectionState })}
        >
          <option value="open" style={{ color: 'var(--good)' }}>Open</option>
          <option value="closed" style={{ color: 'var(--ember)' }}>Closed</option>
          <option value="unknown" style={{ color: 'var(--amber)' }}>Unknown</option>
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
              background: connection.ventilationOn ? 'var(--verified-wash)' : 'var(--surface-3)',
              color: connection.ventilationOn ? 'var(--verified)' : 'var(--ink-4)',
              border: `1px solid ${connection.ventilationOn ? 'var(--verified)' : 'var(--line)'}`,
              borderRadius: 5,
              padding: '4px 12px',
              fontSize: 12,
              cursor: connection.type !== 'imv' ? 'not-allowed' : 'pointer',
              opacity: connection.type !== 'imv' ? 0.4 : 1,
            }}
          >
            {connection.ventilationOn ? 'FLOW ON' : 'FLOW OFF'}
          </button>
          {connection.type !== 'imv' && (
            <span style={{ color: 'var(--ink-4)', fontSize: 11 }}>IMV only</span>
          )}
        </div>
      </div>

      <div>
        <label style={labelStyle}>Hatch Utility Lines</label>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
          {([
            ['powerLineOn', 'POWER', '#facc15'],
            ['airLineOn', 'AIR', '#7dd3fc'],
            ['waterLineOn', 'WATER', '#2563eb'],
          ] as const).map(([field, label, color]) => {
            const enabled = connection[field]
            return (
              <button
                key={field}
                type="button"
                disabled={connection.type !== 'hatch'}
                onClick={() => updateConnection(connection.id, { [field]: !enabled })}
                style={{
                  background: enabled ? `${color}22` : 'var(--surface-3)',
                  color: enabled ? color : 'var(--ink-4)',
                  border: `1px solid ${enabled ? color : 'var(--line)'}`,
                  borderRadius: 4,
                  padding: '5px 3px',
                  fontSize: 9,
                  cursor: connection.type === 'hatch' ? 'pointer' : 'not-allowed',
                  opacity: connection.type === 'hatch' ? 1 : 0.4,
                }}
              >
                {label} {enabled ? 'ON' : 'OFF'}
              </button>
            )
          })}
        </div>
        <div style={{ color: 'var(--ink-4)', fontSize: 10, marginTop: 5 }}>
          Closing the hatch blocks air only. Power and water use independent switches.
        </div>
      </div>

      <div>
        <label style={labelStyle}>Connectivity / inverse resistance</label>
        <input
          aria-label="Current connectivity"
          style={inputStyle}
          type="number"
          min="0"
          max="100"
          step="1"
          disabled={connection.type !== 'hatch'}
          value={connection.connectivity}
          onChange={(e) => updateConnection(connection.id, {
            connectivity: Math.max(0, Math.min(100, Number(e.target.value) || 0)),
          })}
        />
        <div style={{ color: 'var(--ink-4)', fontSize: 10, marginTop: 5, lineHeight: 1.5 }}>
          {connection.type === 'hatch'
            ? `${(4 * connection.connectivity / 100).toFixed(2)} crew/min · ${(10 * connection.connectivity / 100).toFixed(1)}% air/min · baseline ${connection.baseConnectivity}`
            : 'Hatch connections only'}
        </div>
        {connection.type === 'hatch' && (
          <div style={{ color: connection.connectivity < 50 ? 'var(--ember)' : 'var(--ink-4)', fontSize: 10, marginTop: 4 }}>
            Air-coupled negative feedback {connection.connectivity < connection.baseConnectivity ? 'ACTIVE' : 'nominal'}
          </div>
        )}
      </div>

      <div>
        <label style={labelStyle}>Power Passage (%)</label>
        <input
          aria-label="Power passage percent"
          style={inputStyle}
          type="number"
          min="0"
          max="100"
          step="1"
          disabled={connection.type !== 'hatch'}
          value={Math.round(connection.powerTransferFactor * 100)}
          onChange={(event) => updateConnection(connection.id, {
            powerTransferFactor: Math.max(0, Math.min(1, (Number(event.target.value) || 0) / 100)),
          })}
        />
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
        <div style={{ color: 'var(--ink-4)', fontSize: 11, marginTop: 4 }}>
          Numerical interpretation handled by Phase A simulator
        </div>
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
