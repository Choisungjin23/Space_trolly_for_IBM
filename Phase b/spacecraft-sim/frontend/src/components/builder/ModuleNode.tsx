/**
 * ModuleNode — custom React Flow node for spacecraft modules.
 *
 * Visual appearance:
 * - Green border: no emergency
 * - Amber border: emergency in adjacent module
 * - Red border + glow: this module has the active fire emergency
 * - ISOLATED label (future Phase A result)
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { ScenarioModule, EmergencyConfig } from '../../types/scenario'

export interface ModuleNodeData extends Record<string, unknown> {
  module: ScenarioModule
  emergency: EmergencyConfig | null
  isSelected?: boolean
}

const MODULE_TYPE_LABELS: Record<string, string> = {
  habitat: 'HABITAT',
  storage: 'STORAGE',
  life_support: 'LIFE SUPPORT',
  power: 'POWER',
  propulsion: 'PROPULSION',
  other: 'MODULE',
}

const MODULE_TYPE_COLORS: Record<string, string> = {
  habitat: '#3b82f6',
  storage: '#8b5cf6',
  life_support: '#06b6d4',
  power: '#f59e0b',
  propulsion: '#f97316',
  other: '#64748b',
}

function ModuleNode({ data, selected }: NodeProps) {
  const { module, emergency } = data as ModuleNodeData

  const hasEmergency = emergency?.affectedModuleId === module.id
  const typeColor = MODULE_TYPE_COLORS[module.type] ?? '#64748b'
  const typeLabel = MODULE_TYPE_LABELS[module.type] ?? 'MODULE'

  let borderColor = '#2a2d36'
  let glowStyle = ''

  if (hasEmergency) {
    borderColor = '#ef4444'
    glowStyle = '0 0 12px rgba(239, 68, 68, 0.6)'
  } else if (selected) {
    borderColor = '#3b82f6'
  }

  return (
    <div
      style={{
        background: '#1e2128',
        border: `2px solid ${borderColor}`,
        borderRadius: 8,
        minWidth: 160,
        maxWidth: 200,
        fontFamily: '-apple-system, "Segoe UI", system-ui, sans-serif',
        boxShadow: glowStyle || (selected ? '0 0 8px rgba(59, 130, 246, 0.4)' : 'none'),
        cursor: 'pointer',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Top accent bar */}
      <div
        style={{
          height: 3,
          background: hasEmergency ? '#ef4444' : typeColor,
          transition: 'background 0.2s',
        }}
      />

      {/* Header */}
      <div
        style={{
          padding: '8px 12px 4px',
          borderBottom: '1px solid #2a2d36',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 2,
          }}
        >
          {hasEmergency && (
            <span
              style={{
                background: '#7f1d1d',
                color: '#fca5a5',
                fontSize: 9,
                fontWeight: 700,
                padding: '1px 5px',
                borderRadius: 3,
                letterSpacing: '0.05em',
                flexShrink: 0,
              }}
            >
              🔥 FIRE
            </span>
          )}
        </div>
        <div
          style={{
            color: '#e2e8f0',
            fontWeight: 600,
            fontSize: 13,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }}
        >
          {module.name}
        </div>
        <div
          style={{
            color: typeColor,
            fontSize: 9,
            fontWeight: 700,
            letterSpacing: '0.08em',
            marginTop: 1,
          }}
        >
          {typeLabel}
        </div>
      </div>

      {/* Stats */}
      <div style={{ padding: '6px 12px 8px', fontSize: 12, color: '#94a3b8' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>Crew</span>
          <span style={{ color: '#e2e8f0', fontWeight: 500 }}>
            {module.crew.length}
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
          <span>Equipment</span>
          <span style={{ color: '#e2e8f0', fontWeight: 500 }}>
            {module.equipment.length}
          </span>
        </div>
      </div>

      {/* React Flow handles */}
      <Handle
        type="target"
        position={Position.Left}
        style={{ background: '#3b82f6', border: '2px solid #0a0c10', width: 10, height: 10 }}
      />
      <Handle
        type="source"
        position={Position.Right}
        style={{ background: '#3b82f6', border: '2px solid #0a0c10', width: 10, height: 10 }}
      />
      <Handle
        type="target"
        position={Position.Top}
        id="top-target"
        style={{ background: '#3b82f6', border: '2px solid #0a0c10', width: 10, height: 10 }}
      />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom-source"
        style={{ background: '#3b82f6', border: '2px solid #0a0c10', width: 10, height: 10 }}
      />
    </div>
  )
}

export default memo(ModuleNode)
