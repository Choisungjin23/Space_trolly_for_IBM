/**
 * ModuleNode — one pressure volume on the chart.
 *
 * A restrained instrument card, not a dashboard tile. The architecture view
 * stays quiet: name, class, and the two counts that change what an action can
 * do. Warm colour is spent only where a hazard is actually present, so the eye
 * goes straight to the emergency instead of scanning a wall of coloured boxes.
 *
 * Module class is carried by a thin rule and a word, never by hue alone — six
 * module hues are indistinguishable under common colour-vision deficiencies,
 * and the label is what a reader identifies the module by anyway.
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

const HANDLE: React.CSSProperties = {
  background: 'var(--surface-3)',
  border: '1px solid var(--ink-4)',
  width: 7,
  height: 7,
}

function ModuleNode({ data, selected }: NodeProps) {
  const { module, emergency } = data as ModuleNodeData

  const hasEmergency = emergency?.affectedModuleId === module.id
  const typeLabel = MODULE_TYPE_LABELS[module.type] ?? 'MODULE'

  const border = hasEmergency
    ? 'var(--ember)'
    : selected
      ? 'var(--gold)'
      : 'var(--line)'

  return (
    <div
      style={{
        // A burning module sits on warm ground, not the neutral surface: the
        // colour has to reach the eye before the label does.
        background: hasEmergency
          ? 'linear-gradient(180deg, rgba(224,80,63,.16) 0%, rgba(224,80,63,.05) 55%, var(--surface) 100%)'
          : 'var(--surface)',
        border: `1px solid ${border}`,
        borderRadius: 3,
        minWidth: 168,
        maxWidth: 208,
        fontFamily: 'var(--font-ui)',
        boxShadow: selected && !hasEmergency
          ? '0 0 0 1px rgba(194,161,91,.20)'
          : 'none',
        animation: hasEmergency ? 'circe-burn 2.8s ease-in-out infinite' : undefined,
        cursor: 'pointer',
        overflow: 'hidden',
        transition: 'border-color .16s, box-shadow .16s',
      }}
    >
      {/* Heat band: thicker and hotter when this module is the emergency. */}
      <div
        style={{
          height: hasEmergency ? 3 : 1,
          background: hasEmergency
            ? 'linear-gradient(90deg, var(--ember) 0%, var(--ember-bright) 50%, var(--amber) 100%)'
            : 'var(--ink-4)',
          opacity: hasEmergency ? 1 : 0.6,
        }}
      />

      <div style={{ padding: '10px 12px 9px' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            justifyContent: 'space-between',
          }}
        >
          <span
            style={{
              color: 'var(--ink)',
              fontWeight: hasEmergency ? 600 : 500,
              fontSize: 13.5,
              letterSpacing: '.01em',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {module.name}
          </span>

          {hasEmergency && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                background: 'var(--ember)',
                color: '#1a0705',
                fontFamily: 'var(--font-mono)',
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: '.14em',
                padding: '2px 6px',
                borderRadius: 2,
                flexShrink: 0,
              }}
            >
              {emergency?.type === 'electronic_short' ? '⚡ SHORT' : <><FlameMark /> FIRE</>}
            </span>
          )}
        </div>

        <div
          style={{
            color: hasEmergency ? 'var(--ember-bright)' : 'var(--ink-3)',
            fontFamily: 'var(--font-mono)',
            fontSize: 9.5,
            letterSpacing: '.14em',
            marginTop: 4,
          }}
        >
          {typeLabel}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', borderTop: '1px solid var(--line-soft)', padding: '5px 8px', gap: 5, fontFamily: 'var(--font-mono)', fontSize: 8.5 }}>
        <ResourceStat color="#facc15" label="PWR" value={`${module.powerLevelW ?? 0}W`} />
        <ResourceStat color="#7dd3fc" label="AIR" value={`${(((module.oxygenFraction ?? 0.25) * 100)).toFixed(1)}%`} />
        <ResourceStat color="#2563eb" label="H₂O" value={`${(module.waterStoredKg ?? 0).toFixed(2)}kg`} />
      </div>

      {/* Occupancy — the two figures that change what an action can achieve */}
      <div
        style={{
          display: 'flex',
          borderTop: `1px solid ${hasEmergency ? 'var(--ember-wash)' : 'var(--line-soft)'}`,
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
        }}
      >
        <Stat label="CREW" value={module.crew.length} alight={hasEmergency} />
        <div style={{ width: 1, background: 'var(--line-soft)' }} />
        <Stat label="SYS" value={module.equipment.length} alight={hasEmergency} />
      </div>

      <Handle type="target" position={Position.Left} style={HANDLE} />
      <Handle type="source" position={Position.Right} style={HANDLE} />
      <Handle type="target" position={Position.Top} id="top-target" style={HANDLE} />
      <Handle
        type="source"
        position={Position.Bottom}
        id="bottom-source"
        style={HANDLE}
      />
    </div>
  )
}

/** A small flame, drawn rather than typed, so it matches the icon set. */
function FlameMark() {
  return (
    <svg width="7" height="9" viewBox="0 0 7 9" fill="currentColor" aria-hidden>
      <path d="M3.5 0C3.5 2 1.4 2.3 1.4 4.6a2.1 2.1 0 0 0 4.2 0C5.6 3.1 4.3 2.6 4.3 1.5 4.3 2.6 3.5 2.7 3.5 0z" />
      <path d="M3.5 9a1.5 1.5 0 0 1-1.5-1.5c0-1 1.5-1.6 1.5-2.8 0 1.2 1.5 1.8 1.5 2.8A1.5 1.5 0 0 1 3.5 9z" opacity=".65" />
    </svg>
  )
}

function Stat({
  label,
  value,
  alight,
}: {
  label: string
  value: number
  alight?: boolean
}) {
  return (
    <div
      style={{
        flex: 1,
        display: 'flex',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        padding: '6px 12px 7px',
      }}
    >
      <span style={{ color: 'var(--ink-3)', letterSpacing: '.12em' }}>{label}</span>
      <span
        style={{
          color: value === 0
            ? 'var(--ink-4)'
            : alight
              ? 'var(--ember-bright)'
              : 'var(--ink)',
          fontWeight: 500,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {value}
      </span>
    </div>
  )
}

function ResourceStat({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <span style={{ color: 'var(--ink-3)', whiteSpace: 'nowrap' }}>
      <span style={{ color }}>{label}</span> {value}
    </span>
  )
}

export default memo(ModuleNode)
