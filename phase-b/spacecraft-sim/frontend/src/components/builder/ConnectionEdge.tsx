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
import type { EscapeTarget, ScenarioConnection } from '../../types/scenario'

export interface ConnectionEdgeData extends Record<string, unknown> {
  connection: ScenarioConnection
  /** True when this pathway meets the module that is alight. */
  touchesFire?: boolean
  escapeTarget?: EscapeTarget
}

/**
 * Pathway class reads through line treatment, not through five colours.
 * A hatch is a solid rule, an IMV duct is dashed because it only carries while
 * a fan runs, and a leak is finely broken because it is a path nobody chose.
 * Colour stays neutral here so the emergency remains the only warm thing on
 * the chart.
 */
const PATH_STYLE: Record<string, { dash?: string; width: number }> = {
  hatch: { width: 1.25 },
  imv: { dash: '5,3', width: 1.25 },
  leak: { dash: '1.5,3', width: 1 },
  other: { width: 1 },
}

const CONNECTION_TYPE_SHORT: Record<string, string> = {
  hatch: 'HATCH',
  imv: 'IMV',
  leak: 'LEAK',
  other: 'PATH',
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
  const isLeak = connection?.type === 'leak'
  const shape = PATH_STYLE[connection?.type ?? 'other'] ?? PATH_STYLE.other
  const typeShort = CONNECTION_TYPE_SHORT[connection?.type ?? 'other']
  const touchesFire = (data as ConnectionEdgeData | undefined)?.touchesFire
  const escapeTarget = (data as ConnectionEdgeData | undefined)?.escapeTarget
  const isEscape = escapeTarget?.connectionId === connection?.id
  const strokeColor = selected
    ? 'var(--gold)'
    : isEscape
      ? 'var(--good)'
    : isLeak
      ? 'var(--ember)'
      : touchesFire && !isClosed
        ? 'var(--ember)'
        : 'var(--ink-4)'
  const strokeDash = isClosed ? '2,4' : shape.dash

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth: selected ? 1.75 : touchesFire ? shape.width + 0.6 : shape.width,
          strokeDasharray: strokeDash,
          opacity: isClosed ? 0.55 : 1,
          transition: 'stroke .15s, opacity .15s',
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
              background: 'var(--void)',
              border: `1px solid ${
                selected ? 'var(--gold)' : touchesFire ? 'var(--ember)' : 'var(--line)'
              }`,
              borderRadius: 2,
              padding: '1px 6px',
              fontSize: 9.5,
              fontWeight: 500,
              letterSpacing: '.12em',
              color: selected
                ? 'var(--gold)'
                : touchesFire
                  ? 'var(--ember)'
                  : 'var(--ink-2)',
              fontFamily: 'var(--font-mono)',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: 5,
            }}
          >
            {typeShort}
            {isEscape && escapeTarget && (
              <span style={{ color: 'var(--good)' }} title="Evacuation target direction">
                ESC {escapeTarget.fromModuleId} » {escapeTarget.toModuleId}
              </span>
            )}
            {connection?.type === 'hatch' && (
              <span
                style={{ color: connection.connectivity < 50 ? 'var(--ember)' : 'var(--ink-3)' }}
                title="Connectivity (inverse movement/air resistance)"
              >
                {Math.round(connection.connectivity)}/100
              </span>
            )}
            {connection?.type === 'hatch' && connection.powerTransferFactor < 1 && (
              <span style={{ color: 'var(--ember)' }} title="Electronic-short power passage">
                PWR {Math.round(connection.powerTransferFactor * 100)}%
              </span>
            )}
            {connection?.type === 'imv' && connection.ventilationOn && (
              <span style={{ color: 'var(--verified)' }} title="Ventilation running">
                FLOW
              </span>
            )}
            {isClosed && (
              <span style={{ color: 'var(--ember)' }} title="Closed">
                SEALED
              </span>
            )}
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

export default memo(ConnectionEdge)
