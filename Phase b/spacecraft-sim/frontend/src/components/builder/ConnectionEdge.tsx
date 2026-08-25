/**
 * ConnectionEdge — custom React Flow edge for spacecraft connections.
 *
 * Visual appearance:
 * - Solid line: open connection
 * - Dashed line: closed connection
 * - Color-coded by transfer class
 * - IMV connections show ventilation indicator
 */

import { memo } from 'react'
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from '@xyflow/react'
import type { ScenarioConnection } from '../../types/scenario'

export interface ConnectionEdgeData extends Record<string, unknown> {
  connection: ScenarioConnection
}

const TRANSFER_CLASS_COLORS: Record<string, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#22c55e',
  none: '#475569',
  unknown: '#475569',
}

const CONNECTION_TYPE_SHORT: Record<string, string> = {
  hatch: 'H',
  imv: 'IMV',
  leak: 'LK',
  other: '?',
}

function ConnectionEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  markerEnd,
}: EdgeProps) {
  const connection = (data as ConnectionEdgeData | undefined)?.connection

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const isClosed = connection?.state === 'closed'
  const transferColor = TRANSFER_CLASS_COLORS[connection?.transferClass ?? 'unknown']
  const typeShort = CONNECTION_TYPE_SHORT[connection?.type ?? 'other']
  const strokeColor = selected ? '#3b82f6' : isClosed ? '#475569' : transferColor
  const strokeDash = isClosed ? '6,4' : undefined

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 2.5 : 1.8,
          strokeDasharray: strokeDash,
          transition: 'stroke 0.15s',
        }}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              background: '#1e2128',
              border: `1px solid ${strokeColor}`,
              borderRadius: 4,
              padding: '1px 6px',
              fontSize: 10,
              fontWeight: 600,
              color: strokeColor,
              fontFamily: '-apple-system, "Segoe UI", system-ui, sans-serif',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: 3,
            }}
          >
            {typeShort}
            {connection?.type === 'imv' && connection.ventilationOn && (
              <span style={{ color: '#06b6d4' }}>↻</span>
            )}
            {isClosed && <span style={{ color: '#ef4444' }}>✕</span>}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export default memo(ConnectionEdge)
